"""Generate and apply SQLite migrations from the Pydantic schemas.

The Pydantic models are the source of truth for the database tables. After
changing a model, generate a migration and commit the new .sql file:

    python -m backend.database.migrate make -n add_game_tags
    python -m backend.database.migrate make --rename games.hoursplayed=hours_played
    python -m backend.database.migrate make --allow-drop      # when fields were removed
    python -m backend.database.migrate migrate                # apply pending migrations
    python -m backend.database.migrate check                  # exit 1 if a migration is missing
    python -m backend.database.migrate status

`make` compares the models with the last snapshot (migrations/schema.json) and
writes the SQL needed to go from one to the other. Pending migrations are also
applied automatically by initialize_database() when the app starts.
"""

import argparse
import enum
import json
import re
import sqlite3
import sys
import types
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Union, get_args, get_origin

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

MIGRATIONS_DIRECTORY = Path(__file__).parent / "migrations"
SNAPSHOT_FILE = "schema.json"
MIGRATION_PATTERN = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
MIGRATIONS_TABLE = "schema_migrations"


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class TableSpec:
    model: type[BaseModel]
    primary_key: str
    foreign_keys: dict[str, str] = field(default_factory=dict)
    overrides: dict[str, dict] = field(default_factory=dict)


def table_specs() -> dict[str, TableSpec]:
    # Imported lazily so applying migrations at startup does not load the routes.
    from routes.achievements.schemas import Achievement
    from routes.games.schemas import Game

    return {
        "games": TableSpec(
            Game,
            primary_key="id",
            overrides={"platforms": {"nullable": False}},
        ),
        "achievements": TableSpec(
            Achievement,
            primary_key="achievement_id",
            foreign_keys={"game_id": "games (id) ON DELETE CASCADE"},
        ),
    }


# --- model -> schema ----------------------------------------------------------


def _is_json_type(kind) -> bool:
    return get_origin(kind) in (list, dict, set, tuple) or (
        isinstance(kind, type) and issubclass(kind, BaseModel)
    )


def _column_type(annotation) -> tuple[str, bool, list[str] | None, bool]:
    """Return (sql_type, optional, enum_values, is_json) for a field annotation."""
    if get_origin(annotation) in (Union, types.UnionType):
        kinds = get_args(annotation)
    else:
        kinds = (annotation,)
    optional = type(None) in kinds
    kinds = [kind for kind in kinds if kind is not type(None)]

    if any(_is_json_type(kind) for kind in kinds):
        return "TEXT", optional, None, True
    if all(kind is bool for kind in kinds):
        return "BOOLEAN", optional, None, False
    if all(kind is int for kind in kinds):
        return "INTEGER", optional, None, False
    if all(kind in (int, float) for kind in kinds):
        return "REAL", optional, None, False
    if len(kinds) == 1 and isinstance(kinds[0], type) and issubclass(kinds[0], enum.Enum):
        return "TEXT", optional, [str(member.value) for member in kinds[0]], False
    return "TEXT", optional, None, False


def _sql_literal(value) -> str | None:
    if isinstance(value, enum.Enum):
        value = value.value
    if value is None or value is PydanticUndefined or value == "":
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def build_schema(specs: dict[str, TableSpec] | None = None) -> dict:
    specs = table_specs() if specs is None else specs
    tables = {}
    for table_name, spec in specs.items():
        columns = [{"name": spec.primary_key, "type": "INTEGER", "primary_key": True}]
        for name, model_field in spec.model.model_fields.items():
            if name == spec.primary_key:
                continue
            sql_type, optional, enum_values, is_json = _column_type(model_field.annotation)
            column = {
                "name": name,
                "type": sql_type,
                "nullable": optional or is_json,
                "default": _sql_literal(model_field.default),
            }
            if enum_values is not None:
                column["enum"] = enum_values
            if name in spec.foreign_keys:
                column["references"] = spec.foreign_keys[name]
            column.update(spec.overrides.get(name, {}))
            columns.append(column)
        tables[table_name] = {"columns": columns}
    return {"tables": tables}


# --- schema -> SQL ------------------------------------------------------------


def column_sql(column: dict) -> str:
    if column.get("primary_key"):
        return f"{column['name']} INTEGER PRIMARY KEY AUTOINCREMENT"
    parts = [column["name"], column["type"], "NULL" if column["nullable"] else "NOT NULL"]
    if column.get("default") is not None:
        parts.append(f"DEFAULT {column['default']}")
    return " ".join(parts)


def create_table_sql(table_name: str, table: dict) -> str:
    lines = [column_sql(column) for column in table["columns"]]
    lines += [
        f"FOREIGN KEY ({column['name']}) REFERENCES {column['references']}"
        for column in table["columns"]
        if column.get("references")
    ]
    body = ",\n    ".join(lines)
    return f"CREATE TABLE IF NOT EXISTS {table_name} (\n    {body}\n)"


def _structure(column: dict) -> tuple:
    return tuple(
        column.get(key) for key in ("type", "nullable", "default", "primary_key", "references")
    )


def _rebuild_table_sql(table_name: str, table: dict, copied: dict[str, str]) -> list[str]:
    """SQLite cannot alter a column in place, so copy the rows into a new table."""
    new_name = f"{table_name}__new"
    targets = ", ".join(copied)
    sources = ", ".join(copied.values())
    return [
        create_table_sql(new_name, table).replace(" IF NOT EXISTS", "", 1),
        f"INSERT INTO {new_name} ({targets})\nSELECT {sources} FROM {table_name}",
        f"DROP TABLE {table_name}",
        f"ALTER TABLE {new_name} RENAME TO {table_name}",
    ]


def diff_schemas(
    old: dict,
    new: dict,
    allow_drop: bool = False,
    renames: dict[str, dict[str, str]] | None = None,
) -> tuple[list[str], list[str]]:
    """Return (statements, notes) that turn the `old` schema into the `new` one."""
    renames = renames or {}
    statements: list[str] = []
    notes: list[str] = []
    old_tables, new_tables = old["tables"], new["tables"]

    for table_name in old_tables.keys() - new_tables.keys():
        if not allow_drop:
            raise MigrationError(
                f"Table '{table_name}' was removed. Re-run with --allow-drop to delete it and its data."
            )
        statements.append(f"DROP TABLE IF EXISTS {table_name}")
        notes.append(f"- table {table_name}")

    for table_name, table in new_tables.items():
        if table_name not in old_tables:
            statements.append(create_table_sql(table_name, table))
            notes.append(f"+ table {table_name}")
            continue

        table_renames = renames.get(table_name, {})
        old_columns = {column["name"]: column for column in old_tables[table_name]["columns"]}
        for old_name, new_name in table_renames.items():
            if old_name not in old_columns:
                raise MigrationError(f"Cannot rename unknown column {table_name}.{old_name}")
            old_columns[new_name] = {**old_columns.pop(old_name), "name": new_name}
            statements.append(f"ALTER TABLE {table_name} RENAME COLUMN {old_name} TO {new_name}")
            notes.append(f"~ {table_name}.{old_name} renamed to {new_name}")

        new_columns = {column["name"]: column for column in table["columns"]}
        added = [name for name in new_columns if name not in old_columns]
        dropped = [name for name in old_columns if name not in new_columns]
        changed = [
            name
            for name in new_columns
            if name in old_columns and _structure(new_columns[name]) != _structure(old_columns[name])
        ]

        if dropped and not allow_drop:
            names = ", ".join(f"{table_name}.{name}" for name in dropped)
            raise MigrationError(
                f"Fields removed: {names}. If this is a rename, use --rename "
                f"{table_name}.<old>=<new>; otherwise re-run with --allow-drop "
                "(the data in these columns will be deleted)."
            )
        for name in added:
            column = new_columns[name]
            if not column["nullable"] and column.get("default") is None:
                raise MigrationError(
                    f"New field {table_name}.{name} is required and has no default, so "
                    "existing rows would have no value. Give the field a default or make it optional."
                )

        for name in changed:
            notes.append(f"~ {table_name}.{name}: {column_sql(old_columns[name])} -> {column_sql(new_columns[name])}")
        for name in dropped:
            notes.append(f"- {table_name}.{name}")
        for name in added:
            notes.append(f"+ {table_name}.{column_sql(new_columns[name])}")

        if changed:
            copied = {}
            for name, column in new_columns.items():
                if name not in old_columns:
                    continue
                if not column.get("nullable", True) and column.get("default") is not None:
                    copied[name] = f"COALESCE({name}, {column['default']})"
                else:
                    copied[name] = name
            statements += _rebuild_table_sql(table_name, table, copied)
        else:
            statements += [f"ALTER TABLE {table_name} DROP COLUMN {name}" for name in dropped]
            statements += [
                f"ALTER TABLE {table_name} ADD COLUMN {column_sql(new_columns[name])}"
                for name in added
            ]

        for name, column in new_columns.items():
            old_values = old_columns.get(name, {}).get("enum")
            removed_values = sorted(set(old_values or []) - set(column.get("enum") or []))
            if old_values and removed_values and name not in dropped:
                values = ", ".join(f"'{value}'" for value in removed_values)
                notes.append(
                    f"! {table_name}.{name} no longer accepts {values}. Existing rows may need updating, e.g.:\n"
                    f"--   UPDATE {table_name} SET {name} = NULL WHERE {name} IN ({values});"
                )

    return statements, notes


# --- migration files ----------------------------------------------------------


def _migration_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(path for path in directory.iterdir() if MIGRATION_PATTERN.match(path.name))


def load_snapshot(directory: Path = MIGRATIONS_DIRECTORY) -> dict | None:
    path = directory / SNAPSHOT_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_snapshot(schema: dict, directory: Path = MIGRATIONS_DIRECTORY) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / SNAPSHOT_FILE).write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "auto"


def make_migration(
    schema: dict,
    directory: Path = MIGRATIONS_DIRECTORY,
    name: str = "auto",
    allow_drop: bool = False,
    renames: dict[str, dict[str, str]] | None = None,
) -> Path | None:
    """Write a migration for the changes since the last snapshot.

    Returns the new file, or None when there is nothing to migrate. The first
    run only records the current schema as the baseline.
    """
    snapshot = load_snapshot(directory)
    if snapshot is None:
        save_snapshot(schema, directory)
        return None
    if snapshot == schema:
        return None

    statements, notes = diff_schemas(snapshot, schema, allow_drop, renames)
    save_snapshot(schema, directory)
    if not statements and not any(note.startswith("!") for note in notes):
        return None

    files = _migration_files(directory)
    number = int(MIGRATION_PATTERN.match(files[-1].name).group(1)) + 1 if files else 1
    path = directory / f"{number:04d}_{_slug(name)}.sql"
    header = [
        f"-- Migration {path.stem}",
        f"-- Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC by backend/database/migrate.py",
        "--",
        *(f"-- {line}" for note in notes for line in note.splitlines()),
    ]
    body = "".join(f"{statement};\n\n" for statement in statements)
    path.write_text("\n".join(header) + "\n\n" + body, encoding="utf-8")
    return path


def split_statements(sql: str) -> list[str]:
    statements, current = [], ""
    for line in sql.splitlines():
        if not current and (not line.strip() or line.lstrip().startswith("--")):
            continue
        current += line + "\n"
        if sqlite3.complete_statement(current):
            statements.append(current.strip().rstrip(";"))
            current = ""
    if current.strip():
        raise MigrationError(f"Incomplete SQL statement: {current.strip()[:80]}")
    return statements


# --- applying -----------------------------------------------------------------


def _applied_migrations(connection: sqlite3.Connection) -> set[str]:
    connection.execute(
        f"CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    connection.commit()
    return {row[0] for row in connection.execute(f"SELECT name FROM {MIGRATIONS_TABLE}")}


def pending_migrations(
    connection: sqlite3.Connection, directory: Path = MIGRATIONS_DIRECTORY
) -> list[Path]:
    applied = _applied_migrations(connection)
    return [path for path in _migration_files(directory) if path.stem not in applied]


def apply_migrations(
    connection: sqlite3.Connection, directory: Path = MIGRATIONS_DIRECTORY
) -> list[str]:
    """Apply every pending migration, each one in its own transaction."""
    applied = []
    for path in pending_migrations(connection, directory):
        statements = split_statements(path.read_text(encoding="utf-8"))
        connection.commit()
        # Off while tables are rebuilt, otherwise DROP TABLE cascades to child rows.
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            connection.execute("BEGIN")
            for statement in statements:
                try:
                    connection.execute(statement)
                except sqlite3.OperationalError as error:
                    # The column may already exist on databases created after the model change.
                    if "duplicate column name" not in str(error):
                        raise MigrationError(f"{path.name}: {error}\n{statement}") from error
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise MigrationError(f"{path.name}: leaves broken foreign keys: {violations[:5]}")
            connection.execute(
                f"INSERT INTO {MIGRATIONS_TABLE} (name, applied_at) VALUES (?, ?)",
                (path.stem, datetime.now(timezone.utc).isoformat()),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.execute("PRAGMA foreign_keys = ON")
        applied.append(path.stem)
    return applied


# --- CLI ----------------------------------------------------------------------


def _parse_renames(values: list[str]) -> dict[str, dict[str, str]]:
    renames: dict[str, dict[str, str]] = {}
    for value in values:
        match = re.fullmatch(r"(\w+)\.(\w+)=(\w+)", value)
        if match is None:
            raise MigrationError(f"Invalid --rename '{value}', expected table.old=new")
        table_name, old_name, new_name = match.groups()
        renames.setdefault(table_name, {})[old_name] = new_name
    return renames


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.database.migrate", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("make", help="generate a migration from the schema changes")
    make.add_argument("-n", "--name", default="auto", help="short description used in the file name")
    make.add_argument("--allow-drop", action="store_true", help="allow dropping removed fields/tables")
    make.add_argument("--rename", action="append", default=[], metavar="TABLE.OLD=NEW", help="treat a removed+added field as a rename")
    commands.add_parser("migrate", help="apply pending migrations to the database")
    commands.add_parser("check", help="fail if the schemas changed without a migration")
    commands.add_parser("status", help="list migrations and whether they are applied")
    args = parser.parse_args(argv)

    from backend.database import database

    try:
        if args.command == "make":
            had_snapshot = load_snapshot() is not None
            path = make_migration(build_schema(), name=args.name, allow_drop=args.allow_drop, renames=_parse_renames(args.rename))
            if path is not None:
                print(f"Created {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")
                print(path.read_text(encoding="utf-8"))
            elif not had_snapshot:
                print(f"Recorded the current schema as the baseline in {MIGRATIONS_DIRECTORY / SNAPSHOT_FILE}")
            else:
                print("No schema changes.")
        elif args.command == "migrate":
            database.initialize_database()
            print("Database is up to date.")
        elif args.command == "check":
            snapshot = load_snapshot()
            if snapshot != build_schema():
                print("The schemas changed but no migration was generated. Run: npm run db:make -- -n <description>")
                return 1
            print("Schemas and migrations are in sync.")
        elif args.command == "status":
            with closing(database.get_connection()) as connection:
                pending = {path.stem for path in pending_migrations(connection)}
            for path in _migration_files(MIGRATIONS_DIRECTORY):
                print(f"[{' ' if path.stem in pending else 'x'}] {path.stem}")
            if not _migration_files(MIGRATIONS_DIRECTORY):
                print("No migrations yet.")
    except MigrationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
