"""smm_growth 的离线单元测试（无需网络）。

运行：python tests/test_smm.py   或   python -m pytest tests/test_smm.py -q
"""
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smm_growth.config import (interpolate_env, load_campaign, parse_campaign)
from smm_growth.curves import (GrowthCurve, curve_value, jitter_factor, progress)
from smm_growth.panel import OrderResult, PanelClient
from smm_growth.config import Panel
from smm_growth import planner
from smm_growth.runner import run_date, load_post_links


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "smm_growth", "campaign.yaml")


# --------------------------------------------------------------------- curves
def test_progress_and_shape():
    assert progress(0, 30) == 0.0
    assert progress(29, 30) == 1.0
    assert progress(0, 1) == 1.0          # 单天活动
    mid = curve_value(15, 31, 0, 100, "linear")
    assert abs(mid - 50) < 0.001          # 第 15/30 天恰好中点


def test_curve_endpoints_and_monotonic():
    for shape in ("linear", "ease_in", "ease_out", "s_curve"):
        assert abs(curve_value(0, 30, 10, 60, shape) - 10) < 1e-6
        assert abs(curve_value(29, 30, 10, 60, shape) - 60) < 1e-6
        vals = [curve_value(d, 30, 10, 60, shape) for d in range(30)]
        assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:]))  # 单调不降


def test_jitter_deterministic_and_bounded():
    f1 = jitter_factor("chanA|members|3", 0.15)
    f2 = jitter_factor("chanA|members|3", 0.15)
    assert f1 == f2                        # 可复现
    assert 0.85 <= f1 <= 1.15
    assert jitter_factor("x", 0.0) == 1.0  # 0 抖动 -> 恒为 1
    assert jitter_factor("a", 0.1) != jitter_factor("b", 0.1)  # 不同 seed 不同


def test_growthcurve_amount_clamps_nonneg_and_int():
    gc = GrowthCurve(start=15, end=60, curve="ease_in", jitter_pct=0.0)
    a0 = gc.amount(0, 30, seed="s")
    a29 = gc.amount(29, 30, seed="s")
    assert a0 == 15 and a29 == 60
    assert isinstance(a0, int)


# --------------------------------------------------------------------- config
def test_env_interpolation():
    env = {"FOO": "bar"}
    assert interpolate_env("${FOO}", env) == "bar"
    assert interpolate_env("${MISSING}", env) == ""
    assert interpolate_env("${MISSING:-def}", env) == "def"
    assert interpolate_env("k-${FOO}-${MISSING:-z}", env) == "k-bar-z"


def test_load_real_campaign():
    c = load_campaign(CONFIG_PATH, environ={"SMMFOLLOWS_API_KEY": "KKK"})
    assert c.start_date == date(2026, 6, 2)
    assert c.duration_days == 30
    assert len(c.channels) == 10
    assert c.panels["smmfollows"].key == "KKK"
    assert c.panels["smmstone"].key == ""        # 未设环境变量 -> 空
    assert c.members.primary.service_id == 14916
    assert c.members.backup.service_id == 10735
    assert c.views.primary.is_auto is True
    assert c.comment.fixed_qty == 10 and c.comment.link_kind == "post"
    assert c.share.fixed_qty == 15
    assert len(c.regional) == 5
    assert {g.label for g in c.regional} == {
        "chinese", "russian", "indian", "arabic", "western"}
    assert all(g.fixed_qty == 35 for g in c.regional)
    assert c.premium.fixed_qty == 35
    assert c.execution.dry_run is True


def _mini_config():
    """构造一个最小配置 dict，便于精确断言规划逻辑。"""
    def svc(sid, **kw):
        d = {"service_id": sid, "panel": "P", "rate_per_1k": 1.0,
             "min_order": 10, "max_order": 100000}
        d.update(kw)
        return d
    return {
        "start_date": "2026-06-02", "duration_days": 14, "posts_per_day": 5,
        "channels": [{"name": "A", "link": "https://t.me/a"},
                     {"name": "B", "link": "https://t.me/b"}],
        "panels": {"P": {"url": "http://p/api/v2", "key": "k"},
                   "Q": {"url": "http://q/api/v2", "key": "k2"}},
        "services": {
            "members": {"primary": svc(1), "backup": svc(2)},
            "views": {"primary": svc(3, is_auto=True), "backup": svc(4, is_auto=True)},
            "reactions": {"primary": svc(5, is_auto=True)},
        },
        "addon_services": {
            "comment": {"enabled": True, "daily_qty": 10,
                        "primary": svc(6), "backup": svc(7)},
            "share": {"enabled": True, "daily_qty": 15, "primary": svc(8)},
            "regional_members": {"enabled": True, "qty_per_region_per_week": 35,
                                 "regions": {"chinese": svc(9, panel="Q"),
                                             "russian": svc(10, panel="Q")}},
            "premium_members": {"enabled": True, "qty_per_week": 35,
                                "primary": svc(11, panel="Q")},
        },
        "execution": {"dry_run": True},
    }


# --------------------------------------------------------------------- planner
def test_daily_vs_weekly_scheduling():
    c = parse_campaign(_mini_config())
    # 第 0 天：每天项（members,comment,share）+ 每周项（views,reactions,2地区,premium）
    d0 = planner.orders_for_day(c, 0)
    cats0 = sorted(o.category for o in d0 if o.channel.name == "A")
    assert cats0 == ["comment", "members", "premium_members", "reactions",
                     "regional_members", "regional_members", "share", "views"]
    # 第 1 天：只剩每天项
    d1 = planner.orders_for_day(c, 1)
    cats1 = sorted(o.category for o in d1 if o.channel.name == "A")
    assert cats1 == ["comment", "members", "share"]
    # 第 7 天又是每周日
    assert any(o.category == "views" for o in planner.orders_for_day(c, 7))
    # 两个频道
    assert len({o.channel.name for o in d1}) == 2


def test_quantities_and_clamp():
    c = parse_campaign(_mini_config())
    d0 = planner.orders_for_day(c, 0)
    by = {(o.category, o.label): o for o in d0 if o.channel.name == "A"}
    assert by[("comment", "")].quantity == 10
    assert by[("share", "")].quantity == 15
    assert by[("regional_members", "chinese")].quantity == 35
    assert by[("premium_members", "")].quantity == 35
    # members 受 ease_in 曲线影响，第 0 天接近 start=15，被裁剪到 >=10
    m = by[("members", "")].quantity
    assert m >= c.members.primary.min_order
    # 帖子型服务标记
    assert by[("comment", "")].needs_post_link is True
    assert by[("members", "")].needs_post_link is False


def test_full_schedule_size_and_cost():
    c = parse_campaign(_mini_config())
    sched = planner.full_schedule(c)
    # 14 天里有 2 个每周日（day 0, 7）
    weekly_days = [d for d in range(14) if d % 7 == 0]
    assert len(weekly_days) == 2
    # 每频道每天 3 个每天项 -> 14*2*3 = 84
    # 每周项每频道每周日 5 个(views,reactions,2地区,premium) -> 2*2*5 = 20
    assert len(sched) == 84 + 20
    assert planner.total_cost(sched) > 0


def test_out_of_range_returns_empty():
    c = parse_campaign(_mini_config())
    assert planner.orders_for_day(c, -1) == []
    assert planner.orders_for_day(c, 14) == []


def test_prefer_quality_promotes_high_tier():
    cfg = _mini_config()
    # members: 主(1)=standard 便宜，备(2)=high 贵 -> prefer_quality 应优先用 2
    cfg["services"]["members"]["primary"].update(quality="standard", rate_per_1k=0.69)
    cfg["services"]["members"]["backup"].update(quality="high", rate_per_1k=0.78)
    cfg["execution"]["prefer_quality"] = True
    c = parse_campaign(cfg)
    o = next(o for o in planner.orders_for_day(c, 0)
             if o.category == "members" and o.channel.name == "A")
    assert o.lead.service_id == 2 and o.lead.quality == "high"
    assert o.specs[0].service_id == 2 and o.specs[1].service_id == 1  # 优质排前
    # 关掉 prefer_quality -> 维持配置顺序，主=1
    cfg["execution"]["prefer_quality"] = False
    c2 = parse_campaign(cfg)
    o2 = next(o for o in planner.orders_for_day(c2, 0)
              if o.category == "members" and o.channel.name == "A")
    assert o2.lead.service_id == 1


def test_real_campaign_quality_upgrade_members():
    c = load_campaign(CONFIG_PATH, environ={"SMMFOLLOWS_API_KEY": "K"})
    assert c.execution.prefer_quality is True
    o = next(o for o in planner.orders_for_day(c, 1)  # 非每周日，只有 members 是 channel 粉丝
             if o.category == "members")
    # 粉丝应升级到 180D 补量档(10735)
    assert o.lead.service_id == 10735 and o.lead.quality == "high"


# --------------------------------------------------------------------- panel client
def test_panel_dryrun_add_builds_payload_no_network():
    p = Panel(name="P", url="http://p/api/v2", key="secret")
    client = PanelClient(p, dry_run=True, verbose=False)
    r = client.add(14916, "https://t.me/a", 100, cost=0.069)
    assert r.ok and r.dry_run and r.order_id is not None
    assert r.payload["action"] == "add" and r.payload["service"] == 14916
    assert r.payload["key"] == "***"      # 不泄露 key
    assert abs(r.cost - 0.069) < 1e-9


def test_panel_real_add_missing_key():
    p = Panel(name="P", url="http://p/api/v2", key="")
    client = PanelClient(p, dry_run=False, verbose=False)
    r = client.add(1, "https://t.me/a", 100)
    assert not r.ok and "key" in (r.error or "").lower()


def test_panel_add_parses_order_and_error(monkeypatch=None):
    p = Panel(name="P", url="http://p/api/v2", key="secret")
    client = PanelClient(p, dry_run=False, verbose=False)
    client._post = lambda params: {"order": 555}          # type: ignore
    r = client.add(1, "https://t.me/a", 50, cost=0.05)
    assert r.ok and r.order_id == 555
    client._post = lambda params: {"error": "not enough funds"}  # type: ignore
    r2 = client.add(1, "https://t.me/a", 50)
    assert not r2.ok and r2.error == "not enough funds"


# --------------------------------------------------------------------- runner
class _FakeClient:
    """假面板客户端：可指定哪些 service_id 失败，用于测试主->备切换。"""
    def __init__(self, name, fail_ids=()):
        self.name = name
        self.fail_ids = set(fail_ids)
        self.calls = []

    def add(self, service_id, link, quantity, *, cost=0.0, extra=None):
        self.calls.append((service_id, link, quantity))
        if service_id in self.fail_ids:
            return OrderResult(ok=False, panel=self.name, service_id=service_id,
                               link=link, quantity=quantity, error="forced fail",
                               cost=cost)
        return OrderResult(ok=True, panel=self.name, service_id=service_id, link=link,
                           quantity=quantity, order_id=1, cost=cost)


def test_runner_skips_post_services_without_links():
    c = parse_campaign(_mini_config())
    clients = {"P": _FakeClient("P"), "Q": _FakeClient("Q")}
    rep = run_date(c, date(2026, 6, 2), clients=clients, dry_run=True, verbose=False)
    # 评论/分享缺帖子链接 -> 跳过
    assert any("comment" in s for s in rep.skipped)
    assert any("share" in s for s in rep.skipped)
    # 没有任何 comment/share 成功
    assert all(r.service_id not in (6, 7, 8) for r in rep.results)


def test_runner_places_with_post_links_and_only_filter():
    c = parse_campaign(_mini_config())
    clients = {"P": _FakeClient("P"), "Q": _FakeClient("Q")}
    posts = {"https://t.me/a": "https://t.me/a/100",
             "https://t.me/b": "https://t.me/b/200"}
    rep = run_date(c, date(2026, 6, 2), clients=clients, post_links=posts,
                   only=["comment"], dry_run=True, verbose=False)
    # 仅 comment，两个频道各一单
    assert rep.placed == 2 and rep.failed == 0
    assert all(call[0] == 6 for call in clients["P"].calls)  # 主评论服务
    assert clients["P"].calls[0][1].endswith("/100")         # 用了帖子链接


def test_runner_fallback_to_backup():
    c = parse_campaign(_mini_config())
    # 让主 members 服务(1) 失败 -> 应切到备用(2)
    clients = {"P": _FakeClient("P", fail_ids={1}), "Q": _FakeClient("Q")}
    rep = run_date(c, date(2026, 6, 3), clients=clients, only=["members"],
                   dry_run=True, verbose=False)
    assert rep.placed == 2 and rep.failed == 0
    used = {call[0] for call in clients["P"].calls}
    assert 1 in used and 2 in used      # 主试过、备成功


def test_runner_channel_filter_and_out_of_range():
    c = parse_campaign(_mini_config())
    clients = {"P": _FakeClient("P"), "Q": _FakeClient("Q")}
    rep = run_date(c, date(2026, 6, 3), clients=clients, only=["members"],
                   channel_filter="t.me/a", dry_run=True, verbose=False)
    assert rep.placed == 1
    # 越界日期
    rep2 = run_date(c, date(2030, 1, 1), clients=clients, dry_run=True, verbose=False)
    assert rep2.placed == 0 and rep2.skipped


def test_load_post_links_file():
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write("# comment\n")
        f.write("https://t.me/a https://t.me/a/1\n")
        f.write("https://t.me/b, https://t.me/b/2\n")
        path = f.name
    links = load_post_links(path)
    os.unlink(path)
    assert links == {"https://t.me/a": "https://t.me/a/1",
                     "https://t.me/b": "https://t.me/b/2"}


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
