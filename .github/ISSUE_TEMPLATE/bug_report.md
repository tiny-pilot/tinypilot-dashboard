---
name: Bug report
about: Report a problem in the TinyPilot Dashboard alpha
title: ''
labels: bug
assignees: ''
---

## What happened

A clear, brief description of what went wrong.

## What you expected to happen

What you thought would happen instead.

## Steps to reproduce

1.
2.
3.

## Environment

- **Dashboard version:** (see the version badge next to the logo in the UI, or `curl http://localhost:8080/api/version`)
- **TinyPilot firmware:** (any one device is fine; "Settings → About" in TinyPilot)
- **Number of devices on dashboard:**
- **Streaming mode in use:** H.264 / MJPEG / mixed
- **Host OS:** (e.g. Ubuntu 24.04, macOS 14.5, Windows 11 + WSL2)
- **Docker version:** `docker --version`
- **Deployment perimeter:** LAN-only / perimeter VPN / zero-trust overlay (Tailscale, etc.)

## Logs

Output of `docker compose logs --tail=200 dashboard` (redact anything sensitive — device URLs and API tokens can usually stay out):

```
```

## Anything else

Screenshots, network notes, or other context.
