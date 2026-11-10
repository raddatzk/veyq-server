#!/usr/bin/env python3
"""The sha256 of a commit's tree, the way veyqctl recomputes it before Copier reads a release (veyq ADR 0126 decision 6).

    python3 scripts/tree_hash.py <commit>

One line per file of the commit — `<mode> <sha256 of its bytes> <path>`, sorted by path, joined by newlines with a final
newline — and the sha256 of those lines. Not `git archive | sha256sum`: a tar's bytes may differ between git versions,
and the verifier runs whatever git the operator has. Standard library only, Python 3.9.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys


def tree_sha256(commit: str, cwd: str = ".") -> str:
    listing = subprocess.run(["git", "ls-tree", "-r", "-z", commit], cwd=cwd, capture_output=True, check=True).stdout
    lines = []
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        meta, path = entry.split(b"\t", 1)
        mode, kind, obj = meta.split(b" ")
        if kind != b"blob":
            continue
        data = subprocess.run(["git", "cat-file", "blob", obj.decode()], cwd=cwd, capture_output=True, check=True).stdout
        lines.append(b"%s %s %s" % (mode, hashlib.sha256(data).hexdigest().encode(), path))
    return hashlib.sha256(b"\n".join(sorted(lines, key=lambda l: l.split(b" ", 2)[2])) + b"\n").hexdigest()


if __name__ == "__main__":
    print(tree_sha256(sys.argv[1] if len(sys.argv) > 1 else "HEAD"))
