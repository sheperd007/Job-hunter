#!/usr/bin/env bash
# After a reboot: unlock + mount the existing LUKS volume before `make harden-up`.
# Vars: DATA_DIR (default /mnt/agentdata), LUKS_IMG.
set -euo pipefail
DATA_DIR="${DATA_DIR:-/mnt/agentdata}"
IMG="${LUKS_IMG:-$HOME/agentdata.img}"
MAP="agentdata"

[ -e "/dev/mapper/$MAP" ] || sudo cryptsetup open "$IMG" "$MAP"
mountpoint -q "$DATA_DIR" || { sudo mkdir -p "$DATA_DIR"; sudo mount "/dev/mapper/$MAP" "$DATA_DIR"; }
sudo chown -R "$USER" "$DATA_DIR"
mkdir -p "$DATA_DIR/postgres" "$DATA_DIR/n8n"
mountpoint -q "$DATA_DIR" && echo "Mounted $DATA_DIR — safe to run 'make harden-up'."
