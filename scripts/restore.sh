#!/usr/bin/env bash
set -euo pipefail
DUMP="${1:?usage: restore.sh <dump.sql>}"
docker compose up -d postgres
until docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-n8n}"; do sleep 1; done
cat "$DUMP" | docker compose exec -T postgres psql -U "${POSTGRES_USER:-n8n}" "${POSTGRES_DB:-n8n}"
echo "Restored $DUMP"
