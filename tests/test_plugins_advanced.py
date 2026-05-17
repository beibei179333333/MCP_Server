import pytest
from bot.plugins import MessageContext, build_chain


@pytest.mark.asyncio
async def test_dedupe_drops_duplicates():
    chain = build_chain({"dedupe": {"window": 50}})
    ctx1 = MessageContext(text="同样的内容")
    ctx1.extra["rule_id"] = 1
    ctx2 = MessageContext(text="同样的内容")
    ctx2.extra["rule_id"] = 1
    ctx3 = MessageContext(text="不一样的内容")
    ctx3.extra["rule_id"] = 1
    assert await chain.run(ctx1) is True
    assert await chain.run(ctx2) is False   # 重复
    assert await chain.run(ctx3) is True


@pytest.mark.asyncio
async def test_dedupe_isolated_by_rule():
    chain = build_chain({"dedupe": {"window": 10}})
    ctx1 = MessageContext(text="hello")
    ctx1.extra["rule_id"] = 1
    ctx2 = MessageContext(text="hello")
    ctx2.extra["rule_id"] = 2   # 不同规则不会冲突
    assert await chain.run(ctx1) is True
    assert await chain.run(ctx2) is True


@pytest.mark.asyncio
async def test_raw_strips_markdown():
    chain = build_chain({"raw": {}})
    ctx = MessageContext(text="*粗体* `代码` _斜体_ [链接](https://x.com)")
    await chain.run(ctx)
    assert "*" not in ctx.text and "`" not in ctx.text
    assert "链接" in ctx.text and "https://x.com" in ctx.text


@pytest.mark.asyncio
async def test_raw_strips_html():
    chain = build_chain({"raw": {}})
    ctx = MessageContext(text="<b>bold</b> <i>italic</i>")
    await chain.run(ctx)
    assert "<" not in ctx.text and "bold" in ctx.text


@pytest.mark.asyncio
async def test_delay_zero_does_not_block():
    import time
    chain = build_chain({"delay": {"seconds": 0}})
    ctx = MessageContext(text="x")
    t0 = time.time()
    await chain.run(ctx)
    assert time.time() - t0 < 0.1
