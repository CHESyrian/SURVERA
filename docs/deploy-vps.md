# SURVERA — VPS deployment runbook

Target stack: **Ubuntu 22.04/24.04 LTS**, **SQLite**, Redis, Nginx, Gunicorn, Celery.  
App settings module: `config.settings.production`.

This runbook is for a **single-VPS** deploy (app + SQLite file + Redis on one machine). Adjust hostnames, paths, and secrets for your environment.

---

## 1. Prerequisites

| Component | Notes |
|-----------|--------|
| Domain | DNS `A`/`AAAA` → VPS public IP |
| OS | Ubuntu 22.04+ recommended |
| Python | **3.12+** |
| Database | **SQLite** (default in production settings; file under `data/survera_db.sqlite3`) |
| Redis | For cache + Celery broker |
| TLS | Certbot (Let’s Encrypt) via Nginx |

Example values used below:

- App user: `survera`
- App directory: `/srv/survera`
- Domain: `survera.example.com`
- SQLite file: `/srv/survera/app/data/survera_db.sqlite3`

---

## 2. System packages

```bash
sudo apt update
sudo apt install -y \
  python3.12 python3.12-venv python3.12-dev \
  build-essential \
  redis-server \
  nginx certbot python3-certbot-nginx \
  git curl
```

Enable services:

```bash
sudo systemctl enable --now redis-server nginx
```

---

## 3. Application user and directory

```bash
sudo adduser --system --group --home /srv/survera --shell /bin/bash survera
sudo mkdir -p /srv/survera
sudo chown survera:survera /srv/survera
```

Clone or upload the project (as `survera` or deploy user, then chown):

```bash
sudo -u survera -H bash -lc '
  cd /srv/survera
  git clone <YOUR_REPO_URL> app
  # or: rsync / unpack release into /srv/survera/app
'
```

Layout after deploy:

```text
/srv/survera/
  app/                 # repository root (manage.py lives here)
  .venv/               # virtualenv (optional alternate: app/.venv)
  run/                 # sockets, pid files
  logs/                # optional extra logs outside app
```

This runbook uses:

- Code: `/srv/survera/app`
- Venv: `/srv/survera/.venv`
- Socket: `/srv/survera/run/gunicorn.sock`

```bash
sudo -u survera mkdir -p /srv/survera/run /srv/survera/logs
sudo -u survera python3.12 -m venv /srv/survera/.venv
```

---

## 4. SQLite database

Production settings create and use:

```text
/srv/survera/app/data/survera_db.sqlite3
```

Ensure the app user can write the directory:

```bash
sudo -u survera mkdir -p /srv/survera/app/data
sudo -u survera chmod 750 /srv/survera/app/data
```

Optional: set an absolute path in `.env`:

```bash
SQLITE_PATH=/srv/survera/app/data/survera_db.sqlite3
```

**Concurrency note:** SQLite allows one writer at a time. Prefer **1–2 Gunicorn workers** on a small VPS. The production engine sets a 20s busy timeout. For heavy write load, plan a later move to PostgreSQL.

After deploy, enable WAL once (recommended):

```bash
sudo -u survera -H bash -lc '
  source /srv/survera/.venv/bin/activate
  cd /srv/survera/app
  python - <<PY
import sqlite3
from pathlib import Path
p = Path("data/survera_db.sqlite3")
if p.exists():
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL;")
    con.close()
    print("WAL enabled")
else:
    print("DB not created yet — run migrate first")
PY
'
```

---

## 5. Python dependencies

```bash
sudo -u survera -H bash -lc '
  source /srv/survera/.venv/bin/activate
  cd /srv/survera/app
  pip install --upgrade pip
  pip install -e .
  # For one-off checks on the server you may use: pip install -e ".[dev]"
'
```

Production runtime needs at least: Django, psycopg, redis, celery, gunicorn, whitenoise (declared in `pyproject.toml`).

---

## 6. Environment file

Create `/srv/survera/app/.env` (mode `600`, owner `survera`). **Do not** copy a local dev `.env` with weak keys.

```bash
sudo -u survera install -m 600 /dev/null /srv/survera/app/.env
sudo -u survera nano /srv/survera/app/.env
```

### Minimal production `.env`

```bash
DEBUG=False
SECRET_KEY=replace-with-long-random-string-at-least-50-chars
ALLOWED_HOSTS=survera.example.com,www.survera.example.com
CSRF_TRUSTED_ORIGINS=https://survera.example.com,https://www.survera.example.com

# SQLite is the production default (data/survera_db.sqlite3). Optional override:
# SQLITE_PATH=/srv/survera/app/data/survera_db.sqlite3
# Do not set a postgres DATABASE_URL unless you intentionally switch engines.

REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0

SITE_URL=https://survera.example.com
DEFAULT_FROM_EMAIL=noreply@survera.example.com

SECURE_SSL_REDIRECT=True

# SMTP (required for email verification + notifications)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-smtp-user
EMAIL_HOST_PASSWORD=your-smtp-password

# Optional: Cloudflare Turnstile on register / resend
# TURNSTILE_ENABLED=True
# TURNSTILE_SITE_KEY=...
# TURNSTILE_SECRET_KEY=...
```

Generate a secret key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Notes:

- `CSRF_TRUSTED_ORIGINS` must include the **https://** origin (no trailing slash).
- `SITE_URL` is used in email links; no trailing slash.
- Leave `EMAIL_REDIRECT_TO_TEST` unset/false in production.

---

## 7. Django bootstrap

```bash
sudo -u survera -H bash -lc '
  source /srv/survera/.venv/bin/activate
  cd /srv/survera/app
  export DJANGO_SETTINGS_MODULE=config.settings.production

  python manage.py check --deploy
  python manage.py migrate
  python manage.py collectstatic --noinput
  python manage.py compilemessages || true

  python manage.py createsuperuser
  python manage.py init_company
  python manage.py seed_badges
'
```

`init_company` creates the platform company **SURVERA** and attaches superusers as admins.

Ensure writable dirs:

```bash
sudo -u survera mkdir -p /srv/survera/app/logs /srv/survera/app/media /srv/survera/app/staticfiles
```

---

## 8. Gunicorn (systemd)

Unit file: `/etc/systemd/system/survera-web.service`

```ini
[Unit]
Description=SURVERA Gunicorn
After=network.target redis-server.service

[Service]
User=survera
Group=survera
WorkingDirectory=/srv/survera/app
Environment=DJANGO_SETTINGS_MODULE=config.settings.production
EnvironmentFile=/srv/survera/app/.env
ExecStart=/srv/survera/.venv/bin/gunicorn \
  --workers 2 \
  --threads 2 \
  --bind unix:/srv/survera/run/gunicorn.sock \
  --timeout 60 \
  --access-logfile /srv/survera/logs/gunicorn-access.log \
  --error-logfile /srv/survera/logs/gunicorn-error.log \
  config.wsgi:application
Restart=on-failure
RestartSec=3

# Hardening (optional but recommended)
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now survera-web
sudo systemctl status survera-web
```

Socket must be readable by Nginx (`www-data`). Either:

```bash
sudo usermod -aG survera www-data
# and ensure /srv/survera/run is group-executable
sudo chmod 750 /srv/survera /srv/survera/run
```

…or bind Gunicorn to `127.0.0.1:8000` and proxy to that instead of a unix socket.

---

## 9. Celery worker (systemd)

Unit file: `/etc/systemd/system/survera-celery.service`

```ini
[Unit]
Description=SURVERA Celery worker
After=network.target redis-server.service
Requires=redis-server.service

[Service]
User=survera
Group=survera
WorkingDirectory=/srv/survera/app
Environment=DJANGO_SETTINGS_MODULE=config.settings.production
EnvironmentFile=/srv/survera/app/.env
ExecStart=/srv/survera/.venv/bin/celery -A config worker -l info --concurrency 2
Restart=on-failure
RestartSec=5

NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now survera-celery
sudo systemctl status survera-celery
```

Without Celery, many notification paths fall back to synchronous delivery; still run a worker in production when possible.

Optional beat (only if you schedule periodic tasks via django-celery-beat):

```ini
# /etc/systemd/system/survera-celery-beat.service
[Unit]
Description=SURVERA Celery beat
After=network.target redis-server.service

[Service]
User=survera
Group=survera
WorkingDirectory=/srv/survera/app
Environment=DJANGO_SETTINGS_MODULE=config.settings.production
EnvironmentFile=/srv/survera/app/.env
ExecStart=/srv/survera/.venv/bin/celery -A config beat -l info
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

---

## 10. Nginx

Site config: `/etc/nginx/sites-available/survera`

```nginx
upstream survera_app {
    server unix:/srv/survera/run/gunicorn.sock fail_timeout=0;
}

server {
    listen 80;
    listen [::]:80;
    server_name survera.example.com www.survera.example.com;

    # Certbot will adjust this server for HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name survera.example.com www.survera.example.com;

    # ssl_certificate / ssl_certificate_key filled by Certbot

    client_max_body_size 20M;

    # Optional: let Nginx serve WhiteNoise-collected static (Gunicorn+WhiteNoise also works)
    location /static/ {
        alias /srv/survera/app/staticfiles/;
        expires 7d;
        add_header Cache-Control "public";
    }

    location /media/ {
        alias /srv/survera/app/media/;
        expires 1d;
    }

    location / {
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_redirect off;
        proxy_pass http://survera_app;
    }
}
```

Enable and obtain certificates:

```bash
sudo ln -sf /etc/nginx/sites-available/survera /etc/nginx/sites-enabled/survera
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

sudo certbot --nginx -d survera.example.com -d www.survera.example.com
```

Confirm `SECURE_PROXY_SSL_HEADER` in production settings matches `X-Forwarded-Proto` (already set).

---

## 11. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

Do **not** expose Redis publicly. Keep the SQLite file permissions restricted to the app user.

---

## 12. Smoke test checklist

Run after first deploy:

1. **HTTPS** loads; HTTP redirects to HTTPS.
2. **`python manage.py check --deploy`** reports no critical issues.
3. **Register** → receive verification email → verify code.
4. **Create company** (verified user) → create survey + questions → publish.
5. **Discover** → take survey → confirm XP / points / Reputation as expected.
6. **Manager**: analytics, response detail, CSV export (no participant email/name).
7. **Notifications**: publish / invite appear in-app; email when enabled.
8. **Sidebar UI**: desktop collapse, mobile drawer, brand images.
9. **Admin**: `/admin/` login; optional report/penalty path.
10. **Logs**: `/srv/survera/app/logs/django.log`, Gunicorn error log, `journalctl -u survera-web -u survera-celery`.

Useful one-offs:

```bash
sudo -u survera -H bash -lc '
  source /srv/survera/.venv/bin/activate
  cd /srv/survera/app
  export DJANGO_SETTINGS_MODULE=config.settings.production
  python manage.py send_test_email --kind=all
  python manage.py send_test_notification
'
```

---

## 13. Deploy / update procedure

```bash
sudo -u survera -H bash -lc '
  source /srv/survera/.venv/bin/activate
  cd /srv/survera/app
  git pull   # or unpack new release
  pip install -e .
  export DJANGO_SETTINGS_MODULE=config.settings.production
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
  python manage.py compilemessages || true
'
sudo systemctl restart survera-web survera-celery
sudo systemctl status survera-web survera-celery --no-pager
```

Prefer short maintenance windows if migrations are non-trivial.

---

## 14. Backups (minimum)

**Database** (copy SQLite file; stop writes briefly or use SQLite backup API):

```bash
sudo mkdir -p /var/backups/survera
sudo install -d -o survera -g survera /var/backups/survera
# Simple file copy (acceptable for low traffic; prefer downtime or sqlite3 .backup for consistency)
sudo -u survera cp -a /srv/survera/app/data/survera_db.sqlite3 "/var/backups/survera/survera_db_$(date +%F).sqlite3"
# Also copy WAL/SHM if present:
sudo -u survera bash -lc 'cp -a /srv/survera/app/data/survera_db.sqlite3* /var/backups/survera/ 2>/dev/null || true'
```

**Media** (if users upload files):

```bash
rsync -a /srv/survera/app/media/ /var/backups/survera/media/
```

Retain several days of dumps off-box when possible.

---

## 15. Troubleshooting

| Symptom | Check |
|---------|--------|
| CSRF / 403 on login | `CSRF_TRUSTED_ORIGINS` includes `https://your-domain`; cookies Secure; clock OK |
| Redirect loop | Nginx `X-Forwarded-Proto`; `SECURE_SSL_REDIRECT`; cert valid |
| Static 404 | `collectstatic`; WhiteNoise or Nginx `/static/` alias path |
| Email never arrives | SMTP env vars; provider auth; `DEFAULT_FROM_EMAIL`; spam folder |
| Celery silent | `redis-cli ping`; `systemctl status survera-celery`; broker URL |
| 502 Bad Gateway | Gunicorn running; socket permissions; Nginx upstream path |
| DB locked / OperationalError | Fewer Gunicorn workers; enable WAL; check `data/` permissions; `SQLITE_PATH` |
| DB file missing | Run `migrate`; ensure `data/` exists and is writable by `survera` |
| `check --deploy` warnings | SECRET_KEY strength, DEBUG, ALLOWED_HOSTS, HSTS, etc. |

```bash
journalctl -u survera-web -n 100 --no-pager
journalctl -u survera-celery -n 100 --no-pager
sudo -u survera tail -n 100 /srv/survera/app/logs/django.log
```

---

## 16. Security checklist

- [ ] Strong unique `SECRET_KEY`; never commit `.env`
- [ ] `DEBUG=False`
- [ ] `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` locked to real hosts
- [ ] TLS only; HSTS enabled (production settings)
- [ ] Postgres and Redis bound to localhost (or private network)
- [ ] App runs as non-root (`survera`)
- [ ] Firewall: SSH + HTTP/HTTPS only
- [ ] Superuser password strong; limit staff accounts
- [ ] Optional Turnstile on public registration
- [ ] Backups tested with a restore drill

---

## Reference

| Item | Value |
|------|--------|
| Settings | `config.settings.production` |
| WSGI | `config.wsgi:application` |
| Celery app | `config` (`celery -A config`) |
| Static root | `staticfiles/` (WhiteNoise + optional Nginx) |
| Media root | `media/` |
| Bootstrap | `migrate`, `createsuperuser`, `init_company`, `seed_badges` |

Product rules and architecture: `docs/sections.md`, `docs/adr/`.
