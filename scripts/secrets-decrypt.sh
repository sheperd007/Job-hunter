#!/usr/bin/env bash
# Materialize ./secrets/* from the encrypted tarball at deploy time.
#   AGE_KEY_FILE=~/age-key.txt bash scripts/secrets-decrypt.sh
# Tip: keep the age key OFF the server (paste it, decrypt, then `shred` it).
set -euo pipefail
: "${AGE_KEY_FILE:?set AGE_KEY_FILE to your age private key file}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
age -d -i "$AGE_KEY_FILE" "$ROOT/secrets.tar.age" | tar -C "$ROOT" -xzf -
chmod 700 "$ROOT/secrets"
chmod 600 "$ROOT"/secrets/* 2>/dev/null || true
echo "Materialized ./secrets/* (chmod 600)."
