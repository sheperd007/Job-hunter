DATA_DIR ?= ./data
HARDENED := -f docker-compose.yml -f docker-compose.hardened.yml

.PHONY: up down logs test backup restore proxy-up \
        harden-up harden-down harden-logs secrets-encrypt secrets-decrypt \
        firewall luks-init luks-open

# --- standard (single-user host) ---
up:        ; docker compose up -d --build
down:      ; docker compose down
logs:      ; docker compose logs -f --tail=100
proxy-up:  ; docker compose --profile proxy up -d --build
test:      ; python -m pytest -q
backup:    ; bash scripts/backup.sh
restore:   ; bash scripts/restore.sh $(DUMP)

# --- hardened (shared / multi-user host) ---
# Creates the data dirs (on the LUKS mount if DATA_DIR points there) then brings
# the stack up with secrets-as-files + container hardening. One command.
harden-up:
	@mkdir -p "$(DATA_DIR)/postgres" "$(DATA_DIR)/n8n"
	@mountpoint -q "$(DATA_DIR)" 2>/dev/null \
	  && echo "[ok] $(DATA_DIR) is an encrypted mount" \
	  || echo "[warn] $(DATA_DIR) is NOT a mountpoint — data will sit on the plain disk (run 'make luks-open')"
	DATA_DIR="$(DATA_DIR)" docker compose $(HARDENED) up -d --build

harden-down:     ; docker compose $(HARDENED) down
harden-logs:     ; docker compose $(HARDENED) logs -f --tail=100
secrets-encrypt: ; bash scripts/secrets-encrypt.sh
secrets-decrypt: ; bash scripts/secrets-decrypt.sh
firewall:        ; bash scripts/firewall.sh
luks-init:       ; DATA_DIR="$(DATA_DIR)" bash scripts/luks-setup.sh
luks-open:       ; DATA_DIR="$(DATA_DIR)" bash scripts/luks-open.sh
