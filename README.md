# TinyPilot Dashboard

A self-hosted dashboard for monitoring and controlling multiple TinyPilot devices from a single screen. Runs locally on your own hardware in a Docker container — no cloud account, no telemetry.

> **Alpha software.** This release is intended for existing TinyPilot customers to evaluate on a trusted network. It does **not** authenticate inbound users. Please read [Deployment & security](#deployment--security) before installing.
>
> **About this build.** The TinyPilot Dashboard was developed with significant AI-assisted code generation. It has been reviewed and tested for the alpha; the goal of this release is to put it in front of real deployments so we can find and fix anything our review missed. Bug reports are very welcome.
>
> **Direct support for TinyPilot Dashboard is limited during the alpha.** Please file bugs and feedback as [GitHub issues](https://github.com/tiny-pilot/tinypilot-dashboard/issues). TinyPilot's regular product support is unaffected — use your usual support channel for product or deployment questions.

## What you get

- One web UI that lists your TinyPilot devices, up to four per page, with a live screenshot of the connected system on each card.
- One-click device addition (friendly name + TinyPilot URL).
- Per-device snapshot of TinyPilot status: connected display resolution, streaming mode (H.264 with bitrate, or MJPEG with framerate and quality), firmware version, network info, and more.
- Encrypted at-rest storage for device credentials and tokens.

## Requirements

- A host that can already reach your TinyPilot devices over LAN, VPN, or a private overlay. The dashboard does **not** create that connectivity for you.
- [Docker](https://docs.docker.com/get-docker/) and Docker Compose.
- A [TinyPilot Automation License](https://tinypilotkvm.com/pages/automation) on each device — required for the live and on-demand screenshots the dashboard displays.
- A modern browser (Chrome, Firefox, Safari, or Edge).

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

## Adding a device

1. Click **Add a device**.
2. Enter a friendly name (e.g. "Rack A KVM") and the TinyPilot URL (e.g. `https://tinypilot-rack-a.local` or `https://192.168.1.50`).
3. Save. The dashboard will pull a live screenshot and TinyPilot status.

**Alpha limitation:** this release supports TinyPilot devices whose Web UI is **not** protected by a username/password. Username/password support is planned for a future release.

## Deployment & security

The dashboard is designed to live **inside a network perimeter you already trust**. It does not authenticate inbound users and does not implement CSRF protection on its API; the deployment boundary *is* the security boundary.

### Deploy behind a trusted perimeter — pick one

- **LAN only** — run it on a host inside the same network as your TinyPilot devices, and never port-forward `8080` to the public internet.
- **Perimeter VPN** — reach the dashboard over your existing site-to-site or client VPN.
- **Zero-trust overlay** — expose it only via an identity-aware overlay such as [Tailscale](https://tailscale.com/), Twingate, or Cloudflare Tunnel + Access.

If none of those apply to your environment, please **do not run this alpha**.

### What this means in practice

- Anyone who can reach `http://<host>:8080` can add, delete, and snapshot devices. Treat reachability to the dashboard as equivalent to administrative access.
- TinyPilot devices ship with self-signed TLS certificates. The dashboard intentionally skips certificate verification when talking to them so it works out of the box; the perimeter requirement above bounds the resulting risk.
- Device credentials and tokens are encrypted on disk. Host filesystem permissions and full-disk encryption are your last line of defense — protect the host accordingly.

## Data and backup

Everything persistent lives in `./data`:

- `dashboard.sqlite` — devices and encrypted credentials.
- `screenshots/` — latest screenshot per device.
- `secret.key` — the encryption key for the SQLite secrets.

**To back up: copy the entire `data/` directory.** `secret.key` must be backed up alongside `dashboard.sqlite` — without it the encrypted columns cannot be recovered.

## Troubleshooting

- **Old UI after an update.** Hard-refresh the browser (Cmd-Shift-R / Ctrl-Shift-R). If it persists, run `docker compose down && docker compose up -d`.
- **A device can't be reached.** Confirm the host running the dashboard can resolve and reach the TinyPilot URL directly — for example, `curl -k https://<tinypilot-url>` from the host.
- **`.local` / mDNS names don't resolve inside Docker.** Use an IP address or a DNS name that resolves from inside the container.
- **Self-signed certificate warnings in logs.** Expected; the dashboard skips verification when talking to TinyPilot devices (see [Deployment & security](#deployment--security)).

## License

MIT licensed — see [`LICENSE`](LICENSE) and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

---

## Architecture

Source layout and conventions for anyone reading the code or auditing what the dashboard does on the network. Skip this section if you only intend to *run* the dashboard. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for how feedback and bug reports are handled during the alpha.

### Repository layout

**Frontend** (`app/static/`, `app/templates/`)

- `templates/index.html` — Jinja shell that loads the `<dashboard-app>` web component and static assets.
- `static/js/dashboard-app.js` — root custom element with shadow DOM: top bar, theme toggle, Add-a-device modal, paging (four devices per page), and the device grid (`device-grid--n1` … `device-grid--n4`, one column per visible device).
- `static/js/components/device-card.js` — one custom element per TinyPilot target. Owns the screenshot controls and the collapsed/expanded TinyPilot snapshot panel.
- `static/js/lib/` — shared helpers (`strings.js`, `snapshot-view.js`).
- `static/js/api.js` — thin `fetch` wrappers attached to `window.dashboardApi`.

**Backend** (`app/`)

- `__init__.py` — Flask app factory.
- `api.py` — `/api/*` blueprint and route handlers.
- `db.py` — SQLite connection helper and schema bootstrap.
- `tinypilot_client.py` — HTTP client wrapping TinyPilot's Automation and Web UI JSON endpoints.
- `resolution.py` — normalizers for the various shapes TinyPilot uses to report "connected device resolution".
- `snapshot_service.py` — atomic latest-screenshot writer.
- `auth_store.py`, `crypto.py` — Fernet-encrypted at-rest secrets.

### TinyPilot APIs the dashboard uses

- **[TinyPilot REST API](https://tinypilotkvm.com/pages/tinypilot-rest-api)** (`/api/v1/*`, Bearer auth) — used to refresh automation tokens and fetch screenshots. Requires a [TinyPilot Automation License](https://tinypilotkvm.com/pages/automation) on the device.
- **Web UI JSON** (`/api/*`) — used to read device snapshot fields (version, network, video settings, etc.) via the same session the in-browser TinyPilot app uses.

