#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第六阶段：knowledge/ Markdown 知识库层

Agent 直接引用，无需重新分析。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parent
PIPE = Path("/Users/home/Downloads/tg_private_4y_monthly")
TASKS = Path("/Users/home/Downloads/压缩包/monthly_agent_tasks_2022-2026-07")

ROOTS = [
    SKILL / "knowledge",
    PIPE / "knowledge",
    TASKS / "knowledge",
]

SUBS = [
    "personality",
    "relationship",
    "business",
    "emotion",
    "language",
    "strategy",
    "lora",
]


def write_all(rel: str, text: str) -> None:
    for root in ROOTS:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def main() -> int:
    reports = SKILL / "reports"
    long_term = reports / "long_term"
    now = datetime.now(timezone.utc).isoformat()

    # --- personality ---
    self_p = read(reports / "self_personality.md")
    evo = read(long_term / "personality_evolution.md")
    write_all(
        "personality/README.md",
        f"""# 人格知识库

> Agent 直接引用 · 生成于 {now}

## 入口

- [自我人格画像](self_personality.md)
- [人格演化（四年）](personality_evolution.md)
- 月度摘要：`../reports/YYYY-MM_personality_summary.md`（55 份）

## 使用约定

1. 先读 `self_personality.md` 定调
2. 需要时间线时读演化报告
3. 需要某月细节时读对应月度摘要
4. **禁止**用低营养广告腔覆盖人格主轴
""",
    )
    write_all("personality/self_personality.md", self_p or "# （缺失 self_personality，请先跑报告生成）\n")
    write_all("personality/personality_evolution.md", evo or "# （缺失演化报告）\n")
    write_all(
        "personality/how_to_use.md",
        """# 人格知识如何用

- 训练 / 回复生成：以高营养样本中的「短、碎、实、有边界」为准
- 冲突时：`self_personality` > 单月波动 > 单条对话
- 早期月份低置信；后期防模板污染
""",
    )

    # --- relationship ---
    rel = read(long_term / "relationship_evolution.md")
    u = {}
    up = PIPE / "06_full_coverage" / "contact_universe.json"
    if up.exists():
        u = json.loads(up.read_text(encoding="utf-8"))
    write_all(
        "relationship/README.md",
        f"""# 关系知识库

> 联系人宇宙约 **{u.get('contact_count', 7988)}** · 深分析 ≤100（或高价值 stars≥3）≈ **{u.get('deep_analysis_count')}**
> 规则：`{u.get('deep_analysis_rule', 'valid_message_count <= 100 OR value.stars >= 3')}`
> 相对原 ≤50 新增约 **{u.get('deep_analysis_newly_added', '—')}**

## 入口

- [关系演化报告](relationship_evolution.md)
- [深分析扩量说明](deep_coverage_le100.md)
- 单人画像：`person/{{peer_id}}.json` 的 `relationship` / `trust` 字段
- 全员策略：`06_full_coverage/strategies/by_peer/`
- 主队列：`06_full_coverage/deep_priority_le100.jsonl`

## 价值重定义

- 1–2 条 = 特高价值深分析
- ≤100 条必须深分析
- stars≥3（特高/超高/高价值）必须深分析
- 禁止按高消息量优先
""",
    )
    write_all("relationship/relationship_evolution.md", rel or "# （缺失）\n")

    # deep coverage knowledge
    exp = {}
    ep = PIPE / "06_full_coverage" / "deep_expansion_le100_report.json"
    if ep.exists():
        exp = json.loads(ep.read_text(encoding="utf-8"))
    write_all(
        "relationship/deep_coverage_le100.md",
        f"""# 深分析覆盖扩量（≤50 → ≤100 + 高价值）

生成于 {now}

## 规则

```text
deep_analysis = (valid_message_count <= 100) OR (value.stars >= 3)
```

高价值定义为价值分层 **stars≥3**（特高 / 超高 / 高价值）。

## 规模

| 指标 | 数值 |
|---|---:|
| 联系人总数 | {exp.get('contact_count') or u.get('contact_count') or 7988} |
| 原深分析（≤50） | {exp.get('deep_prev_le50') or 6935} |
| 现深分析 | {exp.get('deep_now') or u.get('deep_analysis_count') or '—'} |
| 新增入队 | {exp.get('newly_added') or u.get('deep_analysis_newly_added') or '—'} |
| 新增构成 | {exp.get('newly_by_range') or {}} |

## 产物路径

- `06_full_coverage/deep_priority_le100.jsonl` — 主队列
- `06_full_coverage/deep_priority_le50.jsonl` — 兼容子集
- `06_full_coverage/deep_expansion_le100_report.json` — 扩量审计
- `outputs/contact_universe/build_status.json` — skill 侧状态

## Agent 用法

1. 深分析优先读 le100 队列，不要只读旧 le50
2. 51–100 条联系人同样需要策略证据与置信度，不可因「超过 50」跳过
3. Qwen 深版阶梯目标上限随深分析人数上调（见 strategy/）
4. 仍禁止汇旺/靓号联系人级过滤
""",
    )

    write_all(
        "relationship/stages.md",
        """# 关系阶段字典

| stage | 含义 | 信任倾向 |
|---|---|---|
| 陌生 | 几乎无互惠 | 低 |
| 初识 | 有限回合 | 偏低 |
| 熟悉 | 稳定互惠 | 中 |
| 合作 | 事务/利益绑定 | 中高 |
| 长期 | 持续关系 | 高 |
| 淡化 | 互动衰减 | 下滑 |
| 失联 | 长期中断 | 断裂 |

态度：`被动` / `平衡` / `主动` / `高投入`
""",
    )

    # --- business ---
    write_all(
        "business/README.md",
        f"""# 商务知识库

生成于 {now}

## 原则

1. **被动商务**是人格主轴：对方发起 → 报价/确认/交付/售后
2. 主动营销 / 群发腔 = 污染，可留语料但降权
3. 汇旺/靓号/会员/能量 = 行业场域，**不按名单删联系人**
4. 单人商务摘要：读 `person/{{id}}.json` → `business`

## 边界

- 资金往来坚持验证
- 拒绝越权 / 验证码 / 远程控制
- 朋友与生意可并存，不可混账
""",
    )
    write_all(
        "business/playbook.md",
        """# 商务回应手册（从数据归纳）

1. 先确认需求类型（靓号 / 会员 / 能量 / 其他）
2. 给入口或条件，少空谈
3. 需要时拆多行短句
4. 成交后短确认闭环
5. 风险提示优先于成交话术
""",
    )

    # --- emotion ---
    write_all(
        "emotion/README.md",
        f"""# 情绪知识库

生成于 {now}

## 画像要点

- 共情有配额，不是全天候治愈系
- 路径：确认听到 → 可执行出口 → 必要时短句收束
- 深度情绪劳动集中在高营养情感样本

## Agent 用法

读 `person/{{id}}.json` 的 `emotion`；冲突时以高营养原文为准。
""",
    )
    write_all(
        "emotion/response_patterns.md",
        """# 情绪回应模式

| 模式 | 何时 | 风险 |
|---|---|---|
| 确认 | 对方倾诉/投诉 | 空确认过拟合 |
| 安慰 | 压力/负面 | 灌鸡汤 |
| 建议 | 对方要方案 | 说教 |
| 冷处理 | 空耗/越界 | 被读成敷衍 |
| 拒绝 | 越权/风险 | 伤关系（可接受） |
""",
    )

    # --- language ---
    short = read(long_term / "short_phrase_evolution.md")
    write_all(
        "language/README.md",
        f"""# 语言知识库

生成于 {now}

## 入口

- [短句演化](short_phrase_evolution.md)
- 语义簇：`06_full_coverage/short_phrases/semantic_clusters_top1000.json`
- 替换簇：`06_full_coverage/short_phrases/replace_clusters_top1000.json`
- 人工筛选：`for_manual_review.md`（禁止自动删除）

## 节奏

- 快齿轮：好的/收到/嗯/行
- 慢齿轮：多行短句拆解
""",
    )
    write_all("language/short_phrase_evolution.md", short or "# （缺失）\n")
    write_all(
        "language/style_rules.md",
        """# 语言风格规则

1. 保持原始文本，不润色
2. 短句可合并进替换簇，但须人工确认
3. 训练时限制低营养短确认比例
4. 「有温度的短」≠「空的短」
""",
    )

    # --- strategy ---
    write_all(
        "strategy/README.md",
        f"""# 策略知识库

生成于 {now}

## 双轨

| 轨 | 路径 | 用途 |
|---|---|---|
| 规则版 | `06_full_coverage/strategies/` | 全员 7988 只读基线 |
| Qwen 深版 | `06_full_coverage/strategies_qwen_deep_v1/` | 阶梯扩量，审核后升阶 |

## 阶梯

220 → 1000 → 2500 → **7402**（深分析全量，原 6935 已扩至 ≤100）  
门禁：重复率 / 幻觉 / 一致性 / 稳定性  
状态：`outputs/deep_pilot/ladder/`

## 12 类

利益捆绑、长期关系经营、战略价值整合、战略撤退、筹码对调、情绪杠杆、
沉没成本、情报商、框架驯兽、规则降维、流失挽回、风险审核

单人：`person/{{id}}.json` → `strategy` / `risk`
""",
    )
    write_all(
        "strategy/ladder_policy.md",
        """# Qwen Deep 阶梯政策

1. 禁止 220 直接跳深分析全量（现约 7402）
2. 每阶满员后跑 gate 报告
3. `can_promote_next=true` 才可升阶
4. ≤5 条强制「暂不判断」
5. 规则版永不覆盖
6. 深分析覆盖：`≤100` 或 `stars≥3`（见 `relationship/deep_coverage_le100.md`）
""",
    )

    # --- lora ---
    lora = read(long_term / "lora_data_quality.md")
    write_all(
        "lora/README.md",
        f"""# LoRA 知识库

生成于 {now}

## 入口

- [数据质量报告](lora_data_quality.md)
- 月度 Alpaca：`05_training_dataset/YYYY/MM/`
- 权重字段：`sample_weight`
- 营养：高营养优先，低营养降权

## 训练纪律

1. 会话级 train/val 不泄漏（按 peer）
2. 不把未审核 Qwen 标签写进训练集
3. 抽检高营养 + 限制低营养比例
""",
    )
    write_all("lora/lora_data_quality.md", lora or "# （缺失）\n")
    write_all(
        "lora/weight_policy.md",
        """# Weight / Tag 调整政策

| 信号 | 动作 |
|---|---|
| 高营养 + 情感/被动商务 | 提权 |
| 主动营销 / 模板广告 | 降权或标 low_nutrition |
| 空确认过拟合 | 降权 + 短句人工筛选 |
| 情感串商务 | 检查污染，不删联系人 |
| Tag | 可继续调，但保持可追溯 |
""",
    )

    # root index
    write_all(
        "README.md",
        f"""# Knowledge 知识库层（第六阶段）

生成于 {now}

Agent **直接引用**本目录 Markdown，不必重新分析四年语料。

## 目录

| 子库 | 内容 |
|---|---|
| [personality/](personality/) | 自我画像 + 人格演化 |
| [relationship/](relationship/) | 关系宇宙 + 深分析≤100扩量 + 阶段字典 |

| [business/](business/) | 商务原则与手册 |
| [emotion/](emotion/) | 情绪模式 |
| [language/](language/) | 短句/风格 |
| [strategy/](strategy/) | 12 类策略 + 阶梯政策 |
| [lora/](lora/) | 训练质量与权重 |

## 配套

- 单人 JSON：`person/{{peer_id}}.json`
- 月度报告：`reports/YYYY-MM_personality_summary.md`
- 长期报告：`reports/long_term/`
""",
    )

    # count files
    for root in ROOTS:
        n = sum(1 for _ in root.rglob("*.md"))
        print(f"{root}: {n} md files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
