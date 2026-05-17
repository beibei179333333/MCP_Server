import pytest
from bot.plugins import MessageContext, build_chain


@pytest.mark.asyncio
async def test_btn2text_appends_buttons():
    chain = build_chain({"btn2text": {}})
    ctx = MessageContext(text="正文")
    ctx.extra["source_buttons"] = [
        [{"label": "频道", "url": "https://t.me/x"}],
        [{"label": "客服", "url": "https://t.me/cs"}],
    ]
    await chain.run(ctx)
    assert "频道" in ctx.text and "https://t.me/x" in ctx.text
    assert "客服" in ctx.text


@pytest.mark.asyncio
async def test_buttons_plugin_writes_to_ctx():
    chain = build_chain({"buttons": {"rows": [[{"label": "X", "url": "https://x.com"}]]}})
    ctx = MessageContext(text="hello")
    await chain.run(ctx)
    assert ctx.extra.get("buttons") == [[{"label": "X", "url": "https://x.com"}]]


@pytest.mark.asyncio
async def test_chain_order_with_ai_disabled_keeps_text():
    # AI 没配 key 时应自动跳过，不影响其他插件
    chain = build_chain({
        "filter": {"keywords": ["hello"]},
        "ai": {"action": "rewrite"},
        "caption": {"footer": " — done"},
    })
    ctx = MessageContext(text="hello world")
    ok = await chain.run(ctx)
    assert ok is True
    assert ctx.text.endswith(" — done")


@pytest.mark.asyncio
async def test_chain_filter_drops_before_ai_runs():
    chain = build_chain({
        "filter": {"blacklist": ["ban"]},
        "ai": {"action": "rewrite"},
    })
    ctx = MessageContext(text="this is ban")
    ok = await chain.run(ctx)
    assert ok is False


@pytest.mark.asyncio
async def test_db_new_fields(db):
    from bot.database import ForwardRule
    async with db() as s:
        r = ForwardRule(
            name="t", source_chat="@a", targets="@b",
            sender="bot", sync_edits=True, sync_deletes=True,
            source_topic=12, target_topic=34, folder="新闻",
            plugins={},
        )
        s.add(r); await s.commit(); await s.refresh(r)
    assert r.sender == "bot"
    assert r.sync_edits and r.sync_deletes
    assert r.source_topic == 12 and r.target_topic == 34
    assert r.folder == "新闻"


@pytest.mark.asyncio
async def test_referral_commission_credits_referrer(db):
    from bot.database import User
    from bot.handlers.referral import credit_referral_commission
    async with db() as s:
        ref = User(id=100, points=0, referrals=0)
        u = User(id=200, referrer_id=100)
        s.add_all([ref, u]); await s.commit()
    await credit_referral_commission(200, 99.0)  # 99 * 0.2 = 19.8 -> 19
    async with db() as s:
        ref2 = await s.get(User, 100)
    assert ref2.points == 19


@pytest.mark.asyncio
async def test_referral_no_referrer_skips(db):
    from bot.database import User
    from bot.handlers.referral import credit_referral_commission
    async with db() as s:
        u = User(id=300)
        s.add(u); await s.commit()
    # 没有推荐人 -> 不抛错
    await credit_referral_commission(300, 99.0)
