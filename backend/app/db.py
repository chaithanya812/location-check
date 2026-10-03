"""SQLite storage using the standard library sqlite3 module.

Three tables:
  assessments  what the user asked for (label + address or lat/lon)
  runs         one fetch-and-score attempt for an assessment; a retry adds a new run
  factors      one row per factor per run: raw value, points, source, error

A factor that was unavailable is stored with value NULL and points NULL,
never 0, so a missing value can always be told apart from a real one.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    label       TEXT NOT NULL,
    address     TEXT,
    input_lat   REAL,
    input_lon   REAL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id    INTEGER NOT NULL REFERENCES assessments(id),
    created_at       TEXT NOT NULL,
    lat              REAL,
    lon              REAL,
    matched_address  TEXT,
    location_error   TEXT,
    score            INTEGER,
    coverage         INTEGER NOT NULL,
    verdict          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS factors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id),
    name        TEXT NOT NULL,
    label       TEXT NOT NULL,
    source      TEXT NOT NULL,
    unit        TEXT NOT NULL,
    rule        TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('ok', 'unavailable')),
    value       TEXT,
    points      INTEGER,
    max_points  INTEGER NOT NULL,
    error       TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    """Open a connection, commit if the block succeeds, always close.

    (sqlite3's own `with conn:` commits but does not close the connection.)
    """
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()  # closing without commit discards a half-done write


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def create_assessment(label: str, address, lat, lon) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO assessments (label, address, input_lat, input_lon, created_at) VALUES (?, ?, ?, ?, ?)",
            (label, address, lat, lon, now()),
        )
        return cur.lastrowid


def save_run(assessment_id: int, location: dict, result: dict) -> int:
    """Save one run and its factors in a single transaction."""
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO runs (assessment_id, created_at, lat, lon, matched_address,
                                 location_error, score, coverage, verdict)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (assessment_id, now(), location.get("lat"), location.get("lon"),
             location.get("matched_address"), location.get("error"),
             result["score"], result["coverage"], result["verdict"]),
        )
        run_id = cur.lastrowid
        for f in result["factors"]:
            conn.execute(
                """INSERT INTO factors (run_id, name, label, source, unit, rule, status,
                                        value, points, max_points, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, f["name"], f["label"], f["source"], f["unit"], f["rule"], f["status"],
                 # json.dumps keeps numbers as numbers and strings as strings.
                 None if f["value"] is None else json.dumps(f["value"]),
                 f["points"], f["max_points"], f["error"]),
            )
        return run_id


def get_assessment(assessment_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM assessments WHERE id = ?", (assessment_id,)).fetchone()
        if row is None:
            return None
        assessment = dict(row)
        runs = conn.execute(
            "SELECT * FROM runs WHERE assessment_id = ? ORDER BY id DESC", (assessment_id,)
        ).fetchall()
        assessment["runs"] = []
        for run in runs:
            run = dict(run)
            factor_rows = conn.execute("SELECT * FROM factors WHERE run_id = ? ORDER BY id", (run["id"],)).fetchall()
            run["factors"] = []
            for f in factor_rows:
                f = dict(f)
                f["value"] = None if f["value"] is None else json.loads(f["value"])
                run["factors"].append(f)
            assessment["runs"].append(run)
        return assessment


def list_assessments() -> list[dict]:
    """Every assessment with the score and verdict from its latest run."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT a.id, a.label, a.address, a.input_lat, a.input_lon, a.created_at,
                      r.score, r.coverage, r.verdict, r.created_at AS last_run_at,
                      (SELECT COUNT(*) FROM runs WHERE assessment_id = a.id) AS run_count
               FROM assessments a
               LEFT JOIN runs r ON r.id = (SELECT MAX(id) FROM runs WHERE assessment_id = a.id)
               ORDER BY a.id DESC"""
        ).fetchall()
        return [dict(r) for r in rows]
