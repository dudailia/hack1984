"""Read refs and objects from a repo's .git directly, without running git.

baseline/redteam.py and baseline/judge.py run under the loopback guard (shared/guard.py), which refuses to start
programs. They need three facts that used to come from git: the short HEAD commit, whether the checks-frozen tag
exists, and whether checks/ still matches that tag. This module reads them from the files git itself writes:

- refs: HEAD (symbolic or detached), loose refs, packed-refs (including "^" peeled lines), linked worktrees
  (a .git file "gitdir: ..." plus commondir);
- objects: loose (zlib) and packed (pack index v2, OFS_DELTA and REF_DELTA deltas). Every object read is checked
  against its SHA-1 name, so a corrupt or misread object is a GitError, never a wrong answer.
Not supported (GitError, so callers report "unknown"): SHA-256 repositories, the reftable ref format, alternates.
Standard library only; nothing here writes to .git.
"""
import hashlib
import mmap
import os
import re
import struct
import zlib

_HEX40 = re.compile(r"[0-9a-f]{40}")
_REF_NAME = re.compile(r"[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*")
_TYPES = {1: "commit", 2: "tree", 3: "blob", 4: "tag"}
_OFS_DELTA, _REF_DELTA = 6, 7
_PER_WORKTREE = ("refs/bisect/", "refs/worktree/", "refs/rewritten/")


class GitError(Exception):
    pass


def _read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
        return None


def blob_id(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class _Pack:
    def __init__(self, idx_path):
        with open(idx_path, "rb") as f:
            idx = f.read()
        if idx[:4] != b"\xfftOc" or struct.unpack(">I", idx[4:8])[0] != 2:
            raise GitError("unsupported pack index %s" % os.path.basename(idx_path))
        n = struct.unpack(">I", idx[8 + 255 * 4:8 + 256 * 4])[0]
        names_at = 8 + 256 * 4
        offs_at = names_at + 20 * n + 4 * n
        large_at = offs_at + 4 * n
        self.offsets = {}
        for i in range(n):
            off = struct.unpack(">I", idx[offs_at + 4 * i:offs_at + 4 * i + 4])[0]
            if off & 0x80000000:
                j = off & 0x7FFFFFFF
                off = struct.unpack(">Q", idx[large_at + 8 * j:large_at + 8 * j + 8])[0]
            self.offsets[idx[names_at + 20 * i:names_at + 20 * i + 20].hex()] = off
        self.pack_path = idx_path[:-4] + ".pack"
        self._data = None

    def data(self):
        if self._data is None:
            with open(self.pack_path, "rb") as f:
                self._data = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            if self._data[:4] != b"PACK":
                raise GitError("bad pack %s" % os.path.basename(self.pack_path))
        return self._data

    def entry(self, off):
        """(type number, size, position of the compressed data, base: offset or sha or None)."""
        d = self.data()
        c = d[off]
        kind, size, shift, pos = (c >> 4) & 7, c & 15, 4, off + 1
        while c & 0x80:
            c = d[pos]
            size |= (c & 0x7F) << shift
            shift, pos = shift + 7, pos + 1
        base = None
        if kind == _OFS_DELTA:
            c = d[pos]
            rel, pos = c & 0x7F, pos + 1
            while c & 0x80:
                c = d[pos]
                rel, pos = ((rel + 1) << 7) | (c & 0x7F), pos + 1
            base = off - rel
        elif kind == _REF_DELTA:
            base, pos = bytes(d[pos:pos + 20]).hex(), pos + 20
        return kind, size, pos, base

    def inflate(self, pos, size):
        d = zlib.decompressobj()
        out = d.decompress(self.data()[pos:pos + max(size * 2 + 1024, 64)], size) if size else b""
        tail = pos + max(size * 2 + 1024, 64)
        while len(out) < size and not d.eof:  # rare: very compressible data longer than the first window
            chunk = self.data()[tail:tail + 65536]
            if not chunk:
                break
            tail += len(chunk)
            out += d.decompress(chunk, size - len(out))
        if len(out) != size:
            raise GitError("pack entry inflated to %d bytes, expected %d" % (len(out), size))
        return out


def _varint(delta, pos):
    value, shift = 0, 0
    while True:
        c = delta[pos]
        pos += 1
        value |= (c & 0x7F) << shift
        shift += 7
        if not c & 0x80:
            return value, pos


def _apply_delta(base, delta):
    src, pos = _varint(delta, 0)
    dst, pos = _varint(delta, pos)
    if src != len(base):
        raise GitError("delta base size mismatch")
    out = bytearray()
    while pos < len(delta):
        op = delta[pos]
        pos += 1
        if op & 0x80:
            off = size = 0
            for i in range(4):
                if op & (1 << i):
                    off |= delta[pos] << (8 * i)
                    pos += 1
            for i in range(3):
                if op & (0x10 << i):
                    size |= delta[pos] << (8 * i)
                    pos += 1
            size = size or 0x10000
            if off + size > len(base):
                raise GitError("delta copy out of range")
            out += base[off:off + size]
        elif op:
            out += delta[pos:pos + op]
            pos += op
        else:
            raise GitError("delta opcode 0")
    if len(out) != dst:
        raise GitError("delta result size mismatch")
    return bytes(out)


class Repo:
    def __init__(self, worktree):
        dotgit = os.path.join(worktree, ".git")
        if os.path.isdir(dotgit):
            git_dir = dotgit
        elif os.path.isfile(dotgit):
            line = (_read_text(dotgit) or "").strip()
            if not line.startswith("gitdir:"):
                raise GitError(".git file without gitdir")
            git_dir = os.path.normpath(os.path.join(worktree, line[len("gitdir:"):].strip()))
        else:
            raise GitError("no .git in %s" % worktree)
        common = _read_text(os.path.join(git_dir, "commondir"))
        self.git_dir = git_dir
        self.common_dir = os.path.normpath(os.path.join(git_dir, common.strip())) if common else git_dir
        if os.path.isdir(os.path.join(self.common_dir, "reftable")):
            raise GitError("reftable ref storage is not supported")
        self._packs = None
        self._packed_refs = None

    # ---- refs
    def _packed(self):
        if self._packed_refs is None:
            refs, last = {}, None
            for line in (_read_text(os.path.join(self.common_dir, "packed-refs")) or "").splitlines():
                if not line or line.startswith("#"):
                    continue
                if line.startswith("^"):
                    if last is not None:
                        refs[last] = (refs[last][0], line[1:].strip())
                    continue
                sha, _, name = line.partition(" ")
                if _HEX40.fullmatch(sha) and name:
                    refs[name], last = (sha, None), name
            self._packed_refs = refs
        return self._packed_refs

    def read_ref(self, name, _depth=0):
        """The 40-hex object a ref points to (symbolic refs followed), or None if the ref does not exist."""
        if not isinstance(name, str) or not _REF_NAME.fullmatch(name) or ".." in name.split("/"):
            raise GitError("bad ref name %r" % (name,))
        if _depth > 5:
            raise GitError("symbolic ref loop at %s" % name)
        per_worktree = "/" not in name or name.startswith(_PER_WORKTREE)
        text = _read_text(os.path.join(self.git_dir if per_worktree else self.common_dir, *name.split("/")))
        if text is not None:
            text = text.strip()
            if text.startswith("ref:"):
                return self.read_ref(text[4:].strip(), _depth + 1)
            if _HEX40.fullmatch(text):
                return text
            raise GitError("unreadable ref %s" % name)
        found = self._packed().get(name)
        return found[0] if found else None

    # ---- objects
    def packs(self):
        if self._packs is None:
            base = os.path.join(self.common_dir, "objects", "pack")
            names = sorted(n for n in os.listdir(base) if n.endswith(".idx")) if os.path.isdir(base) else []
            self._packs = [_Pack(os.path.join(base, n)) for n in names]
        return self._packs

    def has_object(self, sha):
        return (os.path.isfile(os.path.join(self.common_dir, "objects", sha[:2], sha[2:]))
                or any(sha in p.offsets for p in self.packs()))

    def _raw(self, sha):
        """(type, body) without the hash check."""
        if not _HEX40.fullmatch(sha or ""):
            raise GitError("bad object name %r" % (sha,))
        path = os.path.join(self.common_dir, "objects", sha[:2], sha[2:])
        if os.path.isfile(path):
            with open(path, "rb") as f:
                try:
                    raw = zlib.decompress(f.read())
                except zlib.error as e:
                    raise GitError("corrupt loose object %s: %s" % (sha, e)) from None
            header, _, body = raw.partition(b"\0")
            kind, _, size = header.decode("ascii", "replace").partition(" ")
            if not size.isdigit() or int(size) != len(body):
                raise GitError("corrupt loose object %s" % sha)
            return kind, body
        for pack in self.packs():
            if sha in pack.offsets:
                return self._from_pack(pack, pack.offsets[sha])
        raise GitError("object %s not found" % sha)

    def _from_pack(self, pack, off):
        chain = []
        for _ in range(10000):
            kind, size, pos, base = pack.entry(off)
            if kind in _TYPES:
                body = pack.inflate(pos, size)
                break
            if kind == _OFS_DELTA:
                chain.append(pack.inflate(pos, size))
                off = base
            elif kind == _REF_DELTA:
                chain.append(pack.inflate(pos, size))
                kind_name, body = self.read_object(base)
                kind = {v: k for k, v in _TYPES.items()}[kind_name]
                break
            else:
                raise GitError("unknown pack entry type %d" % kind)
        else:
            raise GitError("delta chain too long")
        for delta in reversed(chain):
            body = _apply_delta(body, delta)
        return _TYPES[kind], body

    def read_object(self, sha):
        """(type, body) of an object; GitError if missing, corrupt or not the object its name says."""
        kind, body = self._raw(sha)
        if hashlib.sha1(b"%s %d\0" % (kind.encode(), len(body)) + body).hexdigest() != sha:
            raise GitError("object %s does not match its name" % sha)
        return kind, body

    def peel_to_commit(self, sha):
        for _ in range(20):
            kind, body = self.read_object(sha)
            if kind == "commit":
                return sha
            if kind != "tag":
                raise GitError("%s is a %s, not a commit" % (sha, kind))
            first = body.split(b"\n", 1)[0].decode("ascii", "replace")
            if not first.startswith("object "):
                raise GitError("tag %s has no object line" % sha)
            sha = first[len("object "):].strip()
        raise GitError("tag chain too long")

    def tree_entries(self, tree_sha):
        kind, body = self.read_object(tree_sha)
        if kind != "tree":
            raise GitError("%s is not a tree" % tree_sha)
        out, pos = [], 0
        while pos < len(body):
            sp = body.index(b" ", pos)
            nul = body.index(b"\0", sp)
            out.append((body[pos:sp].decode(), body[sp + 1:nul].decode("utf-8", "surrogateescape"),
                        body[nul + 1:nul + 21].hex()))
            pos = nul + 21
        return out

    def files_at(self, commit, subdir, exclude=()):
        """{path relative to subdir: (mode, blob sha)} for every file under subdir at commit; None if absent."""
        kind, body = self.read_object(commit)
        if kind != "commit" or not body.startswith(b"tree "):
            raise GitError("%s is not a commit" % commit)
        tree = body[5:45].decode()
        for part in subdir.strip("/").split("/"):
            match = [e for e in self.tree_entries(tree) if e[1] == part and e[0] == "40000"]
            if not match:
                return None
            tree = match[0][2]
        out = {}

        def walk(tree, prefix):
            for mode, name, sha in self.tree_entries(tree):
                rel = prefix + name
                if not prefix and name in exclude:
                    continue
                if mode == "40000":
                    walk(sha, rel + "/")
                elif mode != "160000":  # submodules are not files
                    out[rel] = (mode, sha)

        walk(tree, "")
        return out


# ---------------------------------------------------------------- what the red team asks

def short_head(worktree):
    """First 7 hex of HEAD (what `git rev-parse --short HEAD` prints in a small repo), or None if unreadable."""
    try:
        sha = Repo(worktree).read_ref("HEAD")
    except (GitError, OSError):
        return None
    return sha[:7] if sha else None


def tag_exists(worktree, tag):
    """True if refs/tags/<tag> resolves to an object present in the repo (`git rev-parse -q --verify`)."""
    try:
        r = Repo(worktree)
        sha = r.read_ref("refs/tags/" + tag)
        return bool(sha) and r.has_object(sha)
    except (GitError, OSError):
        return False


def matches_tag(worktree, tag, subdir, exclude=()):
    """True if every file under subdir at the tag is in the working tree with the same bytes and the working tree
    has no extra .py file there (stricter than `git diff`: untracked code is importable code); False if anything
    differs; None if the tag or the repo cannot be read. Top-level names in `exclude` and __pycache__ are skipped."""
    try:
        r = Repo(worktree)
        sha = r.read_ref("refs/tags/" + tag)
        if not sha:
            return None
        frozen = r.files_at(r.peel_to_commit(sha), subdir, exclude)
    except (GitError, OSError, ValueError, IndexError, struct.error, zlib.error):
        return None
    if frozen is None:
        return None
    base = os.path.join(worktree, *subdir.strip("/").split("/"))
    for rel, (mode, blob) in frozen.items():
        path = os.path.join(base, *rel.split("/"))
        try:
            if mode == "120000":
                data = os.readlink(path).encode("utf-8", "surrogateescape")
            elif os.path.islink(path):
                return False
            else:
                with open(path, "rb") as f:
                    data = f.read()
        except OSError:
            return False
        if blob_id(data) != blob:
            return False
    for dirpath, dirnames, filenames in os.walk(base):
        rel_dir = os.path.relpath(dirpath, base)
        dirnames[:] = [d for d in dirnames if d != "__pycache__" and not (rel_dir == "." and d in exclude)]
        for name in filenames:
            rel = name if rel_dir == "." else "/".join(rel_dir.split(os.sep) + [name])
            if name.endswith(".py") and rel not in frozen:
                return False
    return True
