import copy
import sqlite3
from contextlib import closing

import pytest
from pydantic import BaseModel

import backend.database.database as database
import backend.database.migrate as migrate
from routes.games.schemas import GamesESRB


class Parent(BaseModel):
    name: str


class Child(BaseModel):
    title: str
    score: int | None = None
    rating: GamesESRB | None = None
    parent_id: int


def make_specs(child=Child):
    return {
        "parents": migrate.TableSpec(Parent, primary_key="id"),
        "children": migrate.TableSpec(
            child,
            primary_key="child_id",
            foreign_keys={"parent_id": "parents (id) ON DELETE CASCADE"},
        ),
    }


@pytest.fixture()
def migrations_dir(tmp_path):
    directory = tmp_path / "migrations"
    assert migrate.make_migration(migrate.build_schema(make_specs()), directory) is None
    return directory


@pytest.fixture()
def connection(tmp_path):
    with closing(sqlite3.connect(tmp_path / "test.db")) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        schema = migrate.build_schema(make_specs())
        for table_name, table in schema["tables"].items():
            connection.execute(migrate.create_table_sql(table_name, table))
        connection.execute("INSERT INTO parents (name) VALUES ('p')")
        connection.execute("INSERT INTO children (title, score, parent_id) VALUES ('c', 5, 1)")
        connection.commit()
        yield connection


def columns(connection, table_name):
    return {row[1]: row for row in connection.execute(f"PRAGMA table_info({table_name})")}


# --- the real schemas ----------------------------------------------------------


def test_models_have_a_migration_for_every_change():
    assert migrate.load_snapshot() == migrate.build_schema(), (
        "The Pydantic schemas changed without a migration. Run: npm run db:make -- -n <description>"
    )


def test_model_tables_match_initialize_database(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    database.initialize_database()

    with closing(database.get_connection()) as connection:
        for table_name, table in migrate.build_schema()["tables"].items():
            assert set(columns(connection, table_name)) == {column["name"] for column in table["columns"]}


def test_initialize_database_records_applied_migrations(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "test.db")
    database.initialize_database()

    with closing(database.get_connection()) as connection:
        assert migrate.pending_migrations(connection) == []


# --- generating ----------------------------------------------------------------


def test_build_schema_maps_types_nullability_defaults_and_enums():
    schema = migrate.build_schema(make_specs())
    children = {column["name"]: column for column in schema["tables"]["children"]["columns"]}

    assert migrate.column_sql(children["child_id"]) == "child_id INTEGER PRIMARY KEY AUTOINCREMENT"
    assert migrate.column_sql(children["title"]) == "title TEXT NOT NULL"
    assert migrate.column_sql(children["score"]) == "score INTEGER NULL"
    assert children["rating"]["enum"] == [member.value for member in GamesESRB]
    assert children["parent_id"]["references"] == "parents (id) ON DELETE CASCADE"


def test_first_run_records_baseline_without_a_migration(migrations_dir):
    assert (migrations_dir / migrate.SNAPSHOT_FILE).exists()
    assert migrate._migration_files(migrations_dir) == []


def test_no_changes_writes_nothing(migrations_dir):
    assert migrate.make_migration(migrate.build_schema(make_specs()), migrations_dir) is None


def test_added_field_generates_add_column(migrations_dir, connection):
    class ChildWithTags(Child):
        tags: list[str] = []
        level: int = 1

    path = migrate.make_migration(migrate.build_schema(make_specs(ChildWithTags)), migrations_dir, "add tags")

    assert path.name == "0001_add_tags.sql"
    sql = path.read_text()
    assert "ALTER TABLE children ADD COLUMN tags TEXT NULL;" in sql
    assert "ALTER TABLE children ADD COLUMN level INTEGER NOT NULL DEFAULT 1;" in sql
    assert migrate.apply_migrations(connection, migrations_dir) == ["0001_add_tags"]
    assert connection.execute("SELECT level FROM children").fetchone()[0] == 1
    assert migrate.apply_migrations(connection, migrations_dir) == []


def test_changed_field_rebuilds_table_and_keeps_rows(migrations_dir, connection):
    class ChildWithRequiredScore(Child):
        score: float = 0

    path = migrate.make_migration(migrate.build_schema(make_specs(ChildWithRequiredScore)), migrations_dir)
    migrate.apply_migrations(connection, migrations_dir)

    assert "CREATE TABLE children__new" in path.read_text()
    score = columns(connection, "children")["score"]
    assert (score[2], score[3]) == ("REAL", 1)
    assert connection.execute("SELECT title, score FROM children").fetchall() == [("c", 5.0)]
    connection.execute("DELETE FROM parents")
    assert connection.execute("SELECT COUNT(*) FROM children").fetchone()[0] == 0


def test_rebuilding_a_parent_table_does_not_cascade_deletes(migrations_dir, connection):
    class RenamedParent(BaseModel):
        name: str | None = None

    specs = make_specs()
    specs["parents"] = migrate.TableSpec(RenamedParent, primary_key="id")
    migrate.make_migration(migrate.build_schema(specs), migrations_dir)
    migrate.apply_migrations(connection, migrations_dir)

    assert connection.execute("SELECT COUNT(*) FROM children").fetchone()[0] == 1


def test_removed_field_requires_allow_drop(migrations_dir, connection):
    class ChildWithoutScore(BaseModel):
        title: str
        rating: GamesESRB | None = None
        parent_id: int

    schema = migrate.build_schema(make_specs(ChildWithoutScore))
    with pytest.raises(migrate.MigrationError, match="--allow-drop"):
        migrate.make_migration(schema, migrations_dir)
    assert migrate._migration_files(migrations_dir) == []

    path = migrate.make_migration(schema, migrations_dir, allow_drop=True)
    assert "ALTER TABLE children DROP COLUMN score;" in path.read_text()
    migrate.apply_migrations(connection, migrations_dir)
    assert "score" not in columns(connection, "children")


def test_rename_keeps_data(migrations_dir, connection):
    class ChildWithPoints(BaseModel):
        title: str
        points: int | None = None
        rating: GamesESRB | None = None
        parent_id: int

    path = migrate.make_migration(
        migrate.build_schema(make_specs(ChildWithPoints)),
        migrations_dir,
        renames={"children": {"score": "points"}},
    )
    migrate.apply_migrations(connection, migrations_dir)

    assert "RENAME COLUMN score TO points" in path.read_text()
    assert connection.execute("SELECT points FROM children").fetchone()[0] == 5


def test_required_field_without_default_is_refused(migrations_dir):
    class ChildWithRequiredField(Child):
        code: str

    with pytest.raises(migrate.MigrationError, match="no default"):
        migrate.make_migration(migrate.build_schema(make_specs(ChildWithRequiredField)), migrations_dir)


def test_new_model_creates_table(migrations_dir, connection):
    class Tag(BaseModel):
        label: str

    specs = make_specs()
    specs["tags"] = migrate.TableSpec(Tag, primary_key="tag_id")
    path = migrate.make_migration(migrate.build_schema(specs), migrations_dir)
    migrate.apply_migrations(connection, migrations_dir)

    assert "CREATE TABLE IF NOT EXISTS tags" in path.read_text()
    assert set(columns(connection, "tags")) == {"tag_id", "label"}


def test_removed_enum_values_add_a_warning(migrations_dir):
    old = migrate.build_schema(make_specs())
    new = copy.deepcopy(old)
    rating = next(column for column in new["tables"]["children"]["columns"] if column["name"] == "rating")
    rating["enum"] = [value for value in rating["enum"] if value != "ao"]

    path = migrate.make_migration(new, migrations_dir)

    assert "UPDATE children SET rating = NULL WHERE rating IN ('ao');" in path.read_text()


# --- applying ------------------------------------------------------------------


def test_apply_skips_columns_that_already_exist(migrations_dir, connection):
    (migrations_dir / "0001_manual.sql").write_text(
        "-- comment\nALTER TABLE children ADD COLUMN score INTEGER NULL;\n"
    )

    assert migrate.apply_migrations(connection, migrations_dir) == ["0001_manual"]


def test_failed_migration_is_rolled_back(migrations_dir, connection):
    (migrations_dir / "0001_broken.sql").write_text(
        "ALTER TABLE children ADD COLUMN extra TEXT NULL;\nSELECT * FROM missing_table;\n"
    )

    with pytest.raises(migrate.MigrationError, match="missing_table"):
        migrate.apply_migrations(connection, migrations_dir)
    assert "extra" not in columns(connection, "children")
    assert [path.stem for path in migrate.pending_migrations(connection, migrations_dir)] == ["0001_broken"]


def test_split_statements_handles_comments_and_semicolons_in_strings():
    sql = "-- header\n\nUPDATE t SET a = 'x;y';\n\nDROP TABLE t;\n"

    assert migrate.split_statements(sql) == ["UPDATE t SET a = 'x;y'", "DROP TABLE t"]


def test_cli_check_fails_when_schemas_drift(monkeypatch, capsys):
    monkeypatch.setattr(migrate, "load_snapshot", lambda: {"tables": {}})

    assert migrate.main(["check"]) == 1
    assert "db:make" in capsys.readouterr().out


def test_cli_rejects_bad_rename():
    with pytest.raises(migrate.MigrationError):
        migrate._parse_renames(["games-hours=hours"])
