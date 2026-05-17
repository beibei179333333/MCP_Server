import pytest

from bot.plugins import MessageContext, build_chain


@pytest.mark.asyncio
async def test_filter_keywords_blacklist():
    chain = build_chain({"filter": {"keywords": ["优惠", "好评"], "blacklist": ["广告"]}})
    ctx = MessageContext(text="今天有大优惠")
    assert await chain.run(ctx) is True
    ctx2 = MessageContext(text="今天有广告优惠")
    assert await chain.run(ctx2) is False
    ctx3 = MessageContext(text="什么都没有")
    assert await chain.run(ctx3) is False


@pytest.mark.asyncio
async def test_replace_then_caption():
    chain = build_chain({
        "replace": {"rules": [{"from": "A", "to": "B"}]},
        "caption": {"header": "🔥 ", "footer": " — @ch"},
    })
    ctx = MessageContext(text="AAA")
    ok = await chain.run(ctx)
    assert ok is True
    assert ctx.text == "🔥 BBB — @ch"


@pytest.mark.asyncio
async def test_media_filter():
    chain = build_chain({"media": {"allow": ["photo", "text"]}})
    ok_photo = MessageContext(media_type="photo")
    ok_video = MessageContext(media_type="video")
    assert await chain.run(ok_photo) is True
    assert await chain.run(ok_video) is False


@pytest.mark.asyncio
async def test_format_strip_links():
    chain = build_chain({"format": {"strip_links": True, "strip_mentions": True}})
    ctx = MessageContext(text="点击 https://x.com 关注 @someone 谢谢")
    await chain.run(ctx)
    assert "https://" not in ctx.text
    assert "@someone" not in ctx.text


@pytest.mark.asyncio
async def test_filter_regex():
    chain = build_chain({"filter": {"keywords": ["/订单\\d+/"]}})
    ok = MessageContext(text="订单123 已下单")
    no = MessageContext(text="无订单")
    assert await chain.run(ok) is True
    assert await chain.run(no) is False
