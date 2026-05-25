"""Offline tests for normalization, dedup/merge, filtering, parsing, export.

Run: python -m pytest tests/ -q   (or)   python tests/test_pipeline.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from group_export.api import ApiClient, ApiConfig
from group_export.export import write_csv, write_json
from group_export.filters import FilterConfig, ad_score, classify
from group_export.links import parse_group_link, parse_many
from group_export.models import Member
from group_export.pipeline import run


def test_normalization_varied_fields():
    a = Member.from_raw({"userId": 111, "userName": "@Alice", "firstName": "Al"})
    assert a.user_id == "111"
    assert a.username == "Alice"          # @ stripped
    assert a.full_name == "Al"
    b = Member.from_raw({"id": "222", "name": "Bob Builder", "messages": "57"})
    assert b.user_id == "222" and b.full_name == "Bob Builder" and b.message_count == 57


def test_dedup_and_merge():
    recs = [
        Member.from_raw({"id": 1, "username": "ada", "first_name": "Ada"}, group="G1"),
        Member.from_raw({"id": 1, "last_name": "Lovelace", "message_count": 10}, group="G2"),
        Member.from_raw({"id": 2, "username": "linus"}, group="G1"),
        Member.from_raw({"id": 2, "username": "linus"}, group="G1"),  # exact dup
    ]
    cfg = FilterConfig(filter_ads=False)
    kept, removed, stats = run(recs, cfg)
    assert stats.seen == 4
    assert stats.unique == 2          # ids 1 and 2 collapsed
    assert stats.merged == 2          # two extra records folded in
    ada = next(m for m in kept if m.user_id == "1")
    assert ada.username == "ada" and ada.last_name == "Lovelace" and ada.message_count == 10
    assert ada.groups == {"G1", "G2"}


def test_filter_no_username():
    recs = [
        Member.from_raw({"id": 1, "username": "good", "first_name": "Good"}),
        Member.from_raw({"id": 2, "first_name": "NoHandle"}),  # no username
    ]
    kept, removed, stats = run(recs, FilterConfig(filter_ads=False))
    assert stats.kept == 1
    assert stats.filtered.get("no_username") == 1


def test_filter_ads():
    cfg = FilterConfig()
    spam = Member.from_raw({"id": 9, "username": "promo", "first_name": "广告推广 t.me/xyz"})
    clean = Member.from_raw({"id": 10, "username": "realuser", "first_name": "Jane"})
    assert ad_score(spam, cfg) >= cfg.ad_threshold
    assert classify(spam, cfg) == "ad_marketing"
    assert classify(clean, cfg) is None


def test_filter_scam_and_bot():
    cfg = FilterConfig()
    scam = Member.from_raw({"id": 11, "username": "x", "is_scam": True})
    bot = Member.from_raw({"id": 12, "username": "mybot", "is_bot": True})
    assert classify(scam, cfg) in ("scam_or_fake", "ad_marketing")
    assert classify(bot, cfg) == "bot"


def test_extract_list_envelopes():
    # list at root
    lst, total = ApiClient._extract_list([{"id": 1}, {"id": 2}])
    assert len(lst) == 2
    # wrapped in data + total
    lst, total = ApiClient._extract_list({"total": 5, "data": [{"id": 1}]})
    assert len(lst) == 1 and total == 5
    # nested
    lst, total = ApiClient._extract_list({"result": {"items": [{"id": 1}, {"id": 2}]}})
    assert len(lst) == 2


def test_pagination_loop_with_fake_session(tmp_path=None):
    """Simulate a paged API by monkeypatching the session.request."""
    pages = {
        1: {"total": 5, "data": [{"id": 1, "username": "a"}, {"id": 2, "username": "b"}]},
        2: {"total": 5, "data": [{"id": 3, "username": "c"}, {"id": 4, "username": "d"}]},
        3: {"total": 5, "data": [{"id": 5, "username": "e"}]},
    }

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        def __init__(self, payload): self._p = payload
        def json(self): return self._p

    cfg = ApiConfig(
        base_url="http://x", token="t", endpoint="/members", method="GET",
        group_param="group_id", page_param="page", size_param="size",
        page_size=2, verbose=False,
    )
    client = ApiClient(cfg)

    def fake_request(method, url, **kw):
        page = kw.get("params", {}).get("page", 1)
        return FakeResp(pages.get(page, {"total": 5, "data": []}))

    client.session.request = fake_request  # type: ignore
    recs = client.fetch_members("G1")
    assert len(recs) == 5


def test_export_roundtrip(tmp_path=None):
    import tempfile
    recs = [Member.from_raw({"id": 1, "username": "a", "first_name": "Ann"})]
    kept, _, _ = run(recs, FilterConfig(filter_ads=False))
    d = tempfile.mkdtemp()
    cpath = os.path.join(d, "m.csv")
    jpath = os.path.join(d, "m.json")
    write_csv(kept, cpath)
    write_json(kept, jpath)
    with open(jpath, encoding="utf-8") as f:
        data = json.load(f)
    assert data[0]["username"] == "a"
    assert os.path.getsize(cpath) > 0


def test_parse_group_link():
    assert parse_group_link("https://t.me/somegroup") == "somegroup"
    assert parse_group_link("https://t.me/somegroup/123") == "somegroup"
    assert parse_group_link("@somegroup") == "somegroup"
    assert parse_group_link("-1001234567890") == "-1001234567890"
    assert parse_group_link("t.me/+AbCdEf123") == "+AbCdEf123"
    assert parse_group_link("https://t.me/joinchat/AbCdEf") == "joinchat/AbCdEf"
    assert parse_group_link("not a link !!! 中文") == ""   # garbage skipped


def test_parse_many_dedup_and_skip():
    groups, skipped = parse_many("https://t.me/g1\n@g1\n-100123, t.me/g2\nbad line!!!")
    assert groups == ["g1", "-100123", "g2"]    # @g1 deduped against g1
    assert skipped == ["bad line!!!"]


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
