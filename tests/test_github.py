"""Tests for the GitHub source (hermetic: a local HTTP server stands in for
codeload.github.com, so no network access is needed). Stdlib only."""
import asyncio
import os
import sys
import tarfile
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, ".")

from makemcp.convert import (
    _is_test_path,
    app_from_tree,
    detect_kind,
    download_tarball,
    parse_github_target,
)

# 1) URL parsing -------------------------------------------------------------
assert parse_github_target("https://github.com/psf/requests") == \
    {"owner": "psf", "repo": "requests", "ref": None, "subdir": ""}
assert parse_github_target("https://github.com/o/r.git")["repo"] == "r"
assert parse_github_target("https://github.com/o/r/tree/dev/pkg") == \
    {"owner": "o", "repo": "r", "ref": "dev", "subdir": "pkg"}
assert parse_github_target("o/r") == \
    {"owner": "o", "repo": "r", "ref": None, "subdir": ""}
assert parse_github_target("o/r@v2")["ref"] == "v2"
for bad in ("not-a-repo", "https://example.com/o/r", "", "a/b/c"):
    try:
        parse_github_target(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"should reject: {bad!r}")
assert detect_kind("https://github.com/psf/requests") == "github"
assert detect_kind("psf/requests") == "github"
assert detect_kind("app.py") == "python"
print("1) parsing + detection OK")

assert _is_test_path("tests/test_x.py") and _is_test_path("pkg/x_test.py")
assert _is_test_path("conftest.py") and not _is_test_path("pkg/core.py")
print("2) test-path filter OK")

# 2) Fake repo tarball in codeload layout ------------------------------------
work = tempfile.mkdtemp(prefix="mkgh-")
repo = os.path.join(work, "fakelib-main")
os.makedirs(os.path.join(repo, "fakelib"))
os.makedirs(os.path.join(repo, "tests"))


def _w(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


_w(os.path.join(repo, "fakelib", "__init__.py"), "X = 1\n")
_w(os.path.join(repo, "fakelib", "core.py"),
   'def add(a: int, b: int) -> int:\n    """Add."""\n    return a + b\n')
_w(os.path.join(repo, "top.py"),
   'def shout(t: str) -> str:\n    return t.upper()\n')
_w(os.path.join(repo, "tests", "test_core.py"), "def test_add(): pass\n")
_w(os.path.join(repo, "broken.py"), "def oops(:\n")

tgz = os.path.join(work, "repo.tar.gz")
with tarfile.open(tgz, "w:gz") as tar:
    tar.add(repo, arcname="fakelib-main")


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        with open(tgz, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = ThreadingHTTPServer(("127.0.0.1", 8972), _H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

# 3) Download + safe extract + convert ---------------------------------------
dest = os.path.join(work, "extracted")
download_tarball("http://127.0.0.1:8972/repo.tar.gz", dest)
assert os.path.isfile(os.path.join(dest, "fakelib", "core.py")), os.listdir(dest)

converted = app_from_tree(dest, "fake")
names = sorted(converted._tools)
# fakelib/__init__ has no functions; tests/ and broken.py are skipped
assert names == ["fakelib_core_add", "top_shout"], names
assert asyncio.run(converted.call_tool("fakelib_core_add",
                                       {"a": 2, "b": 3})) == 5

with_tests = app_from_tree(dest, "fake2", include_tests=True)
assert any(n.startswith("test") or "test_core" in n
           for n in with_tests._tools), sorted(with_tests._tools)
srv.shutdown()
print("3) download + extract + convert OK:", names)

# 4) Traversal attack blocked -------------------------------------------------
import io
import urllib.request

evil = os.path.join(work, "evil.tar.gz")
with tarfile.open(evil, "w:gz") as tar:
    info = tarfile.TarInfo("../../evil.py")
    data = b"EVIL = 1\n"
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))
file_url = "file:" + urllib.request.pathname2url(evil)
try:
    download_tarball(file_url, os.path.join(work, "evil-out"))
except ValueError as e:
    assert "unsafe" in str(e), e
else:
    raise AssertionError("path traversal was not blocked")
assert not os.path.exists(os.path.join(work, "evil.py"))
assert not os.path.exists(os.path.join(os.path.dirname(work), "evil.py"))
print("4) traversal blocked OK")

print("ALL GITHUB TESTS PASSED")
