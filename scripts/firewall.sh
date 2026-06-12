#!/usr/bin/env bash
# Lock the host firewall to SSH-only. n8n (5678) and worker (8000) are bound to
# 127.0.0.1, so reach them via an SSH tunnel, never the public interface.
set -euo pipefail
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
# If you run the optional caddy proxy with a real domain, also:
#   sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status verbose
echo "Inbound limited to SSH. Tunnel the UI:  ssh -L 5678:localhost:5678 user@server"
