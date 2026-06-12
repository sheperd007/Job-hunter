# secrets/

One file per secret, filename = lowercase setting name, content = the raw value
(no quotes, no trailing newline ideally). These are mounted at `/run/secrets/<name>`
by `docker-compose.hardened.yml` and read by the worker (via pydantic
`secrets_dir`), Postgres (`*_FILE`), and n8n (`*_FILE`).

**Never commit the actual files** — only this README and `.gitignore` are tracked.

Required files:

```
db_password
openai_key_a
openai_key_b
notion_token
adzuna_app_key
n8n_encryption_key          # 32+ random chars; keep STABLE (rotating it locks saved n8n creds)
n8n_basic_auth_password
```

Create them (chmod 600), e.g.:

```bash
umask 077
printf '%s' 'sk-...keyA...'        > secrets/openai_key_a
printf '%s' 'sk-...keyB...'        > secrets/openai_key_b
printf '%s' 'secret_...notion...'  > secrets/notion_token
printf '%s' '...adzuna_app_key...' > secrets/adzuna_app_key
printf '%s' 'a-strong-db-pass'     > secrets/db_password
openssl rand -hex 24               > secrets/n8n_encryption_key
printf '%s' 'n8n-ui-login-pass'    > secrets/n8n_basic_auth_password
chmod 600 secrets/*
```

Then encrypt them at rest: `AGE_RECIPIENT=age1... bash scripts/secrets-encrypt.sh`
(see [docs/SECURITY.md](../docs/SECURITY.md)).
