"""Tests for tools/sqlite_salvage.py against a genuinely corrupt database.

Builds a sessions/messages database, scribbles random bytes over real leaf
pages of the messages b-tree, and checks that the salvage tool recovers the
readable rows faithfully where a plain scan would abort.

Run: python -m pytest tests/ -q   (or)   python tests/test_sqlite_salvage.py
"""
import os
import random
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import sqlite_salvage

PAGE = 4096
SESSIONS = 40
SEED = 20250811


def _build(path, corrupt_fractions=()):
    """Create the fixture; optionally corrupt messages leaf pages in place."""
    random.seed(SEED)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute(f"PRAGMA page_size={PAGE}")
    con.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY, uuid TEXT UNIQUE, title TEXT)")
    con.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL,"
                " role TEXT, body TEXT, ts REAL)")
    con.execute("CREATE INDEX idx_messages_session ON messages(session_id)")
    con.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT) WITHOUT ROWID")

    con.executemany("INSERT INTO sessions VALUES (?,?,?)",
                    [(i, f"uuid-{i:04d}", f"session {i}") for i in range(1, SESSIONS + 1)])
    rows, mid = [], 1
    for sid in range(1, SESSIONS + 1):
        for _ in range(random.randint(30, 90)):
            rows.append((mid, sid, random.choice(["user", "assistant"]),
                         "x" * random.randint(200, 900), 1.7e9 + mid))
            mid += 1
    con.executemany("INSERT INTO messages VALUES (?,?,?,?,?)", rows)
    con.executemany("INSERT INTO meta VALUES (?,?)", [("schema_version", "9"), ("owner", "mcp")])
    con.commit()
    leaves = [r[0] for r in con.execute(
        "SELECT pageno FROM dbstat WHERE name='messages' AND pagetype='leaf' ORDER BY pageno")]
    con.close()

    hit = [leaves[int(len(leaves) * f)] for f in corrupt_fractions]
    with open(path, "r+b") as fh:
        for pno in hit:
            fh.seek((pno - 1) * PAGE)
            fh.write(bytes(random.getrandbits(8) for _ in range(PAGE)))
    return len(rows), hit


def _naive_scan_count(path):
    """Rows a straightforward dump would get before the corruption stops it."""
    con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    con.text_factory = lambda b: b.decode("utf-8", "replace")
    n = 0
    try:
        cur = con.execute("SELECT * FROM messages NOT INDEXED ORDER BY id")
        while cur.fetchone() is not None:
            n += 1
    except sqlite3.DatabaseError:
        pass
    finally:
        con.close()
    return n


def _fixture(tmpdir, fractions):
    broken = os.path.join(tmpdir, "broken.db")
    pristine = os.path.join(tmpdir, "pristine.db")
    total, hit = _build(broken, fractions)
    _build(pristine)
    return broken, pristine, total, hit


def _salvage(broken, tmpdir, *extra):
    out = os.path.join(tmpdir, "rescued.db")
    code = sqlite_salvage.main([broken, out, "--force", *extra])
    return out, code


def _rows(path, table):
    con = sqlite3.connect(path)
    con.text_factory = lambda b: b.decode("utf-8", "replace")
    try:
        return {r[0]: r for r in con.execute(f"SELECT * FROM {table}")}
    finally:
        con.close()


def test_salvage_beats_a_plain_scan_and_stays_faithful():
    with tempfile.TemporaryDirectory() as tmp:
        broken, pristine, total, hit = _fixture(tmp, (.15, .35, .55, .75, .92))
        naive = _naive_scan_count(broken)
        assert naive < total, "fixture is not actually corrupt"

        out, code = _salvage(broken, tmp, "--segment", "messages:session_id")
        assert code == 2, "damage should be reported via exit code 2"

        want = _rows(pristine, "messages")
        got = _rows(out, "messages")

        # Nothing invented, nothing altered: salvage must never fabricate rows.
        assert not (set(got) - set(want)), "salvage produced phantom rows"
        assert all(got[k] == want[k] for k in got), "salvage altered row contents"

        # Only the damaged pages should be lost, and far less than a plain scan.
        assert len(got) > naive * 2
        assert len(got) >= total * 0.95, f"recovered only {len(got)}/{total}"
        assert len(want) - len(got) <= 40 * len(hit), "lost more than the bad pages hold"


def test_undamaged_tables_come_through_whole():
    with tempfile.TemporaryDirectory() as tmp:
        broken, pristine, _, _ = _fixture(tmp, (.3, .7))
        out, _ = _salvage(broken, tmp, "--segment", "messages:session_id")

        assert _rows(out, "sessions") == _rows(pristine, "sessions")
        # WITHOUT ROWID tables take the plain-scan path; they must still copy.
        assert _rows(out, "meta") == _rows(pristine, "meta")

        con = sqlite3.connect(out)
        try:
            assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            names = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")}
            assert "idx_messages_session" in names, "indexes should be rebuilt"
        finally:
            con.close()


def test_works_without_segmenting():
    with tempfile.TemporaryDirectory() as tmp:
        broken, pristine, total, _ = _fixture(tmp, (.2, .5, .8))
        out, _ = _salvage(broken, tmp)
        got = _rows(out, "messages")
        assert not (set(got) - set(_rows(pristine, "messages")))
        assert len(got) >= total * 0.95


def test_clean_database_round_trips_exactly():
    with tempfile.TemporaryDirectory() as tmp:
        broken, pristine, total, _ = _fixture(tmp, ())
        out, code = _salvage(broken, tmp, "--segment", "messages:session_id")
        assert code == 0, "an intact database should report no damage"
        assert len(_rows(out, "messages")) == total
        assert _rows(out, "messages") == _rows(pristine, "messages")


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
