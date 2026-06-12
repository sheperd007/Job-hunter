# DATA_DIR is read from .env so the value is authoritative and consistent across
# `harden-*` recipes and `docker compose` (which also reads .env). Override on the
# CLI with `make harden-up DATA_DIR=/abs/path` if you prefer.
DATA_DIR := $(shell sh -c "grep -E '^DATA_DIR=' .env 2>/dev/null | tail -1 | cut -d= -f2-")
ifeq ($(strip $(DATA_DIR)),)
DATA_DIR := ./data
endif
export DATA_DIR
HARDENED := -f docker-compose.yml -f docker-compose.hardened.yml

.PHONY: up down logs test backup restore proxy-up \
        harden-up harden-down harden-logs harden-reset secrets-encrypt secrets-decrypt \
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
# Refuses to start if DATA_DIR is a LUKS path that is not currently mounted
# (else data would silently land unencrypted). Override with ALLOW_PLAINTEXT=1.
harden-up:
	@D="$(DATA_DIR)"; \
	if [ "$$D" != "./data" ] && ! mountpoint -q "$$D" 2>/dev/null; then \
	  if [ "$$ALLOW_PLAINTEXT" = "1" ]; then echo "[warn] $$D not mounted; ALLOW_PLAINTEXT=1 -> writing to plain disk"; \
	  else echo "[fatal] $$D is not a mountpoint. Run 'make luks-open' first, or pass ALLOW_PLAINTEXT=1."; exit 1; fi; \
	fi; \
	mkdir -p "$$D/postgres" "$$D/n8n"
	docker compose $(HARDENED) up -d --build

harden-down:     ; docker compose $(HARDENED) down
harden-logs:     ; docker compose $(HARDENED) logs -f --tail=100
# DESTROYS the data volumes (use after changing DATA_DIR so the bind rebinds).
harden-reset:    ; docker compose $(HARDENED) down -v

secrets-encrypt: ; bash scripts/secrets-encrypt.sh
secrets-decrypt: ; bash scripts/secrets-decrypt.sh
firewall:        ; bash scripts/firewall.sh
luks-init:       ; bash scripts/luks-setup.sh
luks-open:       ; bash scripts/luks-open.sh
