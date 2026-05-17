from bot.utils import fmt_size, fmt_time, paginate, short
from datetime import datetime


def test_paginate_normal():
    data = list(range(50))
    chunk, page, pages = paginate(data, 1, per_page=20)
    assert len(chunk) == 20 and page == 1 and pages == 3
    chunk, page, pages = paginate(data, 3, per_page=20)
    assert len(chunk) == 10 and page == 3 and pages == 3


def test_paginate_clamp():
    data = list(range(5))
    chunk, page, pages = paginate(data, 999, per_page=20)
    assert page == 1 and pages == 1 and len(chunk) == 5


def test_paginate_empty():
    chunk, page, pages = paginate([], 1)
    assert chunk == [] and page == 1 and pages == 1


def test_short():
    assert short("abc") == "abc"
    assert short("a" * 50, length=10) == "aaaaaaaaaa…"
    assert short("hello\nworld", length=20) == "hello world"


def test_fmt_size():
    assert fmt_size(0) == "0.0B"
    assert fmt_size(500) == "500.0B"
    assert fmt_size(2048).endswith("KB")
    assert fmt_size(10 * 1024 * 1024).endswith("MB")


def test_fmt_time():
    assert fmt_time(None) == "—"
    out = fmt_time(datetime(2026, 5, 16, 12, 0))
    assert out == "2026-05-16 12:00"
