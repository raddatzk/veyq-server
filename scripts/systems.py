#!/usr/bin/env python3
"""The systems this template sets up: the platforms every role's `meta/main.yml` names, the same in each.

    python3 scripts/systems.py        # prints them as JSON: [{"name": "Debian", "versions": ["trixie"]}, …]

release.yml writes this list into the signed manifest as `systems`, and veyqctl compares a server's /etc/os-release
against it before the bootstrap — so a system is named in one place, the roles' metadata, which ansible-lint already
checks against Galaxy's platform names. Standard library only (the release job installs nothing): the metadata's
`platforms:` block is read by its fixed shape, and check_template.py holds this reading equal to a YAML parser's.
A role that names other platforms than the rest is refused: every role runs on every server.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROLES = ROOT / "template" / "ansible" / "roles"


def platforms(meta: str) -> list[dict]:
    """`galaxy_info.platforms` of one meta/main.yml: each `- name:` with the `- <version>` lines under its `versions:`."""
    block = re.search(r"(?m)^  platforms:\n((?:    .*\n?)*)", meta)
    if not block:
        raise ValueError("no platforms block")
    found: list[dict] = []
    for line in block.group(1).splitlines():
        name = re.fullmatch(r"    - name: (\S+)", line)
        version = re.fullmatch(r"        - (\S+)", line)
        if name:
            found.append({"name": name.group(1), "versions": []})
        elif version and found:
            found[-1]["versions"].append(version.group(1))
        elif line.strip() not in ("versions:", ""):
            raise ValueError(f"unexpected line in platforms: {line!r}")
    return found


def systems(roles: Path = ROLES) -> list[dict]:
    by_role = {meta.parent.parent.name: platforms(meta.read_text()) for meta in sorted(roles.glob("*/meta/main.yml"))}
    if not by_role:
        raise ValueError(f"no role under {roles}")
    first = next(iter(by_role.values()))
    differing = [role for role, p in by_role.items() if p != first]
    if differing:
        raise ValueError(f"roles name different platforms: {', '.join(differing)} differ from {next(iter(by_role))}")
    return first


if __name__ == "__main__":
    try:
        print(json.dumps(systems()))
    except ValueError as e:
        print(f"systems.py: {e}", file=sys.stderr)
        sys.exit(1)
