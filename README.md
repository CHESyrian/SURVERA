# SURVERA

**SURVERA** is a hybrid survey platform:

- **Companies** create free or paid surveys, publish them, view analytics, and export CSV (without participant PII)
- **People** discover and take surveys, earn **XP** (levels & badges), **points** (paid surveys only), and **Reputation** (honor ledger → trust levels)
- **Project superusers** create surveys under the platform company **SURVERA**
- **Notifications** (in-app + email) for publish, team invites, points, and moderation outcomes — with per-user preferences
- **Email verification** (6-digit code) gates take/create survey, points, XP, badges, CSV export, and company creation
- **Moderation**: managers report responses; staff apply a penalty catalog or dismiss from Django admin

Bilingual: **English + Arabic** (RTL supported). Light / dark theme.

See `docs/adr/0001-core-architecture-and-product-decisions.md` and `docs/sections.md` for product rules and architecture.

---

## Tech stack

| Layer | Choice |
|--------|--------|
| Language | Python 3.12+ |
| Framework | Django 5.1 |
| Database | **SQLite** (production) · PostgreSQL optional (local) |
| Cache / queue | Redis + **Celery** (async notification fan-out) |
| Frontend | Django templates + HTMX + Alpine.js + Bootstrap 5 |
| Other | WhiteNoise, django-environ, Pillow, console/SMTP email |

---

## Project structure

```
.
├── apps/
│   ├── accounts/        # User, auth, profile, email verification, Reputation / trust, moderation fields
│   ├── companies/       # Company + memberships + init_company
│   ├── surveys/         # Survey, Question, discover, publish, targeting, analytics
│   ├── responses/       # Take survey, answers, detail view, CSV, reports & penalties
│   ├── rewards/         # Points, XP, levels, badges, daily/weekly tasks
│   ├── notifications/   # In-app + email, Celery tasks, preferences
│   └── common/          # Abstract models, constants, home view
├── config/              # Settings (local / production / test), urls, wsgi/asgi, celery
├── docs/                # ADR + team sections
├── locale/              # EN / AR translation catalogs
├── templates/           # base.html (navbar, footer, theme)
├── static/
│   ├── css/survera.css
│   └── js/password.js
├── manage.py
├── pyproject.toml
└── README.md
```

Each domain app ships a single **`0001_initial`** migration (schema rebuilt from current models).

---

## Installation

### Quick start

```bash
# 1. Enter project root (folder with manage.py)
cd survera

# 2. Virtualenv + dependencies
python3.12 -m venv .venv
source .venv/bin/activate                 # Linux / macOS
# .venv\Scripts\activate                  # Windows
pip install -U pip
pip install -e ".[dev]"                   # or: make install

# 3. Environment
cp .env.example .env
# Edit .env → SECRET_KEY, DATABASE_URL (see table below)

# 4. Database
# Create role/DB if needed, then:
python manage.py migrate

# 5. Bootstrap
python manage.py createsuperuser          # login with email + password
python manage.py init_company             # platform company SURVERA
python manage.py seed_badges              # optional

# 6. Run
python manage.py runserver                # http://127.0.0.1:8000/
```

### Prerequisites

| Requirement | Notes |
|-------------|--------|
| **Python 3.12+** | `python3 --version` |
| **SQLite** | Built into Python — **production default** (`data/survera_db.sqlite3`) |
| **PostgreSQL 15+** | Optional for local if you set `DATABASE_URL` |
| **Redis** | Recommended for Celery; optional (sync fallback works) |

**System packages (examples)**

```bash
# Debian / Ubuntu (production-style: no Postgres required)
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip \
  redis-server build-essential

# Optional local PostgreSQL
# sudo apt install -y postgresql postgresql-contrib libpq-dev

# macOS (Homebrew)
brew install python@3.12 redis
brew services start redis
```

Production uses SQLite automatically (`config.settings.production`).  
Local may still use PostgreSQL via `DATABASE_URL` in `.env`.

### Environment (`.env`)

| Variable | Example | Notes |
|----------|---------|--------|
| `SECRET_KEY` | long random string | Required in production |
| `DEBUG` | `True` | Local only |
| `SQLITE_PATH` | `/srv/survera/app/data/survera_db.sqlite3` | Optional production override |
| `DATABASE_URL` | `postgres://…` or `sqlite:///…` | Local / optional; production ignores non-sqlite URLs |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | |
| `SITE_URL` | `http://localhost:8000` | Absolute links in emails |
| `REDIS_URL` | `redis://localhost:6379/0` | Cache + Celery |
| `CELERY_BROKER_URL` | same as Redis | |
| `CELERY_RESULT_BACKEND` | same as Redis | |
| `DEFAULT_FROM_EMAIL` | `noreply@survera.local` | |
| `EMAIL_FOR_TEST` | `you@example.com` | Local/manual email tests |
| `EMAIL_REDIRECT_TO_TEST` | `True` | Redirect all outbound mail to `EMAIL_FOR_TEST` |
| `TURNSTILE_ENABLED` | `False` | Optional Cloudflare Turnstile on register/resend |

`manage.py` defaults to `config.settings.local`.

### Reset database & migrations (from zero)

If you need a clean schema matching current models:

```bash
# 1. Drop and recreate the database (PostgreSQL)
#    e.g. DROP DATABASE survera_db; CREATE DATABASE survera_db OWNER admin;

# 2. Remove app migration modules (keep __init__.py only), then:
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py init_company
```

---

## Usage

### Roles

| Who | Create surveys | Take surveys |
|-----|----------------|--------------|
| **Person** | No (unless company manager) | Yes — Discover (email verified) |
| **Company owner / moderator** | Yes — under their company | Yes |
| **Superuser** | Yes — under company **SURVERA** | Yes |

### Typical flows

**Participant**

1. Register → 6-digit email code → verify  
2. Discover → take survey → earn XP / points / Reputation  
3. Profile: level, badges, points, **Reputation**, trust level  
4. Tasks (`/rewards/tasks/`): daily / weekly goals → Reputation + XP  

**Company manager**

1. Create company (owner) → create survey + questions → publish  
2. Analytics, response list, **View answers** (per response), CSV export  
3. Report a response if needed (staff reviews in admin)

**Staff moderation (Django admin → Reports)**

1. Open report → related survey / response / answers / user summary  
2. Choose penalty **or** dismiss  
3. Action **Apply penalty & notify** or **Dismiss report & notify**

### Product rules (short)

- Surveys are **company-owned only**; freeze after first response  
- **Free** → public, XP only · **Paid** → may grant coins; may be private + targeted  
- **Points** ≠ **XP** ≠ **Reputation** (honor ledger → trust levels 1–7)  
- CSV export columns: `response_id`, `completed_at`, answers only — **no participant email/name**  
- Email verification required for take/create survey, company create, CSV, awards  

### Reputation & tasks

| Concept | Role |
|---------|------|
| **Reputation** | UI name for `honor_points`; rises from tasks, quality, onboarding |
| **Trust level** | Derived from Reputation bands (Newcomer → Distinguished) |
| **Tasks** | Daily (3 surveys) / weekly (10) → Reputation + XP |

### Penalty catalog (admin)

| Kind | Effect |
|------|--------|
| **Warning** (progressive) | 1st −100 honor · 2nd −200 · 3rd freeze 7d · 4th freeze 30d · 5th+ permanent close |
| **Honor deduction** | Admin-chosen honor amount |
| **Rank reduction** | Drop N trust levels (e.g. 7→6) |
| **Account freeze** | Admin-chosen days (`frozen_until`) |
| **Permanent closure** | `closed_at` + `is_active=False` |

On penalty: in-app + email to **reporter and subject**. On dismiss: reporter only.  
Frozen / closed accounts cannot log in.

### Notifications

| Event | In-app | Email |
|-------|--------|--------|
| Survey published | Eligible members | Private / members_only |
| Team invite | Yes | Default on |
| Points awarded | Yes | Default off |
| Report outcome | Yes | Always sent for moderation |

Navbar bell + HTMX badge. Preferences: Profile → Settings.

### Useful URLs

| URL | Purpose |
|-----|---------|
| `/` | Home |
| `/surveys/discover/` | Discover |
| `/surveys/` | My surveys |
| `/surveys/create/` | Create survey |
| `/r/survey/<id>/responses/` | Response list (managers) |
| `/r/detail/<id>/` | Response answers detail |
| `/rewards/tasks/` | Daily / weekly tasks |
| `/notifications/` | Inbox |
| `/accounts/profile/` | Profile + prefs |
| `/admin/` | Staff control panel |

### Management commands

| Command | Purpose |
|---------|---------|
| `migrate` | Apply migrations |
| `createsuperuser` | Create staff/superuser |
| `init_company` | Platform company SURVERA + attach superusers |
| `seed_badges` | Upsert default badges |
| `fix_discover_visibility` | Active free surveys → public |
| `send_test_notification` | Test in-app notification |
| `send_test_email` | Test email (`--kind=plain\|invite\|survey\|all`) |

### Settings modules

| Module | Use |
|--------|-----|
| `config.settings.local` | Local (DEBUG, console/redirect email) |
| `config.settings.base` | Shared |
| `config.settings.production` | VPS / production |
| `config.settings.test` | Pytest (SQLite memory, Celery eager, locmem email) |

**VPS deploy:** see [`docs/deploy-vps.md`](docs/deploy-vps.md) (Nginx, Gunicorn, Celery, TLS, env, smoke tests).

### Celery (optional)

```bash
redis-server
celery -A config worker -l info
python manage.py runserver
```

Without a worker, notifications fall back to synchronous delivery.

---

## Testing

Tests use **SQLite in-memory** (no PostgreSQL/Redis required):

```bash
make test
# or
pytest
pytest apps/responses/tests/test_penalties.py -v
pytest apps/responses/tests/test_export_and_detail.py -v
```

---

## Makefile

```bash
make install      # pip install -e ".[dev]"
make migrate      # migrate
make run          # runserver
make test         # pytest
make lint         # ruff check
make format       # ruff format
make makemessages # extract i18n strings
make compilemessages
```

---

## Current product status

**MVP core loop:** create → questions → publish → take → XP / points / Reputation → analytics / CSV  

Also shipped:

- Company roles (owner / moderator / participant) and team management  
- Private surveys + targeting; conditional questions; expanded types  
- Discover filters, EN/AR, light/dark theme  
- Response **detail** (questions + answers); CSV **without PII**  
- Reputation, trust levels, quality scoring, daily/weekly tasks  
- Reports + **penalty catalog** (warnings ladder, honor, rank, freeze, close)  
- Notifications (in-app + email), email verification, Turnstile (optional)  

**Recently added:** richer analytics charts, email digests (daily/weekly), profile badges, leaderboard.

**Possible next:** points redemption / wallet, advanced matrix heatmaps.

---

## Team notes

- Prefer small, focused pull requests  
- Keep **Points**, **XP**, and **Reputation** separate  
- Survey definition freezes after the first response  
- New UI strings: `{% trans %}` / `gettext` + `locale/`  
- Notification writes go through `notify_*`; email/async are side effects  
- Gated features must use `email_verified_required` / `user_email_verified`  
- Product reference: `docs/sections.md`
