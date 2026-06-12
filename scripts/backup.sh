#!/usr/bin/env bash
set -euo pipefail
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p backups
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-n8n}" "${POSTGRES_DB:-n8n}" > "backups/db-$STAMP.sql"
echo "Wrote backups/db-$STAMP.sql"
echo "To migrate: copy this dump + your .env to the new host, then: make restore DUMP=backups/db-$STAMP.sql && make up"
