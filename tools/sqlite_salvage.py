#!/usr/bin/env python3
"""Salvage rows out of a corrupt SQLite database, table by table.

Written for the case where ``sqlite3 .recover`` dies (e.g. sqlite 3.40.1
raising "SQL logic error" in the writable_schema stage and emitting an empty
dump). Instead of relying on the shell's recovery extension, this walks each
table's rowid b-tree with the stdlib ``sqlite3`` module and binary-searches
around damaged pages, so a bad page costs the rows on that page rather than
the rest of the table.

The source database is only ever opened read-only and immutable, so it is
never written to, locked, or checkpointed.

Typical use:

    python3 tools/sqlite_salvage.py broken.db rescued.db \\
        --segment messages:session_id --report rescue.json

Exit codes: 0 = every table read cleanly, 2 = salvaged with losses,
1 = could not proceed.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.parse
from dataclasses import dataclass, field

# Errors raised when a page fails to parse. OperationalError shows up too,
# for example "database disk image is malformed" surfacing mid-statement.
CORRUPTION_ERRORS = (sqlite3.DatabaseError,)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def open_source(path: str) -> sqlite3.Connection:
    """Open the damaged database read-only, immutable, tolerant of bad text."""
    if not os.path.exists(path):
        raise SystemExit(f"source database not found: {path}")
    wal = path + "-wal"
    if os.path.exists(wal) and os.path.getsize(wal) > 0:
        log(f"  ! {os.path.basename(wal)} is non-empty ({os.path.getsize(wal)} bytes) and "
            "immutable=1 ignores it; checkpoint a COPY of the database first or "
            "those transactions will not be salvaged")
    uri = "file:" + urllib.parse.quote(os.path.abspath(path)) + "?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True, timeout=30, isolation_level=None)
    # Corrupt pages routinely contain byte sequences that are not valid UTF-8.
    # Replacing instead of raising keeps an otherwise intact row salvageable.
    con.text_factory = lambda b: b.decode("utf-8", "replace")
    return con


def open_dest(path: str, overwrite: bool) -> sqlite3.Connection:
    if os.path.exists(path):
        if not overwrite:
            raise SystemExit(f"destination already exists (use --force): {path}")
        os.unlink(path)
    for suffix in ("-wal", "-shm"):
        stale = path + suffix
        if os.path.exists(stale):
            os.unlink(stale)
    con = sqlite3.connect(path, timeout=30, isolation_level=None)
    con.text_factory = lambda b: b.decode("utf-8", "replace")
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA foreign_keys=OFF")
    return con


@dataclass
class TableReport:
    name: str
    rows: int = 0
    quarantined: int = 0
    skipped_spans: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    without_rowid: bool = False
    segments_total: int = 0
    segments_damaged: int = 0
    seconds: float = 0.0

    @property
    def clean(self) -> bool:
        return not self.skipped_spans and not self.errors and not self.quarantined


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------

def read_schema(con: sqlite3.Connection) -> list[dict]:
    """Read sqlite_master, falling back to a row-by-row walk if it is damaged."""
    sql = "SELECT type, name, tbl_name, sql FROM sqlite_master"
    try:
        rows = con.execute(sql).fetchall()
    except CORRUPTION_ERRORS as exc:
        log(f"  ! sqlite_master scan failed ({exc}); retrying row by row")
        rows = []
        cur = con.execute(sql)
        while True:
            try:
                row = cur.fetchone()
            except CORRUPTION_ERRORS as inner:
                log(f"  ! giving up on remaining sqlite_master rows: {inner}")
                break
            if row is None:
                break
            rows.append(row)
    return [
        {"type": r[0], "name": r[1], "tbl_name": r[2], "sql": r[3]}
        for r in rows
        if r[1] and not str(r[1]).startswith("sqlite_")
    ]


def columns_of(con: sqlite3.Connection, table: str) -> list[str]:
    rows = con.execute(f'PRAGMA table_info("{esc(table)}")').fetchall()
    return [r[1] for r in rows]


def esc(ident: str) -> str:
    return ident.replace('"', '""')


def has_rowid(con: sqlite3.Connection, table: str, ddl: str | None) -> bool:
    if ddl and "without rowid" in " ".join(ddl.lower().split()):
        return False
    try:
        con.execute(f'SELECT rowid FROM "{esc(table)}" LIMIT 1').fetchone()
        return True
    except sqlite3.OperationalError:
        return False
    except CORRUPTION_ERRORS:
        # Corrupt, but it does have a rowid or the parser would have refused.
        return True


def create_table(dest: sqlite3.Connection, table: str, ddl: str | None,
                 cols: list[str]) -> None:
    if ddl:
        try:
            dest.execute(ddl)
            return
        except sqlite3.Error as exc:
            log(f"  ! original DDL rejected for {table} ({exc}); using a loose schema")
    body = ", ".join(f'"{esc(c)}"' for c in cols)
    dest.execute(f'CREATE TABLE "{esc(table)}" ({body})')


def ensure_quarantine(dest: sqlite3.Connection) -> None:
    dest.execute(
        "CREATE TABLE IF NOT EXISTS _salvage_quarantine ("
        "  tbl TEXT, rowid_hint INTEGER, reason TEXT, payload TEXT)"
    )


# --------------------------------------------------------------------------
# reading around damage
# --------------------------------------------------------------------------

class Reader:
    """Reads one table, stepping over pages that fail to parse."""

    # Consecutive one-row reads before going back to bulk reads.
    SINGLE_STEP_LIMIT = 64

    def __init__(self, con: sqlite3.Connection, table: str, cols: list[str],
                 predicate: str = "", params: tuple = (), chunk: int = 2000,
                 max_probes: int = 4096):
        self.con = con
        self.table = table
        self.cols = cols
        self.predicate = predicate
        self.params = params
        self.chunk = chunk
        self.max_probes = max_probes
        self.probes = 0
        self.skipped_spans: list[tuple[int, int]] = []
        self.errors: list[str] = []

    def _where(self, extra: str) -> str:
        parts = [p for p in (extra, self.predicate) if p]
        return (" WHERE " + " AND ".join(parts)) if parts else ""

    def _select(self, extra: str, limit: int) -> str:
        cols = ", ".join(f'"{esc(c)}"' for c in self.cols)
        return (
            f'SELECT rowid, {cols} FROM "{esc(self.table)}"'
            f"{self._where(extra)} ORDER BY rowid LIMIT {limit}"
        )

    def _probe_from(self, start: int) -> tuple[bool, tuple | None]:
        """Read the first row at or after ``start``.

        Returns ``(readable, row)``; ``(True, None)`` means the read worked and
        there is simply nothing left at or after ``start``.
        """
        self.probes += 1
        sql = self._select("rowid >= ?", 1)
        try:
            row = self.con.execute(sql, (start,) + self.params).fetchone()
            return True, row
        except CORRUPTION_ERRORS as exc:
            self._note(exc)
            return False, None

    def _note(self, exc: BaseException) -> None:
        text = f"{type(exc).__name__}: {exc}"
        if text not in self.errors and len(self.errors) < 20:
            self.errors.append(text)

    def _next_readable(self, after: int, ceiling: int) -> int | None:
        """Smallest rowid > ``after`` that can be read, or None if none remain.

        Probes forward with a doubling step until a read succeeds, then binary
        searches back into the damaged span so the loss stays as small as the
        b-tree allows.
        """
        step = 1
        landed: int | None = None
        last_bad = after
        while True:
            if self.probes >= self.max_probes:
                self.errors.append("probe budget exhausted; stopped early")
                return None
            probe = after + step
            if probe > ceiling:
                probe = ceiling
            ok, _ = self._probe_from(probe)
            if ok:
                landed = probe
                break
            last_bad = probe
            if probe >= ceiling:
                return None
            step *= 2

        lo, hi = last_bad + 1, landed
        while lo < hi:
            if self.probes >= self.max_probes:
                break
            mid = (lo + hi) // 2
            ok, _ = self._probe_from(mid)
            if ok:
                hi = mid
            else:
                lo = mid + 1
        if lo - 1 >= after + 1:
            self.skipped_spans.append((after + 1, lo - 1))
        return lo

    def rows(self):
        """Yield ``(rowid, values)`` for every row that can be read."""
        try:
            ceiling = self.con.execute(
                f'SELECT max(rowid) FROM "{esc(self.table)}"{self._where("")}',
                self.params,
            ).fetchone()[0]
        except CORRUPTION_ERRORS as exc:
            self._note(exc)
            ceiling = None
        if ceiling is None:
            # Either an empty table or max() itself walked into damage. Use the
            # widest possible rowid so the forward probe can still find data.
            ceiling = 2 ** 63 - 1

        cursor_at = -(2 ** 63)
        while True:
            sql = self._select("rowid > ?", self.chunk)
            got_any = False
            try:
                cur = self.con.execute(sql, (cursor_at,) + self.params)
                while True:
                    row = cur.fetchone()
                    if row is None:
                        break
                    got_any = True
                    cursor_at = row[0]
                    yield row[0], row[1:]
            except CORRUPTION_ERRORS as exc:
                self._note(exc)
                # A bulk read gives up on the whole chunk, but the rows sitting
                # just before the bad page are still individually readable.
                # Single-step them out first; only once a one-row read also
                # fails have we truly reached the damage and can jump over it.
                stepped = 0
                while stepped < self.SINGLE_STEP_LIMIT:
                    ok, row = self._probe_from(cursor_at + 1)
                    if not ok:
                        break
                    if row is None:
                        return
                    cursor_at = row[0]
                    stepped += 1
                    yield row[0], row[1:]
                else:
                    # Still making progress one row at a time; retry in bulk.
                    continue
                nxt = self._next_readable(cursor_at, ceiling)
                if nxt is None:
                    return
                cursor_at = nxt - 1
                continue
            if not got_any:
                return


# --------------------------------------------------------------------------
# copying
# --------------------------------------------------------------------------

def segment_keys(src: sqlite3.Connection, table: str, column: str) -> list | None:
    """Distinct values of ``column``, used to salvage a table in slices."""
    sql = f'SELECT DISTINCT "{esc(column)}" FROM "{esc(table)}" ORDER BY 1'
    keys: list = []
    try:
        cur = src.execute(sql)
    except CORRUPTION_ERRORS as exc:
        log(f"  ! cannot list {table}.{column} segments ({exc}); scanning whole table")
        return None
    while True:
        try:
            row = cur.fetchone()
        except CORRUPTION_ERRORS as exc:
            log(f"  ! segment list truncated ({exc}); {len(keys)} keys usable")
            break
        if row is None:
            break
        keys.append(row[0])
    return keys


def copy_table(src: sqlite3.Connection, dest: sqlite3.Connection, table: str,
               ddl: str | None, segment_col: str | None, chunk: int,
               max_probes: int) -> TableReport:
    started = time.time()
    rep = TableReport(name=table)
    cols = columns_of(src, table)
    if not cols:
        rep.errors.append("no columns readable from PRAGMA table_info")
        rep.seconds = time.time() - started
        return rep

    create_table(dest, table, ddl, cols)
    rowid_table = has_rowid(src, table, ddl)
    rep.without_rowid = not rowid_table

    placeholders = ", ".join("?" * len(cols))
    collist = ", ".join(f'"{esc(c)}"' for c in cols)
    if rowid_table:
        insert = (
            f'INSERT OR IGNORE INTO "{esc(table)}" (rowid, {collist}) '
            f"VALUES (?, {placeholders})"
        )
    else:
        insert = f'INSERT OR IGNORE INTO "{esc(table)}" ({collist}) VALUES ({placeholders})'

    def emit(rowid, values):
        payload = (rowid,) + tuple(values) if rowid_table else tuple(values)
        try:
            dest.execute(insert, payload)
            rep.rows += 1
        except sqlite3.Error as exc:
            ensure_quarantine(dest)
            dest.execute(
                "INSERT INTO _salvage_quarantine (tbl, rowid_hint, reason, payload)"
                " VALUES (?, ?, ?, ?)",
                (table, rowid, str(exc), json.dumps(values, default=repr)),
            )
            rep.quarantined += 1

    if not rowid_table:
        # No rowid b-tree to walk; take what a plain scan gives us.
        try:
            cur = src.execute(f'SELECT {collist} FROM "{esc(table)}"')
            while True:
                row = cur.fetchone()
                if row is None:
                    break
                emit(None, row)
        except CORRUPTION_ERRORS as exc:
            rep.errors.append(f"{type(exc).__name__}: {exc}")
        rep.seconds = time.time() - started
        return rep

    keys = segment_keys(src, table, segment_col) if segment_col else None

    if keys is None:
        reader = Reader(src, table, cols, chunk=chunk, max_probes=max_probes)
        for rowid, values in reader.rows():
            emit(rowid, values)
        rep.skipped_spans = reader.skipped_spans
        rep.errors.extend(reader.errors)
    else:
        rep.segments_total = len(keys)
        for key in keys:
            predicate = (
                f'"{esc(segment_col)}" IS NULL' if key is None
                else f'"{esc(segment_col)}" = ?'
            )
            params = () if key is None else (key,)
            reader = Reader(src, table, cols, predicate, params,
                            chunk=chunk, max_probes=max_probes)
            before = rep.rows
            for rowid, values in reader.rows():
                emit(rowid, values)
            if reader.skipped_spans or reader.errors:
                rep.segments_damaged += 1
                rep.skipped_spans.extend(reader.skipped_spans)
                for err in reader.errors:
                    tagged = f"[{segment_col}={key!r}] {err}"
                    if len(rep.errors) < 40:
                        rep.errors.append(tagged)
                log(f"    - {segment_col}={key!r}: {rep.rows - before} rows, "
                    f"{len(reader.skipped_spans)} damaged span(s)")

    rep.seconds = time.time() - started
    return rep


def replay_objects(dest: sqlite3.Connection, schema: list[dict],
                   kinds: tuple[str, ...]) -> list[str]:
    failures = []
    for obj in schema:
        if obj["type"] not in kinds or not obj["sql"]:
            continue
        try:
            dest.execute(obj["sql"])
        except sqlite3.Error as exc:
            failures.append(f'{obj["type"]} {obj["name"]}: {exc}')
    return failures


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="corrupt database (opened read-only)")
    ap.add_argument("dest", help="new database to write salvaged rows into")
    ap.add_argument("--segment", action="append", default=[], metavar="TABLE:COLUMN",
                    help="salvage TABLE one COLUMN value at a time, so damage in "
                         "one slice cannot cost the others (repeatable)")
    ap.add_argument("--tables", default="", help="comma-separated allowlist")
    ap.add_argument("--skip-tables", default="", help="comma-separated denylist")
    ap.add_argument("--chunk", type=int, default=2000, help="rows per read (default 2000)")
    ap.add_argument("--max-probes", type=int, default=4096,
                    help="per-scan budget for damage-boundary probes")
    ap.add_argument("--no-indexes", action="store_true",
                    help="do not recreate indexes/triggers/views afterwards")
    ap.add_argument("--report", metavar="PATH", help="write a JSON report here")
    ap.add_argument("--force", action="store_true", help="overwrite dest if present")
    args = ap.parse_args(argv)

    segments = {}
    for spec in args.segment:
        if ":" not in spec:
            raise SystemExit(f"--segment needs TABLE:COLUMN, got {spec!r}")
        tbl, col = spec.split(":", 1)
        segments[tbl] = col

    allow = {t.strip() for t in args.tables.split(",") if t.strip()}
    deny = {t.strip() for t in args.skip_tables.split(",") if t.strip()}

    log(f"sqlite runtime: {sqlite3.sqlite_version} (python {sys.version.split()[0]})")
    src = open_source(args.source)
    dest = open_dest(args.dest, args.force)

    try:
        quick = src.execute("PRAGMA quick_check(20)").fetchall()
        quick_lines = [r[0] for r in quick]
    except CORRUPTION_ERRORS as exc:
        quick_lines = [f"quick_check failed: {exc}"]
    log("quick_check: " + "; ".join(quick_lines[:5]))

    schema = read_schema(src)
    tables = [o for o in schema if o["type"] == "table"]
    log(f"tables found: {len(tables)}")

    reports: list[TableReport] = []
    for obj in tables:
        name = obj["name"]
        if allow and name not in allow:
            continue
        if name in deny:
            continue
        seg = segments.get(name)
        log(f"  * {name}" + (f" (segmented by {seg})" if seg else ""))
        try:
            rep = copy_table(src, dest, name, obj["sql"], seg, args.chunk,
                             args.max_probes)
        except sqlite3.Error as exc:
            rep = TableReport(name=name, errors=[f"aborted: {exc}"])
        reports.append(rep)
        lost = sum(hi - lo + 1 for lo, hi in rep.skipped_spans)
        log(f"    {rep.rows} rows in {rep.seconds:.1f}s"
            + (f", {len(rep.skipped_spans)} damaged span(s) (~{lost} rowids)"
               if rep.skipped_spans else "")
            + (f", {rep.quarantined} quarantined" if rep.quarantined else ""))

    index_failures: list[str] = []
    if not args.no_indexes:
        index_failures = replay_objects(dest, schema, ("index", "trigger", "view"))
        for failure in index_failures:
            log(f"  ! could not recreate {failure}")

    dest.commit()
    try:
        verdict = dest.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.Error as exc:
        verdict = f"check failed: {exc}"
    log(f"destination integrity_check: {verdict}")
    dest.close()
    src.close()

    total_rows = sum(r.rows for r in reports)
    damaged = [r for r in reports if not r.clean]
    log(f"\nsalvaged {total_rows} rows across {len(reports)} tables; "
        f"{len(damaged)} table(s) had damage")

    if args.report:
        payload = {
            "source": os.path.abspath(args.source),
            "dest": os.path.abspath(args.dest),
            "sqlite_version": sqlite3.sqlite_version,
            "quick_check": quick_lines,
            "destination_integrity_check": verdict,
            "index_failures": index_failures,
            "total_rows": total_rows,
            "tables": [
                {
                    "name": r.name,
                    "rows": r.rows,
                    "quarantined": r.quarantined,
                    "without_rowid": r.without_rowid,
                    "skipped_spans": r.skipped_spans,
                    "skipped_rowids_estimate": sum(hi - lo + 1 for lo, hi in r.skipped_spans),
                    "segments_total": r.segments_total,
                    "segments_damaged": r.segments_damaged,
                    "errors": r.errors,
                    "seconds": round(r.seconds, 3),
                }
                for r in reports
            ],
        }
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        log(f"report written to {args.report}")

    return 2 if damaged else 0


if __name__ == "__main__":
    sys.exit(main())
