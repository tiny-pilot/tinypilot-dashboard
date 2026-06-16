# DigitalOcean Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a single cloud-init bash script customers paste into DigitalOcean droplet creation, which installs Docker, clones the repo, starts the dashboard, configures the firewall, optionally joins Tailscale, and enables a daily auto-update timer.

**Architecture:** A standalone bash script (`deploy/cloud-init.sh`) is the only new file. It is pasted by the customer into DigitalOcean's User Data field at droplet creation. The script runs once on first boot as root. All infrastructure knowledge lives in this file; the Flask app and Docker Compose config are unchanged.

**Tech Stack:** Bash (Google Shell style + TinyPilot conventions), Docker Compose, `ufw`, `systemd`, Tailscale CLI, GitHub Actions (ShellCheck).

---

## Style constraints (TinyPilot shell conventions)

Apply these throughout `deploy/cloud-init.sh` and any embedded scripts:

- `set -e`, `set -u`, `set -x` at the top of every bash script.
- Long flag names: `--yes` not `-y`, `--detach` not `-d`, `--quiet` not `-q`.
- `UPPERCASE` constants declared with `readonly` just before first use.
- Comments: capital first letter, trailing period.
- `(( ... ))` for numerical comparisons.
- Here-documents use `EOF` as the delimiter.
- Error messages to `>&2 echo`; no "ERROR:" prefix; sentence casing; no trailing punctuation.
- ShellCheck must pass with no warnings.

---

## File map

| Action | Path | Purpose |
|---|---|---|
| Create | `deploy/cloud-init.sh` | User-data script for DigitalOcean droplet creation |
| Create | `.github/workflows/shellcheck.yml` | CI: lint all shell scripts on every push/PR |
| Modify | `README.md` | Replace flat `## Install` with `## Deploy on DigitalOcean` + `## Run locally` |

---

## Task 1: Create `deploy/cloud-init.sh`

**Files:**
- Create: `deploy/cloud-init.sh`

- [ ] **Step 1: Create the deploy/ directory and write the script**

```bash
mkdir deploy
```

Write `deploy/cloud-init.sh` with the following exact content:

```bash
#!/bin/bash

# TinyPilot Dashboard setup script for DigitalOcean.
# Paste the contents of this file into the "User Data" field when creating
# a DigitalOcean Ubuntu 24.04 droplet (Advanced Options → User Data).
#
# To enable Tailscale (strongly recommended), set TAILSCALE_AUTH_KEY to a
# reusable auth key. Generate one at:
# https://login.tailscale.com/admin/settings/keys
#
# With Tailscale:    dashboard accessible at https://<name>.<tailnet>.ts.net
# Without Tailscale: dashboard accessible via SSH tunnel only
#                    (ssh -L 8080:localhost:8080 root@<droplet-ip>)

set -e
set -u
set -x

# Set your Tailscale auth key here. Leave blank to skip Tailscale setup.
TAILSCALE_AUTH_KEY=""
readonly TAILSCALE_AUTH_KEY

readonly INSTALL_DIR="/opt/tinypilot-dashboard"
readonly UPDATE_SCRIPT="/usr/local/bin/tinypilot-dashboard-update"
readonly UPDATE_SERVICE="/etc/systemd/system/tinypilot-dashboard-update.service"
readonly UPDATE_TIMER="/etc/systemd/system/tinypilot-dashboard-update.timer"

# Install Docker Engine from the official Docker apt repository.
apt-get update --quiet
apt-get install \
  --yes \
  --quiet \
  ca-certificates \
  curl \
  git
install --mode=0755 --directory /etc/apt/keyrings
curl \
  --fail \
  --silent \
  --show-error \
  --location \
  --output /etc/apt/keyrings/docker.asc \
  https://download.docker.com/linux/ubuntu/gpg
chmod a+r /etc/apt/keyrings/docker.asc
# shellcheck disable=SC1091
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update --quiet
apt-get install \
  --yes \
  --quiet \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

# Clone the dashboard repository and build the Docker image.
git clone https://github.com/tiny-pilot/tinypilot-dashboard.git "${INSTALL_DIR}"
cd "${INSTALL_DIR}"
docker compose up --detach --build

# Write the update script that customers can run manually or that the
# systemd timer invokes each night.
cat > "${UPDATE_SCRIPT}" << 'EOF'
#!/bin/bash

# Updates TinyPilot Dashboard to the latest version from GitHub.
# The dashboard is unavailable for approximately 30 seconds while the new
# image builds.

set -e
set -u

readonly INSTALL_DIR="/opt/tinypilot-dashboard"

cd "${INSTALL_DIR}"
git pull
docker compose up --detach --build
EOF
chmod 0755 "${UPDATE_SCRIPT}"

# Install a systemd service and daily timer that auto-update the dashboard.
cat > "${UPDATE_SERVICE}" << 'EOF'
[Unit]
Description=TinyPilot Dashboard auto-update

[Service]
Type=oneshot
ExecStart=/usr/local/bin/tinypilot-dashboard-update
EOF

cat > "${UPDATE_TIMER}" << 'EOF'
[Unit]
Description=TinyPilot Dashboard daily auto-update timer

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now tinypilot-dashboard-update.timer

# Configure ufw: allow SSH, block everything else. Port 8080 is never
# opened on the public internet regardless of Tailscale choice.
ufw allow OpenSSH
ufw --force enable

# Set up Tailscale if an auth key was provided.
if [[ -n "${TAILSCALE_AUTH_KEY}" ]]; then
  curl \
    --fail \
    --silent \
    --show-error \
    --location \
    https://tailscale.com/install.sh \
    | sh
  tailscale up \
    --authkey="${TAILSCALE_AUTH_KEY}" \
    --ssh
  tailscale serve http://localhost:8080
fi
```

- [ ] **Step 2: Make the script executable**

```bash
chmod 0755 deploy/cloud-init.sh
```

- [ ] **Step 3: Run ShellCheck locally to verify no warnings**

```bash
shellcheck deploy/cloud-init.sh
```

Expected: no output (zero warnings, zero errors).

If ShellCheck is not installed:
```bash
brew install shellcheck   # macOS
# or
apt-get install shellcheck  # Ubuntu
```

Common fixes if ShellCheck warns:
- SC2086 (word splitting): quote variables → `"${VAR}"` not `${VAR}`
- SC2046 (word splitting in command substitution): already handled by quoting
- SC1091 (not following sourced file): add `# shellcheck disable=SC1091` above the `/etc/os-release` source line

- [ ] **Step 4: Commit**

```bash
git add deploy/cloud-init.sh
git commit -m "Add DigitalOcean cloud-init setup script"
```

---

## Task 2: Add ShellCheck GitHub Actions workflow

Per TinyPilot style guide: all repositories with shell scripts must run
ShellCheck in CI.

**Files:**
- Create: `.github/workflows/shellcheck.yml`

- [ ] **Step 1: Write the workflow**

Write `.github/workflows/shellcheck.yml`:

```yaml
name: ShellCheck

on:
  push:
  pull_request:

jobs:
  shellcheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run ShellCheck
        uses: ludeeus/action-shellcheck@master
        with:
          scandir: './deploy'
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/shellcheck.yml
git commit -m "Add ShellCheck CI for deploy/ shell scripts"
```

---

## Task 3: Update README.md

Replace the flat `## Install` section with two parallel sections:
`## Deploy on DigitalOcean` and `## Run locally`. Both are first-class
options — no hierarchy, no "recommended" framing.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the `## Install` section**

Find this block in `README.md`:

```markdown
## Install

1. Clone or download this repository.
2. From the repository directory, start the dashboard:

   ```bash
   docker compose up -d
   ```

3. Open **[http://localhost:8080](http://localhost:8080)** in your browser.

To stop the dashboard:

```bash
docker compose down
```

Compose binds to `127.0.0.1:8080` on the host by default, so the UI is reachable only from the machine running it. To expose it to other hosts on your trusted network, see [Deployment & security](#deployment--security).
```

Replace it with:

```markdown
## Deploy on DigitalOcean

For always-on access from anywhere on your Tailscale network, run the
dashboard on a DigitalOcean droplet. All droplet sizes run identical
software — choose based on your workload:

| Use case | Size | Cost |
|---|---|---|
| Dashboard only, light use | `s-1vcpu-1gb` | $6/mo |
| Dashboard only, comfortable | `s-1vcpu-2gb` | $12/mo |
| Dashboard + heavier polling | `s-2vcpu-4gb` | $24/mo |
| Dashboard + AI agent (Cursor/Claude Code) | `s-4vcpu-8gb` | $48/mo |

Droplets can be resized in the DigitalOcean control panel at any time
without data loss.

### Steps

1. [Create a DigitalOcean droplet](https://cloud.digitalocean.com/droplets/new)
   running **Ubuntu 24.04 LTS**.
2. In **Advanced Options → User Data**, paste the contents of
   [`deploy/cloud-init.sh`](deploy/cloud-init.sh) from this repository.
3. At the top of the pasted script, set your Tailscale auth key
   (see below). Leave it blank to skip Tailscale.
4. Click **Create Droplet**. The dashboard starts automatically during
   first boot (~5 minutes).

### Tailscale (strongly recommended)

[Generate a reusable auth key](https://login.tailscale.com/admin/settings/keys)
in your Tailscale admin console, then set it at the top of the
cloud-init script:

```
TAILSCALE_AUTH_KEY="tskey-auth-xxxxxxxx"
```

Once the droplet boots, the dashboard is available at
`https://<machine-name>.<tailnet>.ts.net` — accessible only to devices
on your Tailscale network, with HTTPS provided automatically.

**Without Tailscale:** the dashboard is localhost-only. Access it via
SSH tunnel (`ssh -L 8080:localhost:8080 root@<droplet-ip>`) and open
`http://localhost:8080`. For additional server hardening, see
DigitalOcean's [Initial Server Setup guide](https://www.digitalocean.com/community/tutorials/initial-server-setup-with-ubuntu).

### Updates

The droplet auto-updates the dashboard daily at 3am. No action required.

## Run locally

For running on a machine that is already on the same network as your
TinyPilot devices:

1. Clone or download this repository.
2. From the repository directory, start the dashboard:

   ```bash
   docker compose up -d
   ```

3. Open **[http://localhost:8080](http://localhost:8080)** in your browser.

To stop the dashboard:

```bash
docker compose down
```

Compose binds to `127.0.0.1:8080` on the host by default, so the UI is
reachable only from the machine running it. To expose it to other hosts
on your trusted network, see [Deployment & security](#deployment--security).
```

- [ ] **Step 2: Verify the README renders correctly**

Open `README.md` in a Markdown previewer (GitHub preview or your IDE's
preview) and confirm:

- The sizing table renders correctly.
- The two code blocks (Tailscale auth key, `docker compose up -d`) both
  render as code blocks and are not broken by the surrounding fenced
  code blocks.
- All links resolve (hover to confirm).
- `## Deploy on DigitalOcean` and `## Run locally` appear as sibling
  headings with no visual hierarchy between them.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Add DigitalOcean deployment instructions to README"
```

---

## Task 4: Copy changes to staging repo and verify

The public-facing code lives in the staging repo at
`/Users/shalver/Downloads/tinypilot-dashboard-public/`. Sync the new
files there and verify the tests still pass.

- [ ] **Step 1: Copy new/changed files to the staging repo**

```bash
cp -r \
  /Users/shalver/Downloads/tinypilot-dashboard/.worktrees/poc-dashboard/deploy \
  /Users/shalver/Downloads/tinypilot-dashboard-public/

cp \
  /Users/shalver/Downloads/tinypilot-dashboard/.worktrees/poc-dashboard/.github/workflows/shellcheck.yml \
  /Users/shalver/Downloads/tinypilot-dashboard-public/.github/workflows/

cp \
  /Users/shalver/Downloads/tinypilot-dashboard/.worktrees/poc-dashboard/README.md \
  /Users/shalver/Downloads/tinypilot-dashboard-public/
```

- [ ] **Step 2: Run tests in the staging repo**

```bash
cd /Users/shalver/Downloads/tinypilot-dashboard-public
pytest -q
```

Expected: all 33 tests pass, 1 warning.

- [ ] **Step 3: Run ShellCheck in the staging repo**

```bash
shellcheck /Users/shalver/Downloads/tinypilot-dashboard-public/deploy/cloud-init.sh
```

Expected: no output.

- [ ] **Step 4: Commit and push to GitHub**

```bash
cd /Users/shalver/Downloads/tinypilot-dashboard-public
git add deploy/ .github/workflows/shellcheck.yml README.md
git status   # confirm only expected files are staged
git commit -m "Add DigitalOcean one-droplet deployment"
git push origin master
```

---

## Post-implementation smoke test (manual, on a real droplet)

After the code is pushed, verify the full customer journey:

1. Create a fresh DigitalOcean Ubuntu 24.04 droplet (any size).
2. Paste `deploy/cloud-init.sh` into User Data with a valid Tailscale
   auth key.
3. Wait ~5 minutes after the droplet boots.
4. Confirm the droplet appears in your Tailscale admin console.
5. Open `https://<machine-name>.<tailnet>.ts.net` in a browser — the
   TinyPilot Dashboard should load and show the `v0.1.0` version badge.
6. Add a TinyPilot device and confirm a screenshot loads.
7. Check the auto-update timer is active:
   ```bash
   systemctl status tinypilot-dashboard-update.timer
   ```
   Expected: `active (waiting)`.
8. Verify port 8080 is NOT reachable on the public IP:
   ```bash
   curl --max-time 5 http://<droplet-public-ip>:8080
   ```
   Expected: connection timeout or refused.

---

## Self-review checklist

- [x] `deploy/cloud-init.sh` covers all spec steps: Docker install, git
  clone, docker compose up, update script, systemd timer, ufw, Tailscale.
- [x] Port 8080 is never opened in ufw in either Tailscale or non-Tailscale
  paths.
- [x] Data volume (`/opt/tinypilot-dashboard/data/`) persists across
  auto-updates (bind mount in existing docker-compose.yml is unchanged).
- [x] ShellCheck CI added per TinyPilot style guide requirement.
- [x] README presents both deployment options as equals.
- [x] Sizing table in README matches spec.
- [x] No Docker socket mounted (removed from earlier design iteration).
- [x] All bash follows TinyPilot conventions: `set -e/u/x`, long flags,
  uppercase constants, comments with trailing punctuation.
- [x] No `INTERNAL.md` or `poc` references introduced.
