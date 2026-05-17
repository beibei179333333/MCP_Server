"""SQLAlchemy 异步数据库模型与会话工厂（融合 tgcf 风格的插件/多目标设计）。"""
from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import settings


class Base(DeclarativeBase):
    pass


# =============================================================
# 用户 / 群组（基础实体）
# =============================================================
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    first_name: Mapped[Optional[str]] = mapped_column(String(128))
    last_name: Mapped[Optional[str]] = mapped_column(String(128))
    language: Mapped[Optional[str]] = mapped_column(String(8))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[Optional[str]] = mapped_column(Text)  # 逗号分隔，用于群发分群
    referrer_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    referrals: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type: Mapped[str] = mapped_column(String(16))
    title: Mapped[Optional[str]] = mapped_column(String(255))
    username: Mapped[Optional[str]] = mapped_column(String(64))
    members: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GroupSetting(Base):
    """单群组的开关配置（欢迎语 / 验证码 / 反垃圾）。"""

    __tablename__ = "group_settings"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    welcome_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    welcome_text: Mapped[Optional[str]] = mapped_column(Text)
    farewell_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    farewell_text: Mapped[Optional[str]] = mapped_column(Text)
    captcha_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    captcha_type: Mapped[str] = mapped_column(String(16), default="button")  # button / math
    captcha_timeout: Mapped[int] = mapped_column(Integer, default=120)
    anti_spam_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    block_links: Mapped[bool] = mapped_column(Boolean, default=False)
    block_forward: Mapped[bool] = mapped_column(Boolean, default=False)
    mute_new_user_seconds: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CaptchaSession(Base):
    """新成员等待验证的会话。"""

    __tablename__ = "captcha_sessions"
    __table_args__ = (UniqueConstraint("chat_id", "user_id", name="uq_chat_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    answer: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    message_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# =============================================================
# 搬运（tgcf 风格：多源多目标 + 插件链）
# =============================================================
class ForwardRule(Base):
    __tablename__ = "forward_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    source_chat: Mapped[str] = mapped_column(String(128))
    # 多目标：逗号分隔 / 一对多
    targets: Mapped[str] = mapped_column(Text)
    # 模式：live = 实时，past = 历史（一次性回填）
    mode: Mapped[str] = mapped_column(String(8), default="live")
    # 发送身份：user = user-bot 用你账号发，bot = 机器人发
    sender: Mapped[str] = mapped_column(String(8), default="user")
    # 编辑 / 删除同步
    sync_edits: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_deletes: Mapped[bool] = mapped_column(Boolean, default=False)
    # Topic 支持（论坛超级群）
    source_topic: Mapped[Optional[int]] = mapped_column(Integer)
    target_topic: Mapped[Optional[int]] = mapped_column(Integer)
    # 任务分组
    folder: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    # 插件链配置（JSON），按顺序应用
    plugins: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    forwarded_count: Mapped[int] = mapped_column(Integer, default=0)
    dropped_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_id: Mapped[Optional[int]] = mapped_column(BigInteger)  # 用于断点续传
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ForwardedMapping(Base):
    """搬运消息映射表：用于编辑/删除同步。"""

    __tablename__ = "forwarded_mappings"
    __table_args__ = (
        Index("ix_fwm_src", "rule_id", "src_chat_id", "src_msg_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(Integer, index=True)
    src_chat_id: Mapped[int] = mapped_column(BigInteger)
    src_msg_id: Mapped[int] = mapped_column(BigInteger)
    dst_chat: Mapped[str] = mapped_column(String(128))
    dst_msg_id: Mapped[int] = mapped_column(BigInteger)
    sent_by: Mapped[str] = mapped_column(String(8), default="user")  # user / bot
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Withdrawal(Base):
    """佣金提现申请。"""

    __tablename__ = "withdrawals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    points: Mapped[int] = mapped_column(Integer)
    amount: Mapped[float] = mapped_column(Float)  # 折算金额
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    method: Mapped[str] = mapped_column(String(32))  # usdt / alipay / wechat
    account: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


# =============================================================
# 记账 + 预算
# =============================================================
class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_owner_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    initial_balance: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    entries: Mapped[list["LedgerEntry"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("ledger_accounts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(8))  # income / expense
    amount: Mapped[float] = mapped_column(Float)
    category: Mapped[Optional[str]] = mapped_column(String(32))
    note: Mapped[Optional[str]] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    account: Mapped[LedgerAccount] = relationship(back_populates="entries")


class Budget(Base):
    """月度类别预算 + 超额提醒。"""

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("owner_id", "category", name="uq_owner_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    category: Mapped[str] = mapped_column(String(32))
    monthly_limit: Mapped[float] = mapped_column(Float)
    alert_threshold: Mapped[float] = mapped_column(Float, default=0.8)
    last_alert_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RecurringEntry(Base):
    """订阅 / 房租等定期支出，调度器自动入账。"""

    __tablename__ = "recurring_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("ledger_accounts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(8))
    amount: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(32))
    note: Mapped[Optional[str]] = mapped_column(Text)
    cron: Mapped[str] = mapped_column(String(64))  # APScheduler cron 串
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# =============================================================
# 自动回复（增强：按权重随机回复、内联按钮）
# =============================================================
class AutoReply(Base):
    __tablename__ = "auto_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, index=True)
    pattern: Mapped[str] = mapped_column(String(255))
    match_type: Mapped[str] = mapped_column(String(16), default="contains")
    reply_text: Mapped[str] = mapped_column(Text)
    parse_mode: Mapped[Optional[str]] = mapped_column(String(16))  # markdown / html
    buttons: Mapped[Optional[dict]] = mapped_column(JSON)  # 内联按钮 JSON
    weight: Mapped[int] = mapped_column(Integer, default=1)
    cooldown_sec: Mapped[int] = mapped_column(Integer, default=0)
    last_hit_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# =============================================================
# 群发（增强：定时 / 内联按钮 / 分群标签 / 统计）
# =============================================================
class BroadcastJob(Base):
    __tablename__ = "broadcast_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[Optional[str]] = mapped_column(String(128))
    target_type: Mapped[str] = mapped_column(String(16))  # users / chats / both / tag
    target_tag: Mapped[Optional[str]] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[Optional[dict]] = mapped_column(JSON)  # 媒体 / 按钮 等
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/done/failed
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# =============================================================
# 订阅 / 付费
# =============================================================
class SubscriptionPlan(Base):
    __tablename__ = "sub_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[Optional[str]] = mapped_column(Text)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    features: Mapped[Optional[str]] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("sub_plans.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active/expired/cancelled
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    plan_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sub_plans.id"))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    method: Mapped[str] = mapped_column(String(32))  # stars / ton / manual / usdt 等
    tx_ref: Mapped[Optional[str]] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/paid/refunded/failed
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


# =============================================================
# 通用键值 / 引荐链接
# =============================================================
class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    reward_points: Mapped[int] = mapped_column(Integer, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


Index("ix_entries_owner_time", LedgerEntry.account_id, LedgerEntry.occurred_at)
Index("ix_entries_kind_time", LedgerEntry.kind, LedgerEntry.occurred_at)
Index("ix_rules_enabled_mode", ForwardRule.enabled, ForwardRule.mode)
Index("ix_jobs_status_sched", BroadcastJob.status, BroadcastJob.scheduled_at)
Index("ix_subs_user_status", Subscription.user_id, Subscription.status)
Index("ix_users_blocked", User.is_blocked, User.is_banned)
Index("ix_ar_scope_enabled", AutoReply.scope_chat_id, AutoReply.enabled)
Index("ix_chat_active", Chat.is_active)


# =============================================================
# 引擎 / Session
# =============================================================
_engine = create_async_engine(settings.database_url, future=True)
SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if _engine.url.drivername.startswith("sqlite"):
            from sqlalchemy import text
            # 已有库补索引
            patches = [
                "CREATE INDEX IF NOT EXISTS ix_entries_kind_time ON ledger_entries(kind, occurred_at)",
                "CREATE INDEX IF NOT EXISTS ix_rules_enabled_mode ON forward_rules(enabled, mode)",
                "CREATE INDEX IF NOT EXISTS ix_jobs_status_sched ON broadcast_jobs(status, scheduled_at)",
                "CREATE INDEX IF NOT EXISTS ix_subs_user_status ON subscriptions(user_id, status)",
                "CREATE INDEX IF NOT EXISTS ix_users_blocked ON users(is_blocked, is_banned)",
                "CREATE INDEX IF NOT EXISTS ix_ar_scope_enabled ON auto_replies(scope_chat_id, enabled)",
                "CREATE INDEX IF NOT EXISTS ix_chat_active ON chats(is_active)",
            ]
            for sql in patches:
                try:
                    await conn.execute(text(sql))
                except Exception:
                    pass
            # 旧 forward_rules 表补新字段（SQLite 不支持 IF NOT EXISTS 列）
            alters = [
                "ALTER TABLE forward_rules ADD COLUMN sender VARCHAR(8) DEFAULT 'user'",
                "ALTER TABLE forward_rules ADD COLUMN sync_edits BOOLEAN DEFAULT 0",
                "ALTER TABLE forward_rules ADD COLUMN sync_deletes BOOLEAN DEFAULT 0",
                "ALTER TABLE forward_rules ADD COLUMN source_topic INTEGER",
                "ALTER TABLE forward_rules ADD COLUMN target_topic INTEGER",
                "ALTER TABLE forward_rules ADD COLUMN folder VARCHAR(64)",
            ]
            for sql in alters:
                try:
                    await conn.execute(text(sql))
                except Exception:
                    pass
    await _seed_defaults()


async def _seed_defaults() -> None:
    """首次启动写入默认订阅套餐。"""
    async with SessionLocal() as s:
        from sqlalchemy import select
        existing = (await s.execute(select(SubscriptionPlan).limit(1))).scalar_one_or_none()
        if existing:
            return
        defaults = [
            SubscriptionPlan(
                code="trial", name="🎁 免费试用",
                description="新用户 7 天免费试用全部功能",
                price=0, currency="CNY", duration_days=7,
                features="搬运 1 条规则,记账,基础群发", sort_order=0,
            ),
            SubscriptionPlan(
                code="basic", name="⭐ 基础版",
                description="个人玩家 / 小群组",
                price=19, currency="CNY", duration_days=30,
                features="搬运 5 条规则,无限记账,群发 1000/日,自动回复 50 条", sort_order=1,
            ),
            SubscriptionPlan(
                code="pro", name="🚀 专业版",
                description="副业 / 中型社群",
                price=99, currency="CNY", duration_days=30,
                features="搬运 50 条规则,群发 50000/日,定时群发,水印插件,Web 后台", sort_order=2,
            ),
            SubscriptionPlan(
                code="ultimate", name="👑 旗舰版",
                description="MCN / 大型社群运营",
                price=499, currency="CNY", duration_days=30,
                features="无限规则,无限群发,优先客服,自定义插件,白标授权", sort_order=3,
            ),
        ]
        for p in defaults:
            s.add(p)
        await s.commit()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
