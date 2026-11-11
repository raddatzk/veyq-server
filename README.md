# veyq-server

Sets up a server and its Kubernetes cluster for [veyq](https://github.com/raddatzk/veyq), as a repository you own:
Ansible for the machine (an admin user, a hardened sshd, a host firewall that keeps the Kubernetes API and every
NodePort off the public interface, unattended upgrades, k3s, Argo CD with KSOPS), and Argo CD applications for the
cluster (Argo CD itself, the Gateway API CRDs, Traefik, cert-manager, the system-upgrade-controller).

You do not run anything here by hand. `veyqctl init` (veyq's own tool) asks whether to set up the server, renders this
template into your repository with [Copier](https://copier.readthedocs.io/) — from a **release** whose manifest it
verifies first, never from a branch: the template runs Ansible as root on your server — generates its secrets, runs the
bootstrap, and then writes veyq's own half beside it (veyq ADR 0126). The Run area of veyq's docs says how.

## The server it needs

A freshly installed **Debian 13 (trixie)** server — the platform every role's `meta/main.yml` names, and the only one
the playbooks are written for — reachable as root over SSH with your key. 8 GB of memory (4 GB is tight); the
provider's firewall open for TCP 22, 80 and 443 only. Anything else (another distribution, another release) is not
supported until a role says so.

## What is here

| Path | What it is |
|---|---|
| `copier.yml` | The questions `veyqctl init` answers: the server's address, the node name, the admin user and SSH key, the age key, the repository URL and branch, the Argo CD project, host access. Never a secret. |
| `template/` | What is rendered into your repository. Copier's markers are `[[ … ]]` and `[% … %]`, since the files are Ansible and Kubernetes YAML full of `{{ … }}`. |
| `scripts/check_template.py` | Renders the template with sample answers (host access on and off) and checks the result: yamllint, `kustomize build`, `helm template` of every pinned chart, the Ansible syntax check and ansible-lint. `.github/workflows/checks.yml` runs it on every push. |
| `scripts/tree_hash.py` | The sha256 of a commit's tree, as `veyqctl` recomputes it before rendering. |
| `.github/workflows/release.yml` | A release, by hand on `main`: `veyq-server-manifest.json` (release, commit, tree sha256) signed keylessly by this workflow, on an immutable GitHub Release. |

## Releases

`v<major>.<minor>`: `VERSION` holds the major; the minor counts the commits since `VERSION` last changed. `veyqctl`
verifies `veyq-server-manifest.json` against its bundle under the identity
`https://github.com/raddatzk/veyq-server/.github/workflows/release.yml@refs/heads/main` (GitHub's OIDC issuer), checks
out the commit it names, recomputes the tree sha256, and only then lets Copier read it.

## Working on the template

```sh
python3 scripts/check_template.py            # needs copier, yamllint, kustomize, helm, ansible-core, ansible-lint
python3 scripts/check_template.py --no-lint  # where the local ansible-lint runs on a Python ansible-core does not support
```
