#!/usr/bin/env bash
# One-time: create a file-backed LUKS volume and mount it at $DATA_DIR.
# Vars: DATA_DIR (mount point, default /mnt/agentdata), LUKS_IMG, LUKS_SIZE.
# You'll be asked for a passphrase — that passphrase IS the at-rest protection.
set -euo pipefail
DATA_DIR="${DATA_DIR:-/mnt/agentdata}"
IMG="${LUKS_IMG:-$HOME/agentdata.img}"
SIZE="${LUKS_SIZE:-5G}"
MAP="agentdata"

if [ ! -f "$IMG" ]; then
  echo "Creating $SIZE image at $IMG ..."
  fallocate -l "$SIZE" "$IMG"
  echo "Formatting LUKS (choose a strong passphrase) ..."
  sudo cryptsetup luksFormat "$IMG"
fi

sudo cryptsetup open "$IMG" "$MAP"
sudo blkid "/dev/mapper/$MAP" >/dev/null 2>&1 || sudo mkfs.ext4 "/dev/mapper/$MAP"
sudo mkdir -p "$DATA_DIR"
mountpoint -q "$DATA_DIR" || sudo mount "/dev/mapper/$MAP" "$DATA_DIR"
sudo chown -R "$USER" "$DATA_DIR"
mkdir -p "$DATA_DIR/postgres" "$DATA_DIR/n8n"
sudo chown -R 1000:1000 "$DATA_DIR/n8n"   # n8n container runs as uid 1000 (node)
echo "LUKS volume ready at $DATA_DIR. Set DATA_DIR=$DATA_DIR in .env BEFORE the first 'make harden-up'."
echo "After a reboot, run 'make luks-open' before 'make harden-up'."
