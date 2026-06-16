# Design: TinyPilot Dashboard — DigitalOcean Deployment

**Date:** 2026-05-19  
**Status:** Approved for implementation

---

## Overview

Enable existing TinyPilot customers to deploy the TinyPilot Dashboard on a
DigitalOcean droplet with minimal effort. The droplet runs the dashboard as a
Docker service, secures it with Tailscale, and auto-updates daily from the
public GitHub repository.

Self-hosted local deployment remains a fully supported, first-class option.
DigitalOcean is an additional path for customers who want always-on access
from anywhere on their Tailscale network.

---

## Deliverables

1. `deploy/cloud-init.yaml` — user-data script pasted into DigitalOcean droplet creation
2. Systemd timer unit (embedded in cloud-init) — auto-updates the dashboard daily
3. README updates — new "Deploy on DigitalOcean" and "Run locally" sections replacing the existing flat "Install" section

---

## Droplet sizing

One cloud-init script works on any Ubuntu droplet. Customers choose their own
size; there are no locked tiers. Recommended sizes:

| Use case | Size | Cost |
|---|---|---|
| Dashboard only, light use | `s-1vcpu-1gb` | $6/mo |
| Dashboard only, comfortable | `s-1vcpu-2gb` | $12/mo (recommended) |
| Dashboard + heavier polling | `s-2vcpu-4gb` | $24/mo |
| Dashboard + AI agent (Cursor/Claude Code) | `s-4vcpu-8gb` | $48/mo |

Note: The $6/mo tier works but the first-boot Docker image build may be slow
due to limited RAM. All tiers run identical software. Droplets can be resized
in the DigitalOcean control panel at any time without data loss.

---

## Cloud-init script (`deploy/cloud-init.yaml`)

Runs once on first boot. Steps in order:

1. Update Ubuntu packages
2. Install Docker Engine + Docker Compose plugin (official Docker apt repo)
3. Clone `https://github.com/tiny-pilot/tinypilot-dashboard.git` to `/opt/tinypilot-dashboard/`
4. Build and start the dashboard: `docker compose up -d --build`
6. Configure `ufw`: allow OpenSSH, enable ufw (default deny incoming). Port 8080 is never opened.
7. **If `TAILSCALE_AUTH_KEY` is set:**
   - Install Tailscale via official install script
   - Authenticate: `tailscale up --authkey=$TAILSCALE_AUTH_KEY --ssh`
   - Enable Tailscale Serve: `tailscale serve --bg http://localhost:8080`
   - Dashboard is now accessible at `https://<machine-name>.<tailnet>.ts.net` — Tailscale peers only, HTTPS with valid certificate
8. **If `TAILSCALE_AUTH_KEY` is empty:** skip Tailscale entirely. Dashboard is localhost-only; access via SSH tunnel.
9. Install systemd auto-update timer (see below)

The `TAILSCALE_AUTH_KEY` variable appears at the top of the script as a
clearly labeled blank. Customers paste in their key or leave it empty.

### Security posture

- `ufw` allows SSH only. Port 8080 is never exposed on the public internet in
  either path.
- **With Tailscale:** `tailscale serve` proxies localhost:8080 onto the
  Tailscale interface with automatic HTTPS. No firewall rules needed beyond
  the default deny.
- **Without Tailscale:** dashboard is reachable only via SSH tunnel
  (`ssh -L 8080:localhost:8080 user@droplet-ip`). Customers who choose this
  path are directed to DigitalOcean's
  [Initial Server Setup guide](https://www.digitalocean.com/community/tutorials/initial-server-setup-with-ubuntu)
  for additional hardening. No further security guidance is maintained in this
  repo.
- Docker socket is NOT mounted. No container-to-host privilege escalation.

---

## Auto-update

A systemd timer unit (`tinypilot-dashboard-update.timer`) runs daily at 3am:

```bash
cd /opt/tinypilot-dashboard
git pull
docker compose up -d --build
```

`git pull` is a no-op if no new commits exist — no unnecessary restarts.
When new code is pulled, the container rebuilds and restarts (~30s downtime).

**Data persistence:** `data/` is bind-mounted from the host at
`/opt/tinypilot-dashboard/data/`. Device records, credentials, and
`secret.key` survive every update. Customers never need to re-add their
devices after an update.

**No UI surface for updates.** The existing version badge (`v0.1.x`) in the
topbar is sufficient for bug report reference. Auto-update is silent and
invisible to the customer. This will be revisited for beta when manual update
control may be reintroduced.

---

## README structure changes

The existing flat `## Install` section is replaced with two parallel sections:

### `## Deploy on DigitalOcean`
- When to choose this path (always-on, Tailscale network access)
- Sizing recommendations table
- Step-by-step: create Ubuntu 24.04 droplet, paste cloud-init script into
  User Data field, click Create
- The cloud-init script as a copyable code block with `TAILSCALE_AUTH_KEY=""`
  at the top
- Tailscale note: strongly recommended; link to Tailscale's [auth key docs](https://tailscale.com/kb/1085/auth-keys) for generating a key; link to DO hardening guide for those who skip it

### `## Run locally`
- When to choose this path (LAN use, machine already on the network)
- Existing `docker compose up -d` steps, unchanged

Both sections are presented without hierarchy — different use cases, same product.

---

## Out of scope

- Published Docker image / registry (Path B distribution): future work; will
  eliminate the first-boot build step and make the $6/mo tier more reliable
- DigitalOcean Marketplace 1-click app: post-alpha; requires vendor application
  (~4–8 weeks). The cloud-init script doubles as the basis for a Marketplace
  submission when ready.
- Manual update button in the UI: deferred to beta. Auto-update is sufficient
  for alpha.
- Multi-user auth on the dashboard: separate workstream, not in scope here.
