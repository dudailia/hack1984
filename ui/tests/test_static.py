"""Static checks on the page: offline only, both themes wired, key T present, leak rule from FORMATS.md section 10."""
import os
import re
import unittest

UI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(name):
    with open(os.path.join(UI, name), encoding="utf-8") as f:
        return f.read()


class StaticPage(unittest.TestCase):
    def test_no_external_resources(self):
        for name in ("index.html", "styles.css", "styles-1984.css", "app.js", "outbound.js", "results.js", "runview.js"):
            text = read(name)
            # Only the SVG namespace URI is allowed (it is an identifier, never fetched).
            urls = [u for u in re.findall(r"https?://[^\s\"')]+", text) if not u.startswith("http://www.w3.org/2000/svg")]
            self.assertEqual(urls, [], name)
            self.assertNotIn("@import", text, name)

    def test_both_themes_linked_and_console_is_default(self):
        html = read("index.html")
        self.assertRegex(html, r'<link rel="stylesheet" id="css-console" href="styles.css">')
        self.assertRegex(html, r'<link rel="stylesheet" id="css-classic" href="styles-1984.css" disabled>')

    def test_each_theme_hides_the_others_elements(self):
        self.assertIn(".t-classic", read("styles.css"))
        self.assertIn(".t-console { display: none !important; }", read("styles-1984.css"))

    def test_key_t_switches_theme(self):
        self.assertRegex(read("app.js"), r"case 't': applyTheme\(")

    def test_leak_rule_matches_formats(self):
        js = read("app.js")
        self.assertIn("rule === 'canary' || rule.startsWith('secret.') || rule.startsWith('provenance.')", js)

    def test_run_done_reason_shown_next_to_outcome(self):
        # FORMATS §10 run_done.data.reason: the answer bar and the run label both use RunView.outcomeText.
        js = read("app.js")
        self.assertIn("Run ended: ${window.RunView.outcomeText(s.done)}.", js)
        self.assertIn("if (s.done) bits.push(window.RunView.outcomeText(s.done));", js)
        self.assertNotRegex(js, r"Run ended: \$\{s\.done\.outcome\}")

    def test_console_theme_has_no_hacker_decorations(self):
        css = read("styles.css")
        self.assertNotIn("repeating-linear-gradient", css)
        self.assertNotIn("feTurbulence", css)
        self.assertNotIn("text-transform: uppercase", css)

    def test_status_text_uses_the_darker_shades(self):
        css = read("styles.css")
        self.assertIn("--red-text: #B91C1C;", css)
        self.assertIn("--green-text: #047857;", css)
        # Red and green as text colours only through the darker tokens.
        self.assertNotRegex(css, r"(?<![-\w])color: var\(--(red|green)\);")

    def test_reduced_motion_respected(self):
        self.assertIn("prefers-reduced-motion: reduce", read("styles.css"))


if __name__ == "__main__":
    unittest.main()
