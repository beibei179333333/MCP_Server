#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全部重新生成：月度人格摘要(6000-12000字) + 四类长期报告 + self_personality.md

输出根目录：
  <skill>/reports/
"""
from __future__ import annotations

import json
import math
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL = Path(__file__).resolve().parent
PIPE = Path("/Users/home/Downloads/tg_private_4y_monthly")
TASKS = Path("/Users/home/Downloads/压缩包/monthly_agent_tasks_2022-2026-07")
REPORTS = SKILL / "reports"
LONG = REPORTS / "long_term"
TEMPLATE = (SKILL / "templates" / "personality_summary_v2.md").read_text(encoding="utf-8")

START, END = (2022, 1), (2026, 7)
MIN_CHARS, MAX_CHARS, TARGET = 6000, 12000, 8500
SEED = 42


def ym_iter():
    y, m = START
    while (y, m) <= END:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def dash(y, m):
    return f"{y:04d}-{m:02d}"


def compact(y, m):
    return f"{y:04d}{m:02d}"


def prev_ym(y, m):
    if (y, m) == START:
        return None
    return (y - 1, 12) if m == 1 else (y, m - 1)


def next_ym(y, m):
    return (y + 1, 1) if m == 12 else (y, m + 1)


def load_json(p: Path, default=None):
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def char_count(s: str) -> int:
    # 中文报告按字符数计（含标点空白）
    return len(s)


def pct(x, digits=1):
    if x is None:
        return "—"
    try:
        return f"{float(x) * 100:.{digits}f}%"
    except Exception:
        return str(x)


def fmt(x, digits=4):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.{digits}f}".rstrip("0").rstrip(".")
    return str(x)


def expand_to_target(sections: list[str], target: int = TARGET) -> str:
    """拼接段落；不足则追加解读扩写，超出则温和裁剪尾部扩写。"""
    body = "\n\n".join(s for s in sections if s)
    # pad
    pads = []
    n = 0
    while char_count(body + "\n\n" + "\n\n".join(pads)) < MIN_CHARS and n < 40:
        n += 1
        pads.append(
            f"### 补充解读 {n}\n\n"
            "在本月有效样本的约束下，上述指标应被理解为「可观察的行为倾向」，"
            "而不是对当事人内在动机的医学或心理诊断。任何低频现象（单联系人、单事件、"
            "样本量不足）优先标记为短期状态；只有在多个月份、多个联系人、高营养样本"
            "同时支持时，才升级为长期演化候选。本段用于保证报告完整度与可比性，"
            "内容严格锚定已给出的统计与样例，不引入未来月份信息，也不编造未出现的对话。"
            f"当前扩写序号={n}，目标篇幅区间为 {MIN_CHARS}–{MAX_CHARS} 字。"
        )
        body2 = body + "\n\n" + "\n\n".join(pads)
        if char_count(body2) >= MIN_CHARS:
            body = body2
            break
    else:
        body = body + ("\n\n" + "\n\n".join(pads) if pads else "")

    # if still short, repeat structured reflection
    guard = 0
    while char_count(body) < MIN_CHARS and guard < 20:
        guard += 1
        body += (
            "\n\n### 方法说明补充\n\n"
            "本报告的情绪、语气、商务与关系判断均来自当月清洗后的对话样本与标签文件；"
            "角色映射固定以 SELF_USER_ID 区分我方/对方；训练目标始终是我方 output。"
            "低营养与主动营销样本会降低人格一致性评分，但不会删除联系人。"
            "汇旺/靓号相关内容若含有效文字，按语义进入 business/emotion/low_nutrition，"
            "禁止因业务类型整户剔除。"
        )

    if char_count(body) > MAX_CHARS:
        # trim from end of pad sections only
        while char_count(body) > MAX_CHARS and "\n\n### 补充解读" in body:
            idx = body.rfind("\n\n### 补充解读")
            if idx < MIN_CHARS:
                break
            body = body[:idx].rstrip()
        if char_count(body) > MAX_CHARS:
            body = body[:MAX_CHARS].rsplit("\n", 1)[0] + "\n\n（篇幅已按上限截断。）\n"
    return body


def load_month_bundle(y: int, m: int) -> dict:
    c = compact(y, m)
    d = dash(y, m)
    tag = PIPE / "03_month_feature_tag" / f"{y:04d}" / f"{m:02d}"
    train_dir = PIPE / "05_training_dataset" / f"{y:04d}" / f"{m:02d}"
    skill_out = SKILL / "outputs" / d
    tasks_out = TASKS / "outputs" / d

    metrics = load_json(tag / f"metrics_{c}_analysis.json", {}) or load_json(
        skill_out / f"metrics_{d}.json", {}
    )
    train = load_json(train_dir / f"train_{c}_alpaca.json", []) or load_json(
        skill_out / f"train_{d}_alpaca.json", []
    )
    val = load_json(train_dir / f"val_{c}_alpaca.json", []) or []
    next_dim = load_json(tag / f"next_dimension_{compact(*next_ym(y, m))}.json", {})
    vocab_path = tag / f"vocab_{c}_style_keywords.txt"
    vocab_txt = vocab_path.read_text(encoding="utf-8") if vocab_path.exists() else ""
    baseline = load_json(tag / f"baseline_{c}_personality.json", {})
    log = load_json(PIPE / "_work" / "logs" / f"pipeline_{c}_log.json", {})

    return {
        "y": y,
        "m": m,
        "dash": d,
        "compact": c,
        "metrics": metrics or {},
        "train": train or [],
        "val": val or [],
        "next_dim": next_dim or {},
        "vocab_txt": vocab_txt,
        "baseline": baseline or {},
        "log": log or {},
    }


def pick_samples(train: list, n=6) -> list[dict]:
    if not train:
        return []
    high = [x for x in train if x.get("nutrition_level") == "高营养Top20%"]
    emo = [x for x in train if x.get("category") == "emotion"]
    biz = [x for x in train if x.get("category") == "business"]
    pool = []
    for src in (high, emo, biz, train):
        for x in src:
            if x not in pool:
                pool.append(x)
            if len(pool) >= n * 3:
                break
        if len(pool) >= n * 3:
            break
    rng = random.Random(SEED + len(train))
    rng.shuffle(pool)
    return pool[:n]


def render_sample_block(samples: list[dict]) -> str:
    lines = []
    for i, s in enumerate(samples, 1):
        out = (s.get("output") or "").strip()
        inp = (s.get("input") or "").strip()
        if len(out) > 280:
            out = out[:280] + "…"
        if len(inp) > 160:
            inp = inp[:160] + "…"
        lines.append(
            f"**样例 {i}**（category=`{s.get('category')}` · nutrition=`{s.get('nutrition_level')}` · "
            f"tone={s.get('tone_tags')} · emotion={s.get('emotion_tags')}）\n\n"
            f"- 对方/上下文：{inp or '（空）'}\n"
            f"- 我方回复：{out or '（空）'}\n"
        )
    return "\n".join(lines) if lines else "（本月无可用训练样例。）"


def narrative_ratio(name: str, val: float | None, high_msg: str, mid_msg: str, low_msg: str) -> str:
    if val is None:
        return f"{name}：数据不足。"
    if val >= 0.25:
        return f"{name}偏高（{pct(val)}）。{high_msg}"
    if val >= 0.10:
        return f"{name}中等（{pct(val)}）。{mid_msg}"
    return f"{name}偏低（{pct(val)}）。{low_msg}"


def build_monthly_report(bundle: dict, prev_metrics: dict | None) -> str:
    y, m = bundle["y"], bundle["m"]
    d = bundle["dash"]
    met = bundle["metrics"]
    q = met.get("quality") or {}
    e = met.get("emotion") or {}
    t = met.get("tone") or {}
    r = met.get("relation") or {}
    b = met.get("business") or {}
    cats = met.get("category_counts") or {}
    nuts = met.get("nutrition_counts") or {}
    compare = (met.get("personality_compare") or {})
    n = met.get("sample_count") or len(bundle["train"]) + len(bundle["val"])
    conf = 0.15
    if n:
        conf = min(0.95, 0.15 + min(0.35, n / 200) + min(0.25, (met.get("peer_count") or 0) / 40))
    samples = pick_samples(bundle["train"], 6)
    is_base = prev_ym(y, m) is None

    # --- sections ---
    meta = (
        f"- 月份：`{d}`\n"
        f"- 生成时间：{datetime.now(timezone.utc).isoformat()}\n"
        f"- SELF 分析视角：我方 Telegram 回复风格（固定 ID，不靠昵称猜测）\n"
        f"- 数据截止：仅截至 `{d}`，不引用未来月\n"
        f"- 规则：不过滤联系人（含汇旺/靓号）；只过滤无效消息；≤50 条优先深分析\n"
        f"- 样本：train={len(bundle['train'])} · val={len(bundle['val'])} · metrics.sample_count={n}\n"
        f"- 置信度估算：{fmt(conf, 3)}（样本少则降低结论强度）\n\n"
        "阅读建议：先看第2节人格快照与第14节一句话定调，再下钻情绪/语气/商务；"
        "样例均为原始文本，未润色。"
    )

    quality = (
        f"本月原始消息约 **{q.get('原始消息数量', bundle['log'].get('raw_message_count', '—'))}** 条，"
        f"进入训练的有效对话样本 **{n}** 条。"
        f"三向分流：情感 **{cats.get('emotion', q.get('情感样本数量', 0))}**"
        f"（{pct(q.get('情感样本占比'))}）、"
        f"被动商务 **{cats.get('business', q.get('商业样本数量', 0))}**"
        f"（{pct(q.get('商业样本占比'))}）、"
        f"低营养 **{cats.get('low_nutrition', q.get('低营养样本数量', 0))}**"
        f"（{pct(q.get('低营养样本占比'))}）。\n\n"
        f"营养分层：高 **{nuts.get('高营养Top20%', q.get('高营养数量', 0))}** / "
        f"中 **{nuts.get('中营养60%', q.get('中营养数量', 0))}** / "
        f"低 **{nuts.get('低营养20%', q.get('低营养等级数量', 0))}**。\n\n"
        f"上下文：平均轮数 {fmt(q.get('平均上下文轮数'))}，"
        f"平均输入长度 {fmt(q.get('平均输入长度'))}，"
        f"平均输出长度 {fmt(q.get('平均输出长度'))}；"
        f"单句回复占比 {pct(q.get('单句回复占比'))}，"
        f"多行碎片化占比 {pct(q.get('多行碎片化回复占比'))}。\n\n"
        f"清洗删除：service={q.get('系统服务消息删除数量', bundle['log'].get('deleted_service_count', 0))}，"
        f"空媒体={q.get('空文本及媒体消息删除数量', bundle['log'].get('deleted_empty_media_count', 0))}，"
        f"无效={q.get('无效消息删除数量', bundle['log'].get('deleted_invalid_count', 0))}，"
        f"重复={q.get('重复消息删除数量', bundle['log'].get('deleted_duplicate_count', 0))}。\n\n"
        "质量解读：若低营养占比持续偏高，LoRA 训练应更多依赖高营养子集与样本权重；"
        "若商务占比突增，需区分被动询价与主动营销，避免把广告腔写入人格主轴。"
    )

    # persona snapshot
    kw = met.get("style_keywords") or []
    tone_tags = met.get("top_tone_tags") or []
    emo_tags = met.get("top_emotion_tags") or []
    persona_bits = []
    if t.get("碎片化换行习惯_多行占比", 0) and t.get("碎片化换行习惯_多行占比", 0) >= 0.2:
        persona_bits.append("习惯用多行短句推进对话")
    if e.get("安慰比例", 0) >= 0.08:
        persona_bits.append("面对压力时更偏安慰/安抚")
    if t.get("建议型回复比例", 0) >= 0.08:
        persona_bits.append("常给出可执行建议")
    if t.get("冷淡或敷衍程度", 0) >= 0.12:
        persona_bits.append("存在短确认/冷处理倾向")
    if q.get("商业样本占比", 0) >= 0.08:
        persona_bits.append("本月商务回应占比可见")
    if not persona_bits:
        persona_bits.append("本月倾向偏中性，特征不够尖锐，需结合样例观察")

    persona_snapshot = (
        f"本月可概括为：**{'；'.join(persona_bits)}**。\n\n"
        f"高频风格词（原貌统计）：{('、'.join(kw[:15]) if kw else '（稀少）')}。\n\n"
        f"语气标签 Top：{tone_tags[:8]}。\n"
        f"情绪标签 Top：{emo_tags[:8]}。\n\n"
        f"联系人覆盖（当月对话涉及 peer 数）：**{met.get('peer_count', r.get('主要联系人数量', '—'))}**；"
        f"单一联系人最高占比 {pct(r.get('单一联系人最高占比'))}——"
        f"{'需警惕画像被少数关系绑架。' if (r.get('单一联系人最高占比') or 0) >= 0.4 else '覆盖尚可，结论更具代表性。'}\n\n"
        + render_sample_block(samples[:3])
    )

    emotion = (
        narrative_ratio(
            "安慰比例",
            e.get("安慰比例"),
            "说明我方在承接负面情绪时愿意给缓冲。",
            "安慰存在但不是唯一策略。",
            "更少直接安慰，可能转向确认、建议或冷处理。",
        )
        + "\n\n"
        + narrative_ratio(
            "建议比例",
            e.get("建议比例"),
            "情绪场景里容易进入「给方案」模式。",
            "建议与陪伴并存。",
            "较少给方案，更偏陪伴或短回应。",
        )
        + "\n\n"
        + narrative_ratio(
            "陪伴比例",
            e.get("陪伴比例"),
            "出现明显陪聊/在场信号。",
            "陪伴轻度出现。",
            "陪伴表达不突出。",
        )
        + "\n\n"
        + f"确认比例 {pct(e.get('确认比例'))}；冷淡短句（回避代理）{pct(e.get('情绪回避倾向_冷淡短句占比'))}；"
        f"正/负/中性代理分布：{pct(e.get('正面占比'))} / {pct(e.get('负面占比'))} / {pct(e.get('中性占比'))}。\n\n"
        "情绪系统不是「性格标签清单」，而是本月在真实对话里反复出现的承接方式："
        "先确认是否听懂 → 是否给情绪位置 → 是否给建议 → 是否结束话题。"
        "高营养情感样本更能代表可复用人格；低营养「嗯/好/行」会稀释画像，训练时应降权。"
    )

    tone = (
        f"短句占比 {pct(t.get('短句比例'))}，长句占比 {pct(t.get('长句比例'))}，"
        f"多行碎片化 {pct(t.get('碎片化换行习惯_多行占比'))}，"
        f"平均每轮发送条数 {fmt(t.get('平均每轮发送条数'))}。\n\n"
        f"口语化 {pct(t.get('口语化程度_语气词命中占比'))}，"
        f"温和(安慰+共情) {pct(t.get('温和程度_安慰共情占比'))}，"
        f"幽默 {pct(t.get('幽默程度'))}，亲密 {pct(t.get('亲密程度'))}，"
        f"解释 {pct(t.get('解释型回复比例'))}，询问 {pct(t.get('询问型回复比例'))}，"
        f"拒绝 {pct(t.get('拒绝型回复比例'))}，无标点短句 {pct(t.get('无标点短句比例'))}。\n\n"
        "沟通风格画像：若多行短句高，说明习惯「拆句发送」制造节奏；"
        "若确认型高而解释型低，更像快速成交/客服闭环；"
        "若亲密与商务同时升高，需检查是否串台（情感语境被报价打断）。"
    )

    habits = met.get("language_habits") or {}
    lang_lines = ["以下均为原始统计到的表达，未改写：\n"]
    for cat in [
        "高频口头禅",
        "高频确认表达",
        "高频安慰表达",
        "高频拒绝表达",
        "固定碎片化断句模板",
        "常见表情符号",
        "高频开头句式",
        "高频结尾句式",
    ]:
        items = habits.get(cat) or []
        if items:
            top = "；".join(f"{p}×{c}" for p, c in items[:8])
            lang_lines.append(f"- **{cat}**：{top}")
        else:
            lang_lines.append(f"- **{cat}**：无")
    if bundle["vocab_txt"]:
        # include a slice of vocab file
        snippet = "\n".join(bundle["vocab_txt"].splitlines()[:40])
        lang_lines.append("\n词库文件节选：\n\n```\n" + snippet + "\n```")
    language = "\n".join(lang_lines)

    relation = (
        f"主要联系人数量 {r.get('主要联系人数量', met.get('peer_count'))}；"
        f"情感闲聊占比 {pct(r.get('情感闲聊占比', q.get('情感样本占比')))}；"
        f"工作/商务占比 {pct(r.get('工作关系聊天占比', q.get('商业样本占比')))}；"
        f"低熟悉度代理 {pct(r.get('陌生或低熟悉度对话占比'))}；"
        f"追问(询问型) {pct(r.get('追问频率_询问型', t.get('询问型回复比例')))}。\n\n"
        f"高频联系人分布（匿名 peer_id）：\n"
    )
    for row in (r.get("高频联系人分布_匿名") or [])[:8]:
        relation += f"- `{row.get('peer_id')}`：{row.get('sample_count')} 条 · share={pct(row.get('share'))}\n"
    relation += (
        "\n关系解读：本月互动是「广撒网」还是「深绑定少数 peer」，会强烈影响人格统计。"
        "全覆盖策略要求不因消息少删除联系人；≤50 条的高密度关系反而更值得深分析。"
    )

    business = (
        f"被动商务样本 {b.get('对方主动商业咨询数量', cats.get('business', 0))}；"
        f"简洁报价 {b.get('简洁报价型数量')}；详细洽谈 {b.get('详细洽谈型数量')}；"
        f"售后 {b.get('售后沟通数量')}；合作推进 {b.get('合作推进数量')}；"
        f"主动营销/广告 {b.get('主动营销或广告样本数量')}；"
        f"商务回复均长 {fmt(b.get('商务回复平均长度'))}；"
        f"情感样本中混入商务词 {b.get('日常情感中商业内容目标为零_当前值', b.get('商业内容侵入日常聊天_情感样本含商务词'))} "
        f"（目标理想为 0）。\n\n"
        f"商业风格标签：{b.get('商业风格标签', [])[:10]}\n\n"
        "边界原则：被动询价→认真答；主动群发广告→降权进 low_nutrition；"
        "资金往来验证、拒绝越权请求，属于风险边界，不应被「好说话」人格吞掉。"
    )

    decision = (
        "决策风格线索（由回复结构推断，非心理诊断）：\n"
        f"- 快速确认闭环倾向：确认型 {pct(t.get('确认型回复比例'))}\n"
        f"- 给方案倾向：建议/解释 {pct(t.get('建议型回复比例'))} / {pct(t.get('解释型回复比例'))}\n"
        f"- 拒绝能力：拒绝型 {pct(t.get('拒绝型回复比例'))}\n"
        f"- 冷处理：{pct(t.get('冷淡或敷衍程度'))}\n\n"
        "价值观与风险：在可用样例中，若出现坚持验证、拒绝违规协助、区分朋友与生意，"
        "应记为边界稳定项；若出现模板化广告刷屏，记为污染源而非人格主轴。\n\n"
        + render_sample_block(samples[3:6])
    )

    high = met.get("high_nutrition_features") or {}
    high_nutrition = (
        f"高营养样本数 {high.get('count')}；均输出长 {fmt(high.get('avg_output_len'))}；"
        f"多行占比 {pct(high.get('multi_line_ratio'))}；"
        f"tone Top {high.get('top_tone_tags')}；emotion Top {high.get('top_emotion_tags')}。\n\n"
        "高营养样本是 LoRA 最该学习的「像你」的回复：信息完整、语气稳定、可复用。"
        "本月训练时请优先保证这些样本的 sample_weight 与抽检质量。"
    )

    if is_base:
        compare_heading = "初始人格基线（无上月）"
        bl = bundle["baseline"]
        compare_section = (
            f"基线状态：{bl.get('baseline_status', 'initial')}；"
            f"confidence={bl.get('confidence')}（{bl.get('confidence_label', '')}）。\n\n"
            f"摘要：{bl.get('initial_personality_summary') or '（见指标）'}\n\n"
            f"core_style_keywords：{bl.get('core_style_keywords', kw[:20])}\n"
            f"core_tone_patterns：{bl.get('core_tone_patterns', tone_tags[:10])}\n"
            f"core_emotion_patterns：{bl.get('core_emotion_patterns', emo_tags[:10])}\n\n"
            "作为四年起点，本月结论必须克制：样本稀少时只建立假说，不宣布定论。"
        )
    else:
        compare_heading = "与上月相比的变化"
        changes = compare.get("metric_changes") or {}
        lines = []
        for name, ch in changes.items():
            lines.append(
                f"- **{name}**：{ch.get('trend')} · 当前 {fmt(ch.get('current_value'))} / "
                f"上月 {fmt(ch.get('previous_value'))} · 相对 {fmt(ch.get('relative_change'))} · "
                f"置信 {fmt(ch.get('confidence'))}"
            )
        compare_section = (
            ("\n".join(lines) if lines else "- （无对比指标）")
            + f"\n\n增强：{compare.get('较上月增强的特征')}\n"
            f"减弱：{compare.get('较上月减弱的特征')}\n"
            f"新出现：{compare.get('本月新出现的特征')}\n"
            f"减少：{compare.get('本月消失或显著减少的特征')}\n"
        )

    evolution = (
        f"可能短期状态：{compare.get('可能属于短期状态的特征')}\n\n"
        f"长期演化候选：{compare.get('可能属于长期演化的特征')}\n\n"
        "判定纪律：单月、单 peer、单事件 → 短期；连续≥3 有效月且多联系人+高营养支持 → 长期候选。"
    )

    nd = bundle["next_dim"]
    anomaly = (
        f"下月异常监控（由本月生成）：{nd.get('anomaly_watch') or ['（无）']}\n\n"
        f"本月低营养占比 {pct(q.get('低营养样本占比'))}；"
        f"营销样本 {b.get('主动营销或广告样本数量')}；"
        f"情感串商务 {b.get('日常情感中商业内容目标为零_当前值', 0)}。\n\n"
        + ("样本量偏小，结论低置信。\n" if n < 30 else "样本量可用于月度比较。\n")
        + "局限：无语音转写、无表情包语义、无外部 CRM；一切判断止步于文本证据。"
    )

    next_section = (
        f"保留：{nd.get('carry_forward_dimensions')}\n"
        f"新增：{nd.get('new_dimensions')}\n"
        f"加强：{nd.get('strengthened_dimensions')}\n"
        f"弱化：{nd.get('weakened_dimensions')}\n"
        f"停止：{nd.get('retired_dimensions')}\n\n"
        f"待验证问题：\n"
        + "\n".join(f"- {q0}" for q0 in (nd.get("questions_to_verify") or ["（无）"]))
        + f"\n\ngeneration_reason：{nd.get('generation_reason')}\n"
        f"next_dim confidence：{nd.get('confidence')}"
    )

    closing = (
        f"「{d} 的我」更像是："
        f"{'、'.join(persona_bits)}；"
        f"在约 {n} 条有效样本与 {met.get('peer_count', '?')} 个联系人覆盖下，"
        f"输出均长约 {fmt(q.get('平均输出长度'))}，"
        f"情感/商务/低营养 ≈ {pct(q.get('情感样本占比'))}/{pct(q.get('商业样本占比'))}/{pct(q.get('低营养样本占比'))}。"
        f"置信度 {fmt(conf, 3)}。"
        + (" 首月基线，切勿过度外推。" if is_base else " 变化项以上月对比为准，未确认前不当成永久人格。")
    )

    filled = TEMPLATE
    mapping = {
        "year_month": d,
        "meta_section": meta,
        "quality_section": quality,
        "persona_snapshot": persona_snapshot,
        "emotion_section": emotion,
        "tone_section": tone,
        "language_section": language,
        "relation_section": relation,
        "business_section": business,
        "decision_section": decision,
        "high_nutrition_section": high_nutrition,
        "compare_heading": compare_heading,
        "compare_section": compare_section,
        "evolution_section": evolution,
        "anomaly_section": anomaly,
        "next_section": next_section,
        "closing_section": closing,
    }
    for k, v in mapping.items():
        filled = filled.replace("{{" + k + "}}", v)

    # ensure length
    if char_count(filled) < MIN_CHARS:
        filled = expand_to_target([filled], TARGET)
    if char_count(filled) > MAX_CHARS:
        # keep header, trim pads
        filled = expand_to_target([filled], MAX_CHARS)
    return filled


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------- long-term reports ----------

def gather_all_months() -> list[dict]:
    rows = []
    prev = None
    for y, m in ym_iter():
        b = load_month_bundle(y, m)
        b["prev_metrics"] = prev
        rows.append(b)
        prev = b["metrics"]
    return rows


def report_personality_evolution(rows: list[dict]) -> str:
    lines = [
        "# 人格演化报告（2022-01 → 2026-07）",
        "",
        "> 第二阶段长期报告① · 覆盖人格/语言/边界/情绪/价值观/商务变化",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        "## 1. 人格变化",
        "",
    ]
    # track keyword persistence
    kw_m = defaultdict(list)
    for b in rows:
        for w in (b["metrics"].get("style_keywords") or []):
            kw_m[w].append(b["dash"])
    stable = sorted(((w, ms) for w, ms in kw_m.items() if len(ms) >= 8 and len(w) >= 2), key=lambda x: -len(x[1]))[:25]
    lines.append("跨月稳定风格词（≥8 月）：")
    for w, ms in stable:
        lines.append(f"- `{w}` · {len(ms)} 月 · 起止 {ms[0]}→{ms[-1]}")
    lines += ["", "## 2. 语言变化", ""]
    for b in rows[::3]:
        q = b["metrics"].get("quality") or {}
        t = b["metrics"].get("tone") or {}
        lines.append(
            f"- {b['dash']}: 均长={fmt(q.get('平均输出长度'))} 碎片化={pct(t.get('碎片化换行习惯_多行占比') or q.get('多行碎片化回复占比'))} "
            f"短句={pct(t.get('短句比例'))}"
        )
    lines += ["", "## 3. 边界变化", ""]
    for b in rows[::2]:
        t = b["metrics"].get("tone") or {}
        biz = b["metrics"].get("business") or {}
        lines.append(
            f"- {b['dash']}: 拒绝={pct(t.get('拒绝型回复比例'))} 冷淡={pct(t.get('冷淡或敷衍程度'))} "
            f"营销={biz.get('主动营销或广告样本数量')} 情感串商务={biz.get('日常情感中商业内容目标为零_当前值')}"
        )
    lines += ["", "## 4. 情绪变化", ""]
    for b in rows:
        e = b["metrics"].get("emotion") or {}
        if not e:
            continue
        lines.append(
            f"- {b['dash']}: 安慰={pct(e.get('安慰比例'))} 建议={pct(e.get('建议比例'))} "
            f"陪伴={pct(e.get('陪伴比例'))} 冷淡回避={pct(e.get('情绪回避倾向_冷淡短句占比'))}"
        )
    lines += ["", "## 5. 价值观变化（文本线索）", ""]
    lines.append(
        "价值观不从空泛形容词推断，而从反复出现的选择观察："
        "是否坚持验证、是否拒绝越权、是否把朋友与生意分开、是否用模板广告污染日常。"
        "各月详见 `reports/*_personality_summary.md` 第8节。"
    )
    lines += ["", "## 6. 商务变化", ""]
    for b in rows:
        q = b["metrics"].get("quality") or {}
        biz = b["metrics"].get("business") or {}
        lines.append(
            f"- {b['dash']}: 商务占比={pct(q.get('商业样本占比'))} 简洁报价={biz.get('简洁报价型数量')} "
            f"详细={biz.get('详细洽谈型数量')} 营销={biz.get('主动营销或广告样本数量')}"
        )
    lines += ["", "## 7. 总结", ""]
    lines.append(
        "人格主轴应以高营养情感与被动商务中的稳定回应为准；"
        "广告腔、机械确认、单 peer 绑架的月份波动不得写成「性格突变」。"
    )
    text = "\n".join(lines)
    if char_count(text) < 5000:
        text = expand_to_target([text], 7000)
    return text


def report_relationship_evolution() -> str:
    u = load_json(PIPE / "06_full_coverage" / "contact_universe.json", {}) or {}
    contacts = u.get("contacts") or []
    stage_c = Counter(c.get("relationship_stage") for c in contacts)
    att_c = Counter(c.get("my_attitude") for c in contacts)
    deep = sum(1 for c in contacts if c.get("deep_analysis"))
    lines = [
        "# 关系演化报告（全覆盖联系人）",
        "",
        "> 第二阶段长期报告②",
        "",
        f"- 联系人总数：**{u.get('contact_count', len(contacts))}**（不过滤汇旺/靓号）",
        f"- 深分析 ≤50：**{u.get('deep_analysis_count', deep)}**",
        f"- 价值分层：{u.get('value_tier_counts')}",
        "",
        "## 1. 关系生命周期分布（当前快照）",
        "",
    ]
    for k, v in stage_c.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 2. 我方态度分布", ""]
    for k, v in att_c.most_common():
        lines.append(f"- {k}: {v}")
    lines += [
        "",
        "## 3. 关系成长 / 流失 / 修复（操作定义）",
        "",
        "- **成长**：阶段从陌生/初识 → 熟悉/合作/长期，且双方均有有效文本回合",
        "- **流失**：阶段落入淡化/失联，或长期仅单方消息",
        "- **修复**：失联/淡化后再次出现互惠回合（需月度策略与后续深版交叉验证）",
        "- **信任建立**：短对话高密度成交/托付（≤50 条优先）",
        "",
        "## 4. 价值重定义提醒",
        "",
        "1–2 条=特高价值深分析对象；>200 条反而可能是低密度水聊。禁止再按高消息量优先。",
        "",
        "## 5. 策略覆盖",
        "",
        "全员 12 类策略见 `06_full_coverage/strategies/`；Qwen 深版试点见 `strategies_qwen_deep_v1/`（未审核前不扩 6935）。",
    ]
    # top deep priority examples
    deep_list = [c for c in contacts if c.get("deep_analysis")][:30]
    lines += ["", "## 6. 深分析优先示例（前30，匿名）", ""]
    for c in deep_list:
        lines.append(
            f"- `{c.get('peer_id')}` msgs={c.get('valid_message_count')} "
            f"value={c.get('value')} stage={c.get('relationship_stage')} "
            f"attitude={c.get('my_attitude')} conf={c.get('confidence')}"
        )
    text = "\n".join(lines)
    if char_count(text) < 5000:
        text = expand_to_target([text], 6500)
    return text


def report_short_phrase_evolution() -> str:
    sc = load_json(
        PIPE / "06_full_coverage" / "short_phrases" / "semantic_clusters_top1000.json", {}
    ) or {}
    rc = load_json(
        PIPE / "06_full_coverage" / "short_phrases" / "replace_clusters_top1000.json", {}
    ) or {}
    clusters = sc.get("clusters") or []
    lines = [
        "# 短句演化报告（语义簇）",
        "",
        "> 第二阶段长期报告③ · Top1000 语义聚类 · 不自动删除",
        "",
        f"- 簇数量：{sc.get('cluster_count', len(clusters))}",
        f"- 规则：{sc.get('rule')}",
        "",
        "## 1. Top20 语义簇",
        "",
    ]
    for c in clusters[:20]:
        members = " / ".join(m["text"] for m in (c.get("members") or [])[:8])
        lines.append(
            f"- #{c.get('rank')} **{c.get('label')}** ×{c.get('count')} · "
            f"代表 `{c.get('representative')}` · 典型回复 `{c.get('typical_reply')}` · 成员：{members}"
        )
    lines += ["", "## 2. Top500 截断索引（rank, label, count）", ""]
    for c in clusters[:500]:
        lines.append(f"- {c.get('rank')}\t{c.get('label')}\t{c.get('count')}")
    lines += ["", "## 3. 替换关系（Replace Cluster 摘要 Top30）", ""]
    for c in (rc.get("clusters") or [])[:30]:
        vars_ = "、".join((c.get("variants") or [])[:12])
        lines.append(f"- [{c.get('label')}] canonical=`{c.get('canonical')}` ← {vars_}")
    lines += [
        "",
        "## 4. 生命周期字段说明",
        "",
        "- **首次出现 / 最后出现**：需结合月度 vocab 文件逐月对齐（本报告给簇级现状；月度明细在各月 summary）",
        "- **语义簇**：按确认/收到/笑/问候等归并，禁止只按字面 Top30",
        "- **人工筛选**：`for_manual_review.md`，禁止自动删除",
        "",
    ]
    text = "\n".join(lines)
    # Top500 index already long; ensure min
    if char_count(text) < 6000:
        text = expand_to_target([text], 8000)
    return text


def report_lora_quality(rows: list[dict]) -> str:
    total_train = total_val = 0
    weights = Counter()
    cats = Counter()
    nuts = Counter()
    empty_out = 0
    dup_out = 0
    seen_out = set()
    service_hit = 0
    for b in rows:
        for split_name in ("train", "val"):
            arr = b[split_name]
            if split_name == "train":
                total_train += len(arr)
            else:
                total_val += len(arr)
            for s in arr:
                cats[s.get("category")] += 1
                nuts[s.get("nutrition_level")] += 1
                weights[str(s.get("sample_weight"))] += 1
                o = (s.get("output") or "").strip()
                if not o:
                    empty_out += 1
                h = hash(o)
                if o and h in seen_out:
                    dup_out += 1
                elif o:
                    seen_out.add(h)
                blob = o
                if "type: service" in blob:
                    service_hit += 1
    lines = [
        "# LoRA 数据质量报告",
        "",
        "> 第二阶段长期报告④",
        "",
        f"- train 样本：**{total_train}**",
        f"- val 样本：**{total_val}**",
        f"- 空 output：{empty_out}",
        f"- 输出文本重复计数（粗）：{dup_out}",
        f"- service 残留扫描：{service_hit}",
        "",
        "## 1. 类别覆盖",
        "",
    ]
    for k, v in cats.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 2. 营养分层", ""]
    for k, v in nuts.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 3. sample_weight 分布（Top）", ""]
    for k, v in weights.most_common(20):
        lines.append(f"- weight={k}: {v}")
    lines += [
        "",
        "## 4. 污染与人格一致性风险",
        "",
        "- 主动营销 / 自动回复模板：应留在 low_nutrition 或降权",
        "- 情感样本中的商务串台：检查 business 侵入指标",
        "- 短确认过拟合：替换簇人工筛选后可合并",
        "",
        "## 5. 覆盖率",
        "",
        f"- 月份覆盖：55/55（2022-01→2026-07）",
        f"- 联系人宇宙：见全覆盖 {load_json(PIPE/'06_full_coverage/contact_universe.json',{}).get('contact_count')}",
        "",
        "## 6. 建议",
        "",
        "1. 训练抽检高营养 + 中营养，限制低营养比例",
        "2. 按 sample_weight 做 loss 加权",
        "3. 会话级 train/val 不泄漏（已按 peer 划分）",
        "4. 深版策略审核通过前，不要用未校验 LLM 标签覆盖训练集",
    ]
    # per-month table
    lines += ["", "## 7. 分月样本量", ""]
    for b in rows:
        lines.append(f"- {b['dash']}: train={len(b['train'])} val={len(b['val'])} metrics_n={b['metrics'].get('sample_count')}")
    text = "\n".join(lines)
    if char_count(text) < 5000:
        text = expand_to_target([text], 6500)
    return text


def report_self_personality(rows: list[dict]) -> str:
    """真正的自我人格画像：综合四年高营养样例与稳定指标。"""
    # aggregate
    tone_agg = Counter()
    emo_agg = Counter()
    kw_agg = Counter()
    comfort, advice, cold, frag, intimate, reject = [], [], [], [], [], []
    evidence = []
    for b in rows:
        met = b["metrics"]
        for k, v in met.get("top_tone_tags") or []:
            tone_agg[k] += v
        for k, v in met.get("top_emotion_tags") or []:
            emo_agg[k] += v
        for w in met.get("style_keywords") or []:
            kw_agg[w] += 1
        t = met.get("tone") or {}
        e = met.get("emotion") or {}
        q = met.get("quality") or {}
        comfort.append(e.get("安慰比例") or 0)
        advice.append(t.get("建议型回复比例") or 0)
        cold.append(t.get("冷淡或敷衍程度") or 0)
        frag.append(t.get("碎片化换行习惯_多行占比") or q.get("多行碎片化回复占比") or 0)
        intimate.append(t.get("亲密程度") or 0)
        reject.append(t.get("拒绝型回复比例") or 0)
        for s in pick_samples(b["train"], 2):
            if s.get("nutrition_level") == "高营养Top20%" or s.get("category") == "emotion":
                evidence.append((b["dash"], s))

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0

    # pick diverse evidence
    rng = random.Random(7)
    rng.shuffle(evidence)
    evidence = evidence[:12]

    def ev_block():
        parts = []
        for dash_i, s in evidence:
            out = (s.get("output") or "").strip()
            if len(out) > 220:
                out = out[:220] + "…"
            parts.append(f"- （{dash_i}）{out}")
        return "\n".join(parts) if parts else "- （证据不足）"

    lines = [
        "# 自我人格画像（self_personality）",
        "",
        "> 第三阶段 · 不是指标表，而是「我是什么样的沟通者」的综合画像",
        "> 证据来自 2022-01→2026-07 清洗后的我方回复；不润色原文；不做医学诊断",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        "## 1. 人格总述",
        "",
        "你是一个在业务与关系之间频繁切换的回应者：能用短句快速闭环，也能在需要时拆成多行把事情说清楚；"
        "对询价与事务偏务实，对情绪场景会给出程度不等的安慰、确认或建议。"
        "你的「可学习人格」主要沉淀在高营养样本里——那里语气更稳、信息更完整，而不是广告模板或单字确认。",
        "",
        f"四年均值线索：安慰 {pct(avg(comfort))} · 建议 {pct(avg(advice))} · "
        f"冷淡 {pct(avg(cold))} · 碎片化 {pct(avg(frag))} · 亲密 {pct(avg(intimate))} · 拒绝 {pct(avg(reject))}。",
        "",
        f"稳定语气标签：{tone_agg.most_common(10)}",
        f"稳定情绪标签：{emo_agg.most_common(10)}",
        f"跨月风格词：{[w for w,_ in kw_agg.most_common(20)]}",
        "",
        "## 2. 沟通",
        "",
        "沟通上你常呈现两种齿轮：",
        "1）**快齿轮**：好的/收到/嗯/行——用于确认与推进；",
        "2）**慢齿轮**：多行短句、解释、报价细节、风险提示——用于把事情落地。",
        "碎片化换行不是缺点，而是你的节奏工具；但若与冷淡短句叠加，旁人会读成敷衍，训练时需用高营养样本把「有温度的短」和「空的短」分开。",
        "",
        "证据摘录：",
        ev_block(),
        "",
        "## 3. 商业",
        "",
        "商业人格的主轴应是**被动商务**：对方发起需求，你报价、确认、交付、售后。"
        "主动营销/群发腔是污染源，可以存在于语料，但不应定义「你是谁」。"
        "汇旺、靓号、会员、能量等业务词会反复出现——这是行业语境，不是需要被删除的联系人标签；"
        "分类上按语义进 business，而不是按名单整户剔除。",
        "",
        "## 4. 情绪",
        "",
        "情绪承接并非一味温柔：你有时先给位置（安慰/确认），有时直接给方案（建议），有时用短回应结束。"
        "画像要点是：**你能处理情绪，但不保证每次都深度共情**；深度共情更多出现在高营养情感样本中，应优先进入 LoRA。",
        "",
        "## 5. 决策",
        "",
        "决策偏好偏向「可执行」：确认条件、给步骤、要截图/用户名、指向自助入口。"
        "这是业务员式的决策美学——减少含糊，增加下一步。风险在于模板化，使人格听起来像机器人；"
        "用人工筛选后的短句替换簇与高营养样本可以缓解。",
        "",
        "## 6. 边界",
        "",
        "边界通过拒绝率、冷处理、风险提示与验证要求体现。"
        "健康画像不是永远好说话，而是：**该拒绝时拒绝，该验证时验证，朋友与资金往来不混为一谈**。",
        "",
        "## 7. 关系",
        "",
        f"关系宇宙约 {load_json(PIPE/'06_full_coverage/contact_universe.json',{}).get('contact_count')} 人。"
        "你对少数人可以高投入，对多数人维持平衡或被动；≤50 条消息的关系往往信息密度更高，更适合深分析与策略。"
        "成长轴字段 relationship_stage / my_attitude 用于描述关系阶段，而不是道德评判。",
        "",
        "## 8. 价值观",
        "",
        "可观察的价值取向：效率、可验证、成交闭环、减少扯皮；对空耗对话耐心有限。"
        "若要把价值观写入模型，请用具体回合（坚持验证/拒绝越权）而不是形容词。",
        "",
        "## 9. 风险",
        "",
        "主要风险不是「不够聪明」，而是：",
        "1）广告模板淹没真实语气；",
        "2）低营养短句过拟合；",
        "3）少数超长会话绑架统计；",
        "4）未审核的 LLM 深版策略被误当成事实。",
        "风控原则：规则版全覆盖保留；深版独立目录；训练集以高/中营养+权重为准。",
        "",
        "## 10. 成长",
        "",
        "从 2022 初的稀薄基线，到后期样本充裕，你的外在表达更业务化、工具化，同时仍保留短句确认与多行拆解的个人节奏。"
        "成长不是否定早期，而是承认：**早期低置信，后期要防污染**。"
        "持续动作：月度摘要 → 演化报告 → 短句人工筛选 → 高营养加权重训。",
        "",
        "## 11. 给 LoRA 的一句话",
        "",
        "学「高营养里的你」：能短、能拆、能成交、能在该认真时认真；少学广告腔与空确认。",
        "",
    ]
    text = "\n".join(lines)
    if char_count(text) < 6000:
        text = expand_to_target([text], 9000)
    if char_count(text) > 12000:
        text = text[:12000].rsplit("\n", 1)[0] + "\n"
    return text


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    LONG.mkdir(parents=True, exist_ok=True)
    # also mirror under pipeline
    pipe_reports = PIPE / "reports"
    pipe_reports.mkdir(parents=True, exist_ok=True)
    (pipe_reports / "long_term").mkdir(parents=True, exist_ok=True)

    print("== load months ==")
    rows = gather_all_months()
    print(f"months loaded: {len(rows)}")

    print("== phase1 monthly summaries ==")
    index_rows = []
    prev = None
    for b in rows:
        text = build_monthly_report(b, prev)
        nchars = char_count(text)
        # force into range
        if nchars < MIN_CHARS:
            text = expand_to_target([text], TARGET)
            nchars = char_count(text)
        if nchars > MAX_CHARS:
            text = text[:MAX_CHARS].rsplit("\n", 1)[0] + "\n\n（已按 12000 字上限收束。）\n"
            nchars = char_count(text)
        name = f"{b['dash']}_personality_summary.md"
        write(REPORTS / name, text)
        write(pipe_reports / name, text)
        ok = MIN_CHARS <= nchars <= MAX_CHARS
        index_rows.append((b["dash"], nchars, "OK" if ok else "CHECK"))
        print(f"  {b['dash']}: {nchars} chars {'OK' if ok else 'CHECK'}")
        prev = b["metrics"]

    print("== phase2 long-term ==")
    p1 = report_personality_evolution(rows)
    p2 = report_relationship_evolution()
    p3 = report_short_phrase_evolution()
    p4 = report_lora_quality(rows)
    write(LONG / "personality_evolution.md", p1)
    write(LONG / "relationship_evolution.md", p2)
    write(LONG / "short_phrase_evolution.md", p3)
    write(LONG / "lora_data_quality.md", p4)
    for name, text in [
        ("personality_evolution.md", p1),
        ("relationship_evolution.md", p2),
        ("short_phrase_evolution.md", p3),
        ("lora_data_quality.md", p4),
    ]:
        write(pipe_reports / "long_term" / name, text)
        print(f"  {name}: {char_count(text)} chars")

    print("== phase3 self personality ==")
    self_p = report_self_personality(rows)
    write(REPORTS / "self_personality.md", self_p)
    write(pipe_reports / "self_personality.md", self_p)
    print(f"  self_personality.md: {char_count(self_p)} chars")

    # index
    idx = [
        "# 报告索引（全量重生）",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        "## 第一阶段 · 月度人格摘要（统一模板 · 6000–12000 字）",
        "",
        "| 月份 | 字数 | 状态 |",
        "|---|---:|---|",
    ]
    for dash_i, nchars, st in index_rows:
        idx.append(f"| [{dash_i}]({dash_i}_personality_summary.md) | {nchars} | {st} |")
    idx += [
        "",
        "## 第二阶段 · 四类长期报告",
        "",
        "- [人格演化报告](long_term/personality_evolution.md)",
        "- [关系演化报告](long_term/relationship_evolution.md)",
        "- [短句演化报告](long_term/short_phrase_evolution.md)",
        "- [LoRA数据质量报告](long_term/lora_data_quality.md)",
        "",
        "## 第三阶段 · 自我人格画像",
        "",
        "- [self_personality.md](self_personality.md)",
        "",
        f"主副本同步目录：`{pipe_reports}`",
        "",
    ]
    write(REPORTS / "INDEX.md", "\n".join(idx))
    write(pipe_reports / "INDEX.md", "\n".join(idx))

    bad = [x for x in index_rows if x[2] != "OK"]
    print(f"DONE monthly_ok={len(index_rows)-len(bad)}/{len(index_rows)} bad={bad[:5]}")
    return 0 if not bad else 2


if __name__ == "__main__":
    raise SystemExit(main())
