import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_seed_plans(db):
    from bot.database import SubscriptionPlan
    async with db() as s:
        rows = (await s.execute(select(SubscriptionPlan))).scalars().all()
    assert len(rows) >= 4
    codes = {p.code for p in rows}
    assert {"trial", "basic", "pro", "ultimate"} <= codes


@pytest.mark.asyncio
async def test_ledger_account_unique(db):
    from bot.database import LedgerAccount
    async with db() as s:
        s.add(LedgerAccount(owner_id=1, name="A"))
        await s.commit()
        s.add(LedgerAccount(owner_id=1, name="A"))
        with pytest.raises(Exception):
            await s.commit()


@pytest.mark.asyncio
async def test_forward_rule_plugins_json(db):
    from bot.database import ForwardRule
    async with db() as s:
        r = ForwardRule(
            name="t", source_chat="@a", targets="@b",
            plugins={"filter": {"keywords": ["x"]}},
        )
        s.add(r)
        await s.commit()
        await s.refresh(r)
    assert r.plugins["filter"]["keywords"] == ["x"]


@pytest.mark.asyncio
async def test_budget_unique(db):
    from bot.database import Budget
    async with db() as s:
        s.add(Budget(owner_id=1, category="餐饮", monthly_limit=1000))
        await s.commit()
        s.add(Budget(owner_id=1, category="餐饮", monthly_limit=2000))
        with pytest.raises(Exception):
            await s.commit()
