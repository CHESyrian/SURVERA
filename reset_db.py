#!/usr/bin/env python
"""
Reset SURVERA database from a clean slate.

- Deletes SQLite database files (if used)
- Removes all app migration modules (keeps migrations/__init__.py)
- Runs makemigrations + migrate
- Creates a superuser: username=admin, password=password

Usage (from project root, venv active):

    python reset_db.py

Optional:

    python reset_db.py --settings config.settings.local
    python reset_db.py --no-input   # same as default; kept for clarity
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
APPS_DIR = BASE_DIR / "apps"

# App packages that own migrations (domain apps under apps/)
APP_MIGRATION_DIRS = [
    APPS_DIR / "accounts" / "migrations",
    APPS_DIR / "common" / "migrations",
    APPS_DIR / "companies" / "migrations",
    APPS_DIR / "surveys" / "migrations",
    APPS_DIR / "responses" / "migrations",
    APPS_DIR / "rewards" / "migrations",
    APPS_DIR / "notifications" / "migrations",
]


def _log(msg: str) -> None:
    print(msg, flush=True)


def delete_migration_files() -> int:
    """Remove migration modules; keep each migrations/__init__.py."""
    removed = 0
    for mig_dir in APP_MIGRATION_DIRS:
        if not mig_dir.is_dir():
            continue
        for path in sorted(mig_dir.iterdir()):
            if path.name == "__init__.py":
                continue
            if path.suffix == ".py" or path.suffix == ".pyc":
                path.unlink(missing_ok=True)
                removed += 1
                _log(f"  removed {path.relative_to(BASE_DIR)}")
            elif path.is_dir() and path.name == "__pycache__":
                for cached in path.glob("*"):
                    cached.unlink(missing_ok=True)
                try:
                    path.rmdir()
                except OSError:
                    pass
    return removed


def delete_sqlite_files() -> list[Path]:
    """Delete known SQLite DB files under the project."""
    candidates = [
        BASE_DIR / "db.sqlite3",
        BASE_DIR / "data" / "survera_db.sqlite3",
        BASE_DIR / "survera_db.sqlite3",
    ]
    # Also honor SQLITE_PATH from environment if set
    env_path = os.environ.get("SQLITE_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path))

    deleted: list[Path] = []
    for db_path in candidates:
        for suffix in ("", "-journal", "-wal", "-shm"):
            p = Path(f"{db_path}{suffix}") if suffix else db_path
            if p.is_file():
                p.unlink(missing_ok=True)
                deleted.append(p)
                _log(f"  deleted {p}")
    return deleted


def django_setup(settings_module: str) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)
    # Ensure project root is on sys.path
    root = str(BASE_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)

    import django

    django.setup()


def run_management(*args: str) -> None:
    from django.core.management import call_command

    call_command(*args)


def create_superuser() -> None:
    """Create superuser username=admin / password=password (email login)."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    email = "admin@survera.local"
    username = "admin"
    password = "password"

    existing = User.objects.filter(email__iexact=email).first()
    if existing is None:
        existing = User.objects.filter(username=username).first()

    if existing is not None:
        existing.username = username
        existing.email = email
        existing.set_password(password)
        existing.is_staff = True
        existing.is_superuser = True
        existing.is_active = True
        if hasattr(existing, "is_email_verified"):
            existing.is_email_verified = True
        existing.save()
        _log(f"  updated existing superuser: {email} / {username}")
        return

    kwargs = {
        "username": username,
        "email": email,
        "password": password,
        "is_staff": True,
        "is_superuser": True,
        "is_active": True,
    }
    if "is_email_verified" in {f.name for f in User._meta.get_fields()}:
        kwargs["is_email_verified"] = True

    User.objects.create_superuser(**kwargs)
    _log(f"  created superuser: email={email} username={username} password={password}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset SURVERA DB and migrations.")
    parser.add_argument(
        "--settings",
        default=os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.local"),
        help="Django settings module (default: config.settings.local)",
    )
    args = parser.parse_args()

    _log("=== SURVERA database reset ===")
    _log(f"Settings: {args.settings}")
    _log(f"Project:  {BASE_DIR}")

    _log("\n[1/5] Removing migration files...")
    n = delete_migration_files()
    _log(f"  done ({n} file(s) removed)")

    _log("\n[2/5] Removing SQLite database files (if any)...")
    deleted = delete_sqlite_files()
    if not deleted:
        _log("  no SQLite files found (Postgres or empty — migrate will recreate schema)")
    else:
        _log(f"  done ({len(deleted)} file(s))")

    _log("\n[3/5] Django setup...")
    django_setup(args.settings)

    from django.conf import settings

    engine = settings.DATABASES["default"].get("ENGINE", "")
    name = settings.DATABASES["default"].get("NAME", "")
    _log(f"  engine: {engine}")
    _log(f"  name:   {name}")

    # For non-SQLite: drop all tables so migrate starts clean after migration wipe
    if "sqlite" not in engine:
        _log("\n[3b] Flushing non-SQLite database (drop all tables)...")
        try:
            from django.db import connection

            with connection.cursor() as cursor:
                if connection.vendor == "postgresql":
                    cursor.execute("DROP SCHEMA public CASCADE;")
                    cursor.execute("CREATE SCHEMA public;")
                    cursor.execute("GRANT ALL ON SCHEMA public TO CURRENT_USER;")
                    cursor.execute("GRANT ALL ON SCHEMA public TO public;")
                    _log("  PostgreSQL schema recreated")
                else:
                    _log("  non-Postgres engine — running migrate with fake-initial disabled")
        except Exception as exc:  # noqa: BLE001
            _log(f"  warning: could not reset schema automatically: {exc}")
            _log("  continue with makemigrations/migrate")

    _log("\n[4/5] makemigrations + migrate...")
    run_management("makemigrations", "accounts", "companies", "surveys", "responses", "rewards", "notifications")
    # common may have no models — ignore quietly
    try:
        run_management("makemigrations", "common")
    except Exception:
        pass
    run_management("migrate", verbosity=1)

    _log("\n[5/5] Creating superuser...")
    create_superuser()

    _log("\n=== Reset complete ===")
    _log("Login: email=admin@survera.local  (or username=admin)  password=password")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
