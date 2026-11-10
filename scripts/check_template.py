#!/usr/bin/env python3
"""Render the template with sample answers and check what it renders — no server, no cluster.

    python3 scripts/check_template.py [--copier PATH]

For each set of answers below (host access on and off): `copier copy` into a temporary directory, then on the result
  * no Copier marker is left (`[[` / `[%` outside the files that are bash),
  * yamllint with the rendered repository's own .yamllint.yaml,
  * `kustomize build` of the root's gitops/apps, of Argo CD's install and of the system-upgrade install, and of the
    Gateway API CRDs at the commit the Application pins,
  * `helm template` of every chart an Application pins by digest (cert-manager, Traefik), with its values file,
  * `ansible-playbook --syntax-check` of both playbooks against the rendered inventory, and ansible-lint when present,
  * Argo CD's NodePorts rendered exactly when host access is on.
Needs copier, yamllint, kustomize, helm and ansible-playbook (with ansible/requirements.yml's collections) on PATH.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANSWERS = {
    "server_address": "server.example.org",
    "admin_user": "admin",
    "admin_ssh_public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyExampleKeyExampleKeyExampleKeyExam",
    "age_recipient": "age1" + "q" * 58,
    "repo_url": "git@example.org:ops/server.git",
}
API_VERSIONS = ["--api-versions", "gateway.networking.k8s.io/v1", "--api-versions",
                "gateway.networking.k8s.io/v1/GatewayClass", "--api-versions", "cert-manager.io/v1",
                "--api-versions", "cert-manager.io/v1/Issuer"]
failures: list[str] = []
LINT = True


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {label}" + (f" — {detail[-1500:]}" if detail and not ok else ""), flush=True)
    if not ok:
        failures.append(label)


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def render(copier: str, out: Path, host_access: bool) -> None:
    cmd = [copier, "copy", "--trust", "--defaults", "--quiet", str(ROOT), str(out), "-d", f"host_access={host_access}"]
    for key, value in ANSWERS.items():
        cmd += ["-d", f"{key}={value}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"copier copy failed: {result.stderr[-2000:]}")


def chart_refs(repo: Path) -> list[tuple[str, str, Path]]:
    """(name, oci://…@sha256:…, values file) for every Application that pins a chart by digest."""
    found = []
    for app in sorted((repo / "gitops/apps").glob("*/application.yaml")):
        m = re.search(r"repoURL: (oci://\S+)\n(?:\s*#[^\n]*\n)*\s+targetRevision: (sha256:[0-9a-f]{64})", app.read_text())
        values = app.parent / "values.yaml"
        if m and values.is_file():
            found.append((app.parent.name, f"{m.group(1)}@{m.group(2)}", values))
    return found


def check_repo(repo: Path, host_access: bool) -> None:
    tag = f"host_access={'on' if host_access else 'off'}"
    left = [str(p.relative_to(repo)) for p in repo.rglob("*") if p.is_file() and p.suffix != ".sh"
            and re.search(r"\[\[|\[%", p.read_text(errors="replace"))]
    check(f"{tag}: no Copier marker left", not left, ", ".join(left))
    check(f"{tag}: .copier-answers.yml records the answers",
          (repo / ".copier-answers.yml").is_file() and "server.example.org" in (repo / ".copier-answers.yml").read_text())
    result = run(["yamllint", "-c", ".yamllint.yaml", "-s", "."], repo)
    check(f"{tag}: yamllint", result.returncode == 0, result.stdout + result.stderr)
    for path in ("gitops/apps", "gitops/apps/argocd/install", "gitops/apps/system-upgrade/install"):
        result = run(["kustomize", "build", path], repo)
        check(f"{tag}: kustomize build {path}", result.returncode == 0, result.stderr)
        if path == "gitops/apps/argocd/install":
            nodeports = "nodePort: 30443" in result.stdout
            check(f"{tag}: Argo CD's NodePort rendered exactly when host access is on", nodeports == host_access)
    rev = re.search(r"(?m)^\s*targetRevision: ([0-9a-f]{40})\s*$", (repo / "gitops/apps/gateway-api/application.yaml").read_text())
    result = run(["kustomize", "build", f"https://github.com/kubernetes-sigs/gateway-api//config/crd?ref={rev.group(1)}"], repo)
    check(f"{tag}: the Gateway API CRDs at {rev.group(1)[:12]}", result.returncode == 0 and "kind: CustomResourceDefinition"
          in result.stdout, result.stderr)
    for name, ref, values in chart_refs(repo):
        result = run(["helm", "template", name, ref, "-n", name, "-f", str(values), *API_VERSIONS], repo)
        check(f"{tag}: helm template {name} ({ref.rsplit('@', 1)[1][:19]}…)", result.returncode == 0, result.stderr)
    # The pinned collections, where ansible.cfg looks for them (ansible/collections, gitignored in a real repository).
    result = run(["ansible-galaxy", "collection", "install", "-r", "requirements.yml", "-p", "collections"], repo / "ansible")
    check(f"{tag}: ansible-galaxy installs ansible/requirements.yml", result.returncode == 0, result.stderr)
    for playbook in ("playbooks/bootstrap.yml", "playbooks/server.yml"):
        result = run(["ansible-playbook", "--syntax-check", "-i", "inventory/hosts.yml", playbook], repo / "ansible")
        check(f"{tag}: ansible-playbook --syntax-check {playbook}", result.returncode == 0, result.stdout + result.stderr)
    if LINT and shutil.which("ansible-lint"):
        result = subprocess.run(["ansible-lint", "--offline", "-q"], cwd=repo / "ansible", capture_output=True, text=True,
                                env={**os.environ, "ANSIBLE_COLLECTIONS_PATH": str(repo / "ansible" / "collections")})
        check(f"{tag}: ansible-lint", result.returncode == 0, result.stdout + result.stderr)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--copier", default=shutil.which("copier") or "copier")
    p.add_argument("--no-lint", action="store_true", help="skip ansible-lint (a local one on an unsupported Python)")
    args = p.parse_args()
    global LINT
    LINT = not args.no_lint
    with tempfile.TemporaryDirectory(prefix="veyq-server-check-") as tmp:
        for host_access in (True, False):
            out = Path(tmp) / f"rendered-{host_access}"
            render(args.copier, out, host_access)
            check_repo(out, host_access)
    print(f"\nveyq-server template check {'FAILED: ' + str(len(failures)) if failures else 'OK'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
