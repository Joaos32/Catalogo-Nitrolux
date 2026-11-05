"""Check or initialize the private catalog schema in the configured PostgreSQL database."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from catalog import state_database  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Create the private schema and tables if absent")
    args = parser.parse_args(argv)
    if not state_database.is_configured():
        print("Configure CATALOG_STATE_DATABASE_URL in .env.local first.", file=sys.stderr)
        return 1
    try:
        with state_database._connect() as connection:
            if args.apply:
                schema = (BASE_DIR / "scripts" / "sql" / "catalog_state.sql").read_text(encoding="utf-8")
                connection.execute(schema)
            tables = connection.execute(
                "SELECT to_regclass('catalog_private.objects'), to_regclass('catalog_private.presence')"
            ).fetchone()
            if not tables or any(table is None for table in tables):
                print("Connection OK; catalog tables are missing. Use --apply to initialize them.")
                return 1
            # An actual read catches missing schema/table read privileges.
            rows = connection.execute(
                "SELECT object_key, octet_length(content) FROM catalog_private.objects ORDER BY object_key"
            ).fetchall()
            connection.execute("SELECT email FROM catalog_private.presence LIMIT 0")
        print("Connection OK; private catalog tables are available.")
        for key, size in rows:
            if key in {state_database.REPRESENTATIVES_KEY, state_database.ERP_KEY}:
                print(f"Stored {key}: {size} bytes")
        if not rows:
            print("No catalog state stored yet. Run migrate_blob_state.py after validating the source.")
        return 0
    except Exception as exc:
        # Never include driver errors or connection strings in command output.
        print(f"Database setup failed ({type(exc).__name__}). Check credentials and database permissions.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env.local")
    load_dotenv(BASE_DIR / ".env")
    raise SystemExit(main())
