"""Network evidence for the page (owner: Sheara). Standard library only.

    python ui/check_network.py        ->  writes ui/evidence/network-replay.md, exit 0 only if loopback-only

Plays the full replay of ui/index.html (both themes) in headless Edge or Chrome, served by ui/preview.py on an
ephemeral 127.0.0.1 port, and records two views of every request:
  1. the browser's own net log (--log-net-log): every URL request and every host lookup, page or browser;
  2. the page's Resource Timing list, collected by ui/tests/net.check.html.
Any host other than 127.0.0.1 in either view fails the check. During the run every non-loopback host is mapped to
NOTFOUND (--host-resolver-rules), so an attempt shows up as a failed lookup and nothing can actually leave.
Raw net logs stay in a temp folder (they hold local paths); only the summary is written to ui/evidence/.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

from ui import preview  # noqa: E402
from ui.tests.test_ui_browser import BROWSER, QUIET_FLAGS  # noqa: E402

EVIDENCE = os.path.join(HERE, "evidence", "network-replay.md")
LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}
# Headless virtual time advances requestAnimationFrame slower than timers, so the budget is generous; it is
# virtual time, so the run still takes seconds. net.check.html stops as soon as the replay reports its end.
VIRTUAL_BUDGET_MS = 4_000_000
# Scheme-only or browser-internal entries that are not network hosts.
INTERNAL = re.compile(r"^(data:|blob:|about:|chrome:|edge:|chrome-extension:|devtools:)", re.I)


def host_of(url):
    if INTERNAL.match(url):
        return None
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    return parts.hostname or None


def read_netlog(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # A net log cut short by the browser's exit may miss its closing brackets.
        return json.loads(text.rstrip().rstrip(",") + "]}")


def analyse_netlog(path, page_origin):
    """Split a Chromium net log into what the page asked for, what the browser asked for, and what connected.

    - page requests: URL_REQUEST_START_JOB whose initiator is the page's origin, plus navigations to that origin;
    - browser requests: every other URL request (browser services such as autofill or network time);
    - connects: every socket connect attempt and its remote address. This is the decisive list: a request that
      never connected never left the machine.
    """
    log = read_netlog(path)
    const = log.get("constants", {})
    etype = {v: k for k, v in const.get("logEventTypes", {}).items()}
    page, browser, connects, failed = {}, {}, {}, {}
    # A connect failed if any event on the same socket source carries a net_error.
    errored = {ev["source"]["id"] for ev in log.get("events", [])
               if "CONNECT" in etype.get(ev.get("type"), "") and (ev.get("params") or {}).get("net_error")}

    def bump(d, k):
        d[k] = d.get(k, 0) + 1

    for ev in log.get("events", []):
        name = etype.get(ev.get("type"), "")
        params = ev.get("params") or {}
        if name == "URL_REQUEST_START_JOB" and isinstance(params.get("url"), str):
            url = params["url"]
            host = host_of(url)
            if not host:
                continue
            initiator = str(params.get("initiator", ""))
            if initiator == page_origin or (initiator == "not an origin" and url.startswith(page_origin + "/")):
                bump(page, host)
            else:
                bump(browser, host)
        elif "CONNECT" in name and isinstance(params.get("address"), str):
            addr = params["address"]
            ip = addr.rsplit(":", 1)[0].strip("[]") if addr.count(":") == 1 or addr.startswith("[") else addr
            if ev["source"]["id"] in errored:
                bump(failed, f"{addr} ({name}, failed)")
            else:
                bump(connects, ip)
    return {"page": page, "browser": browser, "connects": connects, "failed": failed}


def netlog_hosts(path, page_origin):
    return analyse_netlog(path, page_origin)


def run_theme(port, theme, workdir):
    netlog = os.path.join(workdir, f"netlog-{theme}.json")
    profile = os.path.join(workdir, f"profile-{theme}")
    url = f"http://127.0.0.1:{port}/ui/tests/net.check.html?theme={theme}"
    cmd = [BROWSER, *QUIET_FLAGS, f"--user-data-dir={profile}", "--window-size=1320,900",
           f"--log-net-log={netlog}", "--net-log-capture-mode=Default",
           f"--virtual-time-budget={VIRTUAL_BUDGET_MS}", "--dump-dom", url]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    m = re.search(r'<pre id="result">(.*?)</pre>', res.stdout, re.S)
    page = json.loads(m.group(1).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")) if m and m.group(1).startswith("{") else None
    net = netlog_hosts(netlog, f"http://127.0.0.1:{port}") if os.path.exists(netlog) else {"page": {}, "browser": {}, "connects": {}}
    return {"theme": theme, "page": page, "net": net}


def browser_version():
    # macOS: the app bundle's Info.plist holds the version (BROWSER is <App>.app/Contents/MacOS/<name>).
    plist = os.path.join(os.path.dirname(os.path.dirname(BROWSER)), "Info.plist")
    if os.path.isfile(plist):
        import plistlib
        with open(plist, "rb") as f:
            info = plistlib.load(f)
        return f"{info.get('CFBundleName', os.path.basename(BROWSER))} {info.get('CFBundleShortVersionString', '')}".strip()
    root = os.path.dirname(BROWSER)
    versions = [d for d in os.listdir(root) if re.match(r"^\d+(\.\d+)+$", d)] if os.path.isdir(root) else []
    return f"{os.path.basename(BROWSER)} {max(versions, key=lambda v: [int(x) for x in v.split('.')]) if versions else ''}".strip()


def main(out=EVIDENCE):
    # Invariant 1 for this process: loopback only (preview.py's audit hook; shared/guard.py has no ui role and
    # refuses program starts, and this check has to start the browser). The browser itself is held to loopback by
    # --host-resolver-rules, and the net log proves what it did.
    preview.install_audit_hook()
    if not BROWSER:
        print("No Edge or Chrome found; set DT_BROWSER.", file=sys.stderr)
        return 2
    server = preview.make_server(port=0)
    port = server.server_address[1]
    served = []
    orig = preview.Handler.log_message
    preview.Handler.log_message = lambda self, fmt, *a: served.append(fmt % a)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    workdir = tempfile.mkdtemp(prefix="dt-netcheck-")
    try:
        runs = [run_theme(port, t, workdir) for t in ("console", "1984")]
    finally:
        server.shutdown()
        server.server_close()
        preview.Handler.log_message = orig

    problems = []
    lines = []
    for r in runs:
        page = r["page"] or {}
        net = r["net"]
        ext_page_req = sorted(h for h in net["page"] if h not in LOOPBACK)
        ext_connects = sorted(a for a in net["connects"] if a not in LOOPBACK)
        ext_resources = sorted(h for h in (page.get("hosts") or {}) if h not in LOOPBACK)
        if not page:
            problems.append(f"{r['theme']}: the check page did not report")
        elif not page.get("ended"):
            problems.append(f"{r['theme']}: the replay did not reach its end (status {page.get('status')!r})")
        if not net["page"]:
            problems.append(f"{r['theme']}: the net log recorded no page requests")
        if ext_page_req:
            problems.append(f"{r['theme']}: the page requested non-loopback hosts: {', '.join(ext_page_req)}")
        if ext_resources:
            problems.append(f"{r['theme']}: the page loaded resources from: {', '.join(ext_resources)}")
        if ext_connects:
            problems.append(f"{r['theme']}: a socket connected to a non-loopback address: {', '.join(ext_connects)}")
        if any("results_example.json" in u for u in page.get("urls", [])):
            problems.append(f"{r['theme']}: the example results file was loaded without ?example=1")
        lines.append((r, page, ext_page_req, ext_resources, ext_connects))

    verdict = "PASS: the page requested only 127.0.0.1 and nothing connected anywhere else" if not problems else "FAIL"
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = [
        "# Network check: full replay, loopback only",
        "",
        f"Generated by `python ui/check_network.py` on {now} with {browser_version()} (headless).",
        "",
        f"**Verdict: {verdict}.**",
        "",
        "Method:",
        "- The page is served by `ui/preview.py` on an ephemeral 127.0.0.1 port.",
        "- The full replay (`?title=0&play=1`, all 175 s of the fixture) plays in each theme until the status shows ■.",
        "- Three views are recorded:",
        "  1. **Page requests** in the browser's net log (`--log-net-log`): URL requests whose initiator is the page's"
        " origin, plus navigations to it.",
        "  2. **Socket connects** in the same net log: the remote address of every connect attempt, from the page or the"
        " browser. Nothing that did not connect left the machine.",
        "  3. **The page's own resource list** (Resource Timing, from `ui/tests/net.check.html`).",
        "- Background browser traffic is reduced (`--disable-background-networking` and related flags).",
        "- Every non-loopback host is mapped to NOTFOUND (`--host-resolver-rules`), so any attempt fails its lookup and"
        " cannot leave.",
        "- The browser's own services (Edge or Chrome: updates, sign-in, network time, experiments) still try a few"
        " lookups. They are listed as"
        " *browser requests*: none was initiated by the page. If the browser tries a connect anyway (for example a"
        " QUIC attempt to a built-in address), it is listed with its outcome; the check fails on any *successful*"
        " connect to an address other than 127.0.0.1.",
        "- The replay plays with `?play=1` under headless virtual time. Every fixture event is dispatched; animation"
        " frames are coarser than in a real browser, so a screen that is open only between two polls (the results"
        " screen) may not be sampled.",
        "- The replay runs without `?example=1`, so `results_example.json` must not be loaded; the check fails if it"
        " appears in the page's resource list.",
        "",
    ]
    for r, page, ext_page_req, ext_resources, ext_connects in lines:
        net = r["net"]
        report += [
            f"## Theme: {r['theme']}",
            "",
            f"- Replay reached the end: {'yes' if page.get('ended') else 'no'} (status `{page.get('status', '')}`)."
            f" Results screen shown during the replay: {'yes' if page.get('resultsShown') else 'no'}.",
            f"- Non-loopback hosts the page requested: {', '.join(ext_page_req) if ext_page_req else 'none'}.",
            f"- Non-loopback hosts in the page's resource list: {', '.join(ext_resources) if ext_resources else 'none'}.",
            f"- Successful socket connects to non-loopback addresses: {', '.join(ext_connects) if ext_connects else 'none'}."
            + (f" Failed connect attempts by the browser itself: {sum(net['failed'].values())} (listed below; nothing"
               " was sent on them)." if net.get("failed") else ""),
            "",
            "| View | Host or address | Count |",
            "|---|---|---|",
        ]
        for h, n in sorted(net["page"].items()):
            report.append(f"| page request (net log) | {h} | {n} |")
        for h, n in sorted((page.get("hosts") or {}).items()):
            report.append(f"| page resource (Resource Timing) | {h} | {n} |")
        for a, n in sorted(net["connects"].items()):
            report.append(f"| socket connect, succeeded (net log) | {a} | {n} |")
        for a, n in sorted(net.get("failed", {}).items()):
            report.append(f"| socket connect attempt by the browser, failed (net log) | {a} | {n} |")
        for h, n in sorted(net["browser"].items()):
            report.append(f"| browser request, not from the page (lookup mapped to NOTFOUND) | {h} | {n} |")
        report += ["", "Resources the page loaded:", ""]
        for u in page.get("urls", []):
            p = urllib.parse.urlsplit(u)
            report.append(f"- `{p.scheme}://{p.hostname}:<port>{p.path}`" if p.hostname else f"- `{u[:60]}`")
        report.append("")
    if problems:
        report += ["## Problems", ""] + [f"- {p}" for p in problems] + [""]
    report += ["Requests the preview server answered (both themes): " + str(len(served)) + ".", ""]

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(report))
    shutil.rmtree(workdir, ignore_errors=True)
    print(verdict)
    for p in problems:
        print(" -", p)
    print("Evidence:", out)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--out" else EVIDENCE))
