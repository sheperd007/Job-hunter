.PHONY: up down logs test backup restore proxy-up
up:        ; docker compose up -d --build
down:      ; docker compose down
logs:      ; docker compose logs -f --tail=100
proxy-up:  ; docker compose --profile proxy up -d --build
test:      ; python -m pytest -q
backup:    ; bash scripts/backup.sh
restore:   ; bash scripts/restore.sh $(DUMP)
