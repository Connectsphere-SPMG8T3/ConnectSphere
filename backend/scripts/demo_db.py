"""Swap the shared Supabase project's data for the live demo, and put it back.

The project is the team's development database, the demo database and the graded
evidence at once (docs/CI.md), so the demo runs on a swapped copy of its data:

    python scripts/demo_db.py backup pre-demo          # every row, to ~/connectsphere-backups/
    python scripts/demo_db.py rehearse <backup-dir>    # wipe + restore, rolled back; counts must match
    python scripts/demo_db.py swap <backup-dir>        # wipe, then supabase/seed.sql
    python scripts/demo_db.py restore <backup-dir>     # wipe, then the backup's rows exactly

Then `python scripts/demo_data.py --load` builds each story's starting state.

A backup is one JSON file per table (`<schema>.<table>.json`, an array of rows) for
every public base table plus auth.users and auth.identities, and `_counts.json`. It
holds password hashes and personal data, so it lives outside the repository and is
never committed. Sessions and refresh tokens aren't kept: people sign in again.

Everything goes through `supabase db query --linked`, since `supabase db dump` needs
Docker. Restoring inserts with `session_replication_role = replica`, so no trigger
runs (no new history, notifications or profiles) and foreign keys aren't checked
until the whole backup is in.
"""

import argparse
import json
import secrets
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.verify_live import REPO_ROOT, _rows, _supabase_query, db_query

BACKUP_ROOT = Path.home() / "connectsphere-backups"
SEED = REPO_ROOT / "supabase" / "seed.sql"
AUTH_TABLES = ["auth.users", "auth.identities"]
# Filled by migrations, not by seed.sql: a wipe would lose them for good.
REFERENCE_TABLES = frozenset({"public.notification_types"})
MAX_BACKUP_AGE_SECONDS = 3600


def public_tables() -> list[str]:
    rows = db_query("select table_schema || '.' || table_name as t from information_schema.tables "
                    "where table_type = 'BASE TABLE' and table_schema = 'public' order by 1")
    return [row["t"] for row in rows]


def generated_columns() -> dict[str, set[str]]:
    rows = db_query("select table_schema || '.' || table_name as t, column_name as c "
                    "from information_schema.columns where is_generated = 'ALWAYS' "
                    "and table_schema in ('public', 'auth')")
    columns: dict[str, set[str]] = {}
    for row in rows:
        columns.setdefault(row["t"], set()).add(row["c"])
    return columns


def table_counts(tables: list[str]) -> dict[str, int]:
    union = " union all ".join(f"select '{t}' as t, count(*)::int as n from {t}" for t in tables)
    return {row["t"]: row["n"] for row in db_query(union)}


def backup(label: str, root: Path = BACKUP_ROOT) -> Path:
    directory = root / f"{datetime.now():%Y-%m-%d-%H%M}-{label}"
    directory.mkdir(parents=True)
    counts = {}
    for table in public_tables() + AUTH_TABLES:
        rows = db_query(f"select coalesce(json_agg(x), '[]'::json) as j from {table} x")[0]["j"]
        (directory / f"{table}.json").write_text(json.dumps(rows))
        counts[table] = len(rows)
    (directory / "_counts.json").write_text(json.dumps(counts, indent=1))
    return directory


def wipe_sql(tables: list[str]) -> str:
    """Empties every given public table except the reference ones, then every account
    (identities, sessions and the rest of auth cascade)."""
    wiped = [t for t in tables if t not in REFERENCE_TABLES]
    truncate = f"truncate {', '.join(wiped)};\n" if wiped else ""
    return f"{truncate}delete from auth.users;\n"


def restore_sql(backup_dir: Path, tables: list[str], generated: dict[str, set[str]]) -> str:
    statements = [wipe_sql(tables), "set local session_replication_role = replica;\n"]
    for path in sorted(backup_dir.glob("*.json")):
        table = path.stem
        if table.startswith("_") or table in REFERENCE_TABLES:
            continue
        text = path.read_text()
        rows = json.loads(text)
        if not rows:
            continue
        columns = ", ".join(f'"{c}"' for c in rows[0] if c not in generated.get(table, set()))
        tag = _dollar_tag(text)
        statements.append(
            f"insert into {table} ({columns}) select {columns} "
            f"from json_populate_recordset(null::{table}, ${tag}${text}${tag}$::json);\n"
        )
    return "".join(statements)


def _dollar_tag(text: str) -> str:
    while True:
        tag = f"demo_{secrets.token_hex(6)}"
        if f"${tag}$" not in text:
            return tag


def compare_counts(expected: dict[str, int], actual: dict[str, int]) -> list[str]:
    return [f"{t}: expected {n}, found {actual.get(t)}" for t, n in expected.items() if actual.get(t) != n]


def require_fresh_backup(backup_dir: Path) -> dict[str, int]:
    counts = backup_dir / "_counts.json"
    if not counts.exists():
        raise SystemExit(f"{backup_dir}: no _counts.json, so not a backup")
    if time.time() - counts.stat().st_mtime > MAX_BACKUP_AGE_SECONDS:
        raise SystemExit(f"{backup_dir}: older than an hour; take a fresh backup first")
    return json.loads(counts.read_text())


def run_sql(sql: str) -> list[dict]:
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as handle:
        handle.write(sql)
    try:
        completed = _supabase_query("-f", handle.name)
    finally:
        Path(handle.name).unlink()
    if completed.returncode != 0:
        raise SystemExit(f"query failed: {completed.stderr.strip()[-500:]}")
    return _rows(completed.stdout)


def counts_query(tables: list[str]) -> str:
    rows = ", ".join(f"'{t}', (select count(*) from {t})" for t in tables)
    return f"select json_build_object({rows}) as counts;\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["backup", "rehearse", "swap", "restore"])
    parser.add_argument("target", help="a label for backup; the backup directory otherwise")
    args = parser.parse_args()

    if args.command == "backup":
        print(backup(args.target))
        return 0

    backup_dir = Path(args.target).expanduser()
    tables = public_tables()
    everything = tables + AUTH_TABLES
    if args.command == "swap":
        require_fresh_backup(backup_dir)
        run_sql(f"begin;\n{wipe_sql(tables)}commit;\n")
        run_sql(SEED.read_text())
        print(json.dumps(table_counts(everything), indent=1))
        return 0

    expected = json.loads((backup_dir / "_counts.json").read_text())
    restore = restore_sql(backup_dir, tables, generated_columns())
    if args.command == "rehearse":
        [row] = run_sql(f"begin;\n{restore}{counts_query(everything)}rollback;\n")
        actual = row["counts"]
    else:
        run_sql(f"begin;\n{restore}commit;\n")
        actual = table_counts(everything)
    mismatches = compare_counts(expected, actual)
    print("\n".join(mismatches) or f"all {len(expected)} tables match the backup")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
