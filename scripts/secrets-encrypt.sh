#!/usr/bin/env bash
# Encrypt the ./secrets directory into a single age-encrypted tarball you can
# safely store / commit. Requires `age` (https://github.com/FiloSottile/age).
#   AGE_RECIPIENT=age1xxxx bash scripts/secrets-encrypt.sh
set -euo pipefail
: "${AGE_RECIPIENT:?set AGE_RECIPIENT to your age public key (age1...)}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
tar -C "$ROOT" --exclude='secrets/.gitignore' --exclude='secrets/README.md' \
    -czf - secrets | age -r "$AGE_RECIPIENT" > "$ROOT/secrets.tar.age"
echo "Wrote secrets.tar.age (encrypted). Keep your age PRIVATE key off this host."
