"""Offline tests for the G789 bot skill catalog (no network / tokens needed).

Run: python tests/test_bot_skills.py   (or: python -m pytest tests/ -q)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from g789_bot.skills import Catalog, load_all  # noqa: E402


def test_loads_all_500():
    skills = load_all()
    assert len(skills) == 500, f"expected 500 skills, got {len(skills)}"


def test_ids_unique_and_well_formed():
    skills = load_all()
    ids = [s.id for s in skills]
    assert len(set(ids)) == 500
    assert all(s.id.startswith("S-") and s.num >= 1 for s in skills)
    assert all(s.body and s.name and s.category for s in skills)


def test_id_lookup_normalization():
    cat = Catalog()
    assert cat.get("S-001") is cat.get("1")
    assert cat.get("42").id == "S-042"
    assert cat.get("s-500").id == "S-500"
    assert cat.get("nope") is None


def test_category_filter():
    full = Catalog()
    filtered = Catalog(blocked_categories={"黄", "赌"})
    assert len(filtered) == len(full) - 60  # 30 in 黄 + 30 in 赌
    assert all(s.category not in {"黄", "赌"} for s in filtered.skills)


def test_search_matches_name_and_id():
    cat = Catalog()
    assert cat.search("S-100")[0].id == "S-100"
    assert any("购物" in s.name for s in cat.search("购物"))
    assert cat.search("") == []


def test_categories_sorted_by_count():
    cats = Catalog().categories()
    counts = [c for _, c in cats]
    assert counts == sorted(counts, reverse=True)
    assert sum(counts) == 500


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    print("PASS" if failures == 0 else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
