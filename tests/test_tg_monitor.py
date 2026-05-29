"""离线测试 tg_monitor 的核心纯逻辑（关键词匹配、点击去重/冷却、配置存读）。

不依赖 OCR / 鼠标 / GUI，可直接跑：
  python tests/test_tg_monitor.py        （或）   python -m pytest tests/ -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tg_monitor.config import MonitorConfig
from tg_monitor.matcher import OcrBox, find_hits, KeywordMatcher, ClickGuard, pick_best


def _box(text, left=100, top=100, w=60, h=20, conf=0.9):
    return OcrBox(text=text, box=(left, top, w, h), confidence=conf)


def test_ocrbox_center():
    b = OcrBox(text="领取", box=(100, 200, 60, 20))
    assert b.center == (130, 210)


def test_find_hits_basic_chinese():
    boxes = [_box("点击领取奖励"), _box("无关文字"), _box("立即领取", left=300)]
    hits = find_hits(boxes, ["领取"])
    assert len(hits) == 2
    assert hits[0].keyword == "领取"
    assert hits[0].x == 130 and hits[0].y == 110     # 第一个框中心


def test_find_hits_case_insensitive_english():
    boxes = [_box("Click CLAIM now")]
    hits = find_hits(boxes, ["claim"])
    assert len(hits) == 1


def test_find_hits_multiple_keywords_one_per_box():
    boxes = [_box("领取红包")]
    hits = find_hits(boxes, ["领取", "红包"])
    assert len(hits) == 1                              # 一段文字命中算一次


def test_find_hits_min_confidence():
    boxes = [_box("领取", conf=0.2), _box("领取", left=300, conf=0.95)]
    hits = find_hits(boxes, ["领取"], min_confidence=0.5)
    assert len(hits) == 1
    assert hits[0].x == 330


def test_keyword_matcher_wrapper():
    m = KeywordMatcher(["领取"], min_confidence=0.0)
    assert len(m.match([_box("领取")])) == 1
    assert len(m.match([_box("别的")])) == 0


def test_pick_best_by_confidence():
    h = pick_best(find_hits([_box("领取", conf=0.6), _box("领取", left=300, conf=0.99)], ["领取"]))
    assert h is not None and h.x == 330


def test_click_guard_dedupe_same_spot():
    g = ClickGuard(cooldown=10, dedupe_radius=40)
    assert g.should_click(500, 500, now=100.0) is True       # 首次放行
    assert g.should_click(510, 505, now=101.0) is False      # 同一按钮(近) -> 跳过
    assert g.should_click(500, 500, now=103.0) is False      # 冷却内 -> 跳过


def test_click_guard_releases_after_cooldown():
    g = ClickGuard(cooldown=5, dedupe_radius=40)
    assert g.should_click(500, 500, now=100.0) is True
    assert g.should_click(500, 500, now=104.0) is False
    assert g.should_click(500, 500, now=106.0) is True       # 超过冷却，可再点


def test_click_guard_throttles_even_different_spot():
    g = ClickGuard(cooldown=8, dedupe_radius=30)
    assert g.should_click(100, 100, now=0.0) is True
    # 冷却期内即便是另一个位置，也先节流（避免一帧里狂点多处）
    assert g.should_click(900, 900, now=1.0) is False
    assert g.should_click(900, 900, now=9.0) is True


def test_config_roundtrip(tmp_path=None):
    import tempfile
    cfg = MonitorConfig(keywords=["领取", "红包"], region=(10, 20, 800, 600),
                        interval=0.9, cooldown=6, auto_click=False)
    d = tempfile.mkdtemp()
    p = os.path.join(d, "cfg.json")
    cfg.save(p)
    loaded = MonitorConfig.load(p)
    assert loaded.keywords == ["领取", "红包"]
    assert loaded.region == (10, 20, 800, 600)        # JSON list -> tuple
    assert loaded.auto_click is False
    assert abs(loaded.interval - 0.9) < 1e-9


def test_config_from_dict_ignores_unknown():
    cfg = MonitorConfig.from_dict({"keywords": ["x"], "garbage": 1, "region": [1, 2, 3, 4]})
    assert cfg.keywords == ["x"]
    assert cfg.region == (1, 2, 3, 4)


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
