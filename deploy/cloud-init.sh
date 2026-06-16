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
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-${VERSION_CODENAME}}") stable" \
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
set -x

readonly INSTALL_DIR="/opt/tinypilot-dashboard"

cd "${INSTALL_DIR}"
git pull --ff-only
docker compose up --detach --build
EOF
chmod 0755 "${UPDATE_SCRIPT}"

# Install a systemd service and daily timer that auto-update the dashboard.
cat > "${UPDATE_SERVICE}" << 'EOF'
[Unit]
Description=TinyPilot Dashboard auto-update
Wants=network-online.target
After=network-online.target

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
  tailscale serve --bg http://localhost:8080
fi
