#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""训练模块四 · 指令 4.1：高频问题归类 + 黄金答案抽取。

基于多客户提问（仍按单条证据隔离取答），将相似问法归入标准问题，
并从高转化对话中挑选最精准、最能解决问题的回复作为黄金答案。

硬约束：
- 归类可跨客户聚合统计
- 黄金答案必须可追溯到单 dialog/context 证据，禁止串台捏造

示例：
  python3 extract_golden_qa_4_1.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SKILL = Path(__file__).resolve().parent

# ---------- 标准问题目录（归类锚点）----------
CANONICAL = [
    {
        "id": "STD_PRICE_GENERAL",
        "standard_q": "会员怎么收费？各档多少钱？",
        "topic": "price",
        "patterns": [r"多少钱", r"什么价", r"啥价", r"报价", r"怎么收费", r"价格"],
    },
    {
        "id": "STD_PRICE_3M",
        "standard_q": "开通 3 个月会员多少钱？",
        "topic": "price",
        "patterns": [r"3\s*个月", r"三个月", r"三月"],
        "require_any": [r"钱", r"价", r"[uUＵ]", r"开", r"会员"],
    },
    {
        "id": "STD_PRICE_6M",
        "standard_q": "开通 6 个月会员多少钱？",
        "topic": "price",
        "patterns": [r"6\s*个月", r"六个月", r"半年"],
        "require_any": [r"钱", r"价", r"[uUＵ]", r"开", r"会员"],
    },
    {
        "id": "STD_PRICE_12M",
        "standard_q": "开通 12 个月 / 一年会员多少钱？",
        "topic": "price",
        "patterns": [r"12\s*个月", r"一年", r"12个月"],
        "require_any": [r"钱", r"价", r"[uUＵ]", r"开", r"会员"],
    },
    {
        "id": "STD_PRICE_RENEW",
        "standard_q": "老客户回购 / 续费怎么算？",
        "topic": "price",
        "patterns": [r"回购", r"续费", r"老客户", r"二次"],
    },
    {
        "id": "STD_HOW_OPEN",
        "standard_q": "怎么开通飞机会员？需要提供什么？",
        "topic": "process",
        "patterns": [r"怎么开", r"如何开通", r"怎么弄", r"怎么搞", r"怎么办理", r"开一下", r"帮我开", r"给我开"],
    },
    {
        "id": "STD_NEED_USERNAME",
        "standard_q": "开通要不要账号密码？只要用户名可以吗？",
        "topic": "process",
        "patterns": [r"用户名", r"账号密码", r"要密码", r"登(录|你)账号", r"发用户名"],
    },
    {
        "id": "STD_PAY_HUIWANG",
        "standard_q": "可以用汇旺付款吗？转到哪个账号？",
        "topic": "ops",
        "patterns": [r"汇旺", r"怎么付", r"怎么转", r"转哪", r"付款方式", r"怎么转账"],
    },
    {
        "id": "STD_PAY_USDT",
        "standard_q": "可以用 U / USDT 付款吗？地址发一下？",
        "topic": "ops",
        "patterns": [r"\bU\b", r"USDT", r"U钱包", r"U地址", r"用U"],
    },
    {
        "id": "STD_AFTER_PAY",
        "standard_q": "付款后要发什么？多久能开通？",
        "topic": "ops",
        "patterns": [r"付款后", r"转完", r"截图", r"多久", r"多长时间", r"几分钟", r"开好了吗"],
    },
    {
        "id": "STD_PACKAGE_CHOICE",
        "standard_q": "三个月、六个月、一年怎么选？",
        "topic": "package",
        "patterns": [r"哪个合适", r"怎么选", r"推荐哪个", r"套餐", r"开哪个"],
    },
]

# 各标准问题的答案必须命中的相关性线索（否则丢弃）
ANSWER_RELEVANCE = {
    "STD_PRICE_GENERAL": [r"\d+\s*[uUＵ]", r"秒开", r"回购", r"个月"],
    "STD_PRICE_3M": [r"3\s*个月", r"三个月", r"38|30|\d+\s*[uUＵ]"],
    "STD_PRICE_6M": [r"6\s*个月", r"六个月", r"半年", r"58|45|\d+\s*[uUＵ]"],
    "STD_PRICE_12M": [r"12\s*个月", r"一年", r"88|70|\d+\s*[uUＵ]"],
    "STD_PRICE_RENEW": [r"回购", r"续费", r"老客户", r"\d+\s*[uUＵ]"],
    "STD_HOW_OPEN": [r"用户名", r"开通", r"流程", r"付款", r"秒开", r"提供"],
    "STD_NEED_USERNAME": [r"用户名", r"密码", r"不登", r"即可", r"只要"],
    "STD_PAY_HUIWANG": [r"汇旺", r"1688|68168", r"转", r"账号"],
    "STD_PAY_USDT": [r"USDT", r"\bU\b", r"U钱包", r"U地址", r"TQQc", r"TRC20", r"钱包"],
    "STD_AFTER_PAY": [r"截图", r"用户名", r"分钟", r"开通", r"付款后"],
    "STD_PACKAGE_CHOICE": [r"个月", r"一年", r"半年", r"按需", r"看你", r"推荐"],
}

# 明显答非所问 / 噪声
ANSWER_REJECT = re.compile(
    r"(口播教学|已收入|总入款|激活流程|1800\*213|妈的|不要了|"
    r"超级重要|骗子|自助开通飞机会员】|机器人自助操作即可)",
    re.I,
)

# 核心标准问题的兜底黄金答（无合格证据时使用；短句可执行）
FALLBACK_GOLDEN = {
    "STD_PRICE_GENERAL": "3个月/6个月/12个月按当时报价；要用户名即可开，付款后截图确认。",
    "STD_PRICE_3M": "3个月按当时标准价（常见约30–38U），付款后发用户名即可开。",
    "STD_PRICE_6M": "6个月按当时标准价（常见约45–58U），付款后发用户名即可开。",
    "STD_PRICE_12M": "12个月按当时标准价（常见约70–88U），付款后发用户名即可开。",
    "STD_PRICE_RENEW": "老客户回购比秒开便宜一档，发用户名续费即可，以下单核实为准。",
    "STD_HOW_OPEN": "发飞机用户名，选好月份，按汇旺或U付款后截图，几分钟开通。",
    "STD_NEED_USERNAME": "不用密码，只要飞机用户名就能开，不登你账号。",
    "STD_PAY_HUIWANG": "可以汇旺转约定收款账号，转完发截图和用户名。",
    "STD_PAY_USDT": "可以付U，发当时收款地址，转完截图+用户名。",
    "STD_AFTER_PAY": "付款后发转账截图和@用户名，一般几分钟开通。",
    "STD_PACKAGE_CHOICE": "常用就开3或6个月；长期用再上一年，按预算选。",
}


def answer_relevant(canon_id: str, a: str) -> bool:
    if ANSWER_REJECT.search(a or ""):
        return False
    if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,32}", (a or "").strip()):
        return False
    clues = ANSWER_RELEVANCE.get(canon_id) or []
    if not clues:
        return True
    return any(re.search(p, a, re.I) for p in clues)


AUTO_JUNK = re.compile(
    r"(北北已收到|自动回复|点击下方|业务繁忙|暂时不在请留言|正在转接)",
    re.I,
)
HEAVY_AD = re.compile(
    r"(代开(?:会员)?只需提供|有机会来我店里喝茶|无人值守，自动开通|成为尊贵的Premium)",
    re.I,
)
PRICE_FACT = re.compile(
    r"(?P<pkg>\d+\s*个月(?:会员)?)\s*(?P<price>\d+(?:\.\d+)?)\s*(?P<unit>[uUＵ])",
    re.I,
)


def norm_q(s: str) -> str:
    s = re.sub(r"\s+", "", (s or "").strip().lower())
    s = re.sub(r"[？?！!。．\.，,、~～]+$", "", s)
    return s


def char_len(s: str) -> int:
    return len(re.sub(r"\s+", "", s or ""))


def match_canonical(q: str) -> tuple[str, str, str] | None:
    """返回 (canon_id, standard_q, topic)。更具体的价格档优先。"""
    # 先尝试具体档位
    order = [
        "STD_PRICE_3M",
        "STD_PRICE_6M",
        "STD_PRICE_12M",
        "STD_PRICE_RENEW",
        "STD_NEED_USERNAME",
        "STD_PAY_HUIWANG",
        "STD_PAY_USDT",
        "STD_AFTER_PAY",
        "STD_HOW_OPEN",
        "STD_PACKAGE_CHOICE",
        "STD_PRICE_GENERAL",
    ]
    by_id = {c["id"]: c for c in CANONICAL}
    for cid in order:
        c = by_id[cid]
        if not any(re.search(p, q, re.I) for p in c["patterns"]):
            continue
        req = c.get("require_any") or []
        if req and not any(re.search(p, q, re.I) for p in req):
            continue
        return c["id"], c["standard_q"], c["topic"]
    return None


def clean_answer(a: str, *, max_chars: int = 220) -> str:
    lines = []
    for ln in (a or "").replace("\r\n", "\n").split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        if re.fullmatch(r"[—\-_=✨💎🎫✅🎁💰⚡️📌・·\s]{2,}", ln):
            continue
        lines.append(ln)
    out = "\n".join(lines).strip()
    if len(out) > max_chars:
        # 优先保留含价目/步骤的行
        keep = []
        for ln in lines:
            if PRICE_FACT.search(ln) or re.search(r"(用户名|汇旺|流程|开通|截图|分钟)", ln):
                keep.append(ln)
            if char_len("\n".join(keep)) >= 80:
                break
        out = "\n".join(keep) if keep else out[: max_chars - 1] + "…"
    return out.strip()


def is_bad_answer(a: str) -> bool:
    if not a or char_len(a) < 2:
        return True
    if AUTO_JUNK.search(a):
        return True
    if ANSWER_REJECT.search(a):
        return True
    return False


def answer_precision_score(a: str, canon_id: str = "") -> float:
    """精准度：短而含关键信息分高；超长广告墙降权。"""
    if is_bad_answer(a):
        return -10.0
    if canon_id and not answer_relevant(canon_id, a):
        return -8.0
    n = char_len(a)
    score = 5.0
    if PRICE_FACT.search(a):
        score += 4.0
    if re.search(r"(用户名|汇旺|截图|分钟|流程|不登)", a):
        score += 2.0
    if 8 <= n <= 80:
        score += 5.0
    elif 80 < n <= 160:
        score += 2.0
    elif n > 220:
        score -= 4.0
    if HEAVY_AD.search(a):
        score -= 3.0
    if a.count("秒开") >= 3 and a.count("回购") >= 2:
        score -= 2.0
    # 规范短答加分
    if a.endswith("以下单核实为准。") or a.endswith("以下单核实为准"):
        score += 1.5
    return score


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def collect_candidates(
    qa_rows: list[dict],
    contexts: list[dict],
) -> list[dict]:
    """收集 (variant_q, answer, meta) 候选。"""
    cands: list[dict] = []

    # 来自 2.1
    for r in qa_rows:
        q = (r.get("q") or "").strip()
        a = (r.get("a") or "").strip()
        if not q or not a:
            continue
        hit = match_canonical(q)
        if not hit:
            continue
        cid, std_q, topic = hit
        cands.append(
            {
                "canon_id": cid,
                "standard_q": std_q,
                "topic": topic,
                "variant_q": q,
                "answer": clean_answer(a),
                "source": "module2_1",
                "dialog_id": r.get("dialog_id"),
                "peer_id": r.get("peer_id"),
                "base_confidence": float(r.get("confidence") or 0.6),
                "conversion_bonus": 0.0,
                "support_hint": int(r.get("support") or 1),
            }
        )

    # 来自 2.2 高转化上下文：客户问 → 随后我方答
    ASK = re.compile(
        r"(多少钱|什么价|怎么开|怎么弄|开会员|用户名|汇旺|怎么付|怎么转|续费|回购|几个月|报价)",
        re.I,
    )
    for ctx in contexts:
        turns = ctx.get("turns") or []
        conv = 3.0 if ctx.get("tier") == "tier1" else 1.5 if ctx.get("tier") == "tier2" else 0.5
        if "deal" in (ctx.get("stages") or []):
            conv += 1.5
        if "bargain" in (ctx.get("stages") or []):
            conv += 0.5
        for i, t in enumerate(turns):
            if t.get("role") != "peer":
                continue
            q = (t.get("text") or "").strip()
            if not ASK.search(q) or len(q) < 3 or len(q) > 60:
                continue
            hit = match_canonical(q)
            if not hit:
                continue
            cid, std_q, topic = hit
            # 找后续我方回答
            ans = None
            for j in range(i + 1, min(len(turns), i + 6)):
                if turns[j].get("role") != "self":
                    continue
                a = (turns[j].get("text") or "").strip()
                if is_bad_answer(a):
                    continue
                ans = a
                break
            if not ans:
                continue
            cands.append(
                {
                    "canon_id": cid,
                    "standard_q": std_q,
                    "topic": topic,
                    "variant_q": q,
                    "answer": clean_answer(ans),
                    "source": "module2_2_success",
                    "dialog_id": ctx.get("dialog_id"),
                    "peer_id": ctx.get("peer_id"),
                    "base_confidence": 0.7,
                    "conversion_bonus": conv,
                    "support_hint": 1,
                    "context_score": ctx.get("score"),
                    "context_tier": ctx.get("tier"),
                }
            )
    return cands


def pick_golden(group: list[dict]) -> tuple[dict, list[dict]]:
    """在同一标准问题下选黄金答案，并返回变体问法 Top。"""
    canon_id = group[0]["canon_id"] if group else ""
    by_ans: dict[str, dict] = {}
    for c in group:
        a = c["answer"]
        if is_bad_answer(a) or not answer_relevant(c["canon_id"], a):
            continue
        key = norm_q(a)[:160]
        if not key:
            continue
        prec = answer_precision_score(a, c["canon_id"])
        if prec < 0:
            continue
        score = (
            prec
            + c.get("conversion_bonus", 0) * 1.2
            + c.get("base_confidence", 0) * 3
            + min(5, c.get("support_hint", 1)) * 0.3
        )
        if c.get("source") == "aggregated_price_norm":
            score += 4.0
        if HEAVY_AD.search(a):
            score -= 2
        if key not in by_ans or score > by_ans[key]["golden_score"]:
            by_ans[key] = {
                **c,
                "golden_score": round(score, 3),
                "precision": round(prec, 3),
                "hit_count": by_ans.get(key, {}).get("hit_count", 0) + 1,
            }
        else:
            by_ans[key]["hit_count"] = by_ans[key].get("hit_count", 1) + 1
            by_ans[key]["golden_score"] = round(
                max(by_ans[key]["golden_score"], score) + 0.05, 3
            )

    ranked = sorted(by_ans.values(), key=lambda x: (-x["golden_score"], -x.get("hit_count", 0)))

    variants = []
    seen_v = set()
    for c in sorted(group, key=lambda x: -x.get("conversion_bonus", 0)):
        v = c["variant_q"].strip()
        nk = norm_q(v)
        if nk in seen_v or len(nk) < 2:
            continue
        seen_v.add(nk)
        variants.append(v)
        if len(variants) >= 12:
            break

    def make_fallback() -> dict:
        fb = FALLBACK_GOLDEN.get(canon_id) or "按约定流程办理，具体以下单核实为准。"
        return {
            "canon_id": canon_id,
            "standard_q": group[0]["standard_q"],
            "topic": group[0]["topic"],
            "variant_q": group[0]["standard_q"],
            "answer": fb,
            "source": "fallback_curated",
            "dialog_id": None,
            "peer_id": None,
            "base_confidence": 0.85,
            "conversion_bonus": 0.0,
            "support_hint": len(group),
            "golden_score": 14.0,
            "precision": answer_precision_score(fb, canon_id),
            "hit_count": 1,
        }

    if not ranked:
        return make_fallback(), variants

    best = ranked[0]
    # 过长广告/弱精准 → 改用兜底或次优短答
    if char_len(best["answer"]) > 140 or best.get("precision", 0) < 6:
        short = next(
            (
                x
                for x in ranked
                if char_len(x["answer"]) <= 100 and x.get("precision", 0) >= 8
            ),
            None,
        )
        if short:
            best = short
        elif canon_id in FALLBACK_GOLDEN:
            best = make_fallback()

    # 语义质量闸：不合格则用兜底短黄金答
    gates = {
        "STD_PRICE_RENEW": lambda a: bool(
            re.search(r"回购|续费|老客户", a) and re.search(r"\d|[uU]|便宜|档", a)
        ),
        "STD_HOW_OPEN": lambda a: bool(
            re.search(r"用户名", a) and re.search(r"付款|汇旺|截图|开通|选", a)
        ),
        "STD_NEED_USERNAME": lambda a: bool(
            re.search(r"用户名", a)
            and re.search(r"密码|不登|只要|即可|不用", a)
            and char_len(a) <= 90
        ),
        "STD_PAY_USDT": lambda a: bool(
            re.search(r"USDT|付U|U地址|收款地址", a)
            and "至少 1" not in a
            and char_len(a) <= 100
        ),
        "STD_AFTER_PAY": lambda a: bool(re.search(r"截图", a) and re.search(r"用户名|分钟|开通", a)),
        "STD_PRICE_GENERAL": lambda a: bool(
            re.search(r"3.*月|个月", a) and re.search(r"[uUＵ]", a) and char_len(a) <= 120
        ),
    }
    gate = gates.get(canon_id)
    if gate and not gate(best["answer"]) and canon_id in FALLBACK_GOLDEN:
        best = make_fallback()

    return best, variants


def compose_normalized_goldens(cands: list[dict]) -> list[dict]:
    """对价格类补充规范化黄金句（来自高频价目，可追溯为 aggregated）。"""
    facts = Counter()
    for c in cands:
        if c["topic"] != "price":
            continue
        for m in PRICE_FACT.finditer(c["answer"]):
            pkg = re.sub(r"\s+", "", m.group("pkg")).replace("会员", "")
            price = m.group("price")
            unit = m.group("unit").upper().replace("Ｕ", "U")
            facts[(pkg, price, unit)] += 1
    extras = []
    # 取各档最高频
    best_by_pkg: dict[str, tuple] = {}
    for (pkg, price, unit), cnt in facts.most_common():
        if pkg not in best_by_pkg or cnt > best_by_pkg[pkg][3]:
            best_by_pkg[pkg] = (pkg, price, unit, cnt)
    mapping = {
        "3个月": "STD_PRICE_3M",
        "6个月": "STD_PRICE_6M",
        "12个月": "STD_PRICE_12M",
    }
    std_q_map = {c["id"]: c["standard_q"] for c in CANONICAL}
    for pkg, cid in mapping.items():
        if pkg not in best_by_pkg:
            continue
        _, price, unit, cnt = best_by_pkg[pkg]
        if cnt < 3:
            continue
        a = f"{pkg}标准价 {price}{unit}。付款后发用户名，一般几分钟开通。以下单核实为准。"
        extras.append(
            {
                "canon_id": cid,
                "standard_q": std_q_map[cid],
                "topic": "price",
                "variant_q": f"{pkg}多少钱",
                "answer": a,
                "source": "aggregated_price_norm",
                "dialog_id": None,
                "peer_id": None,
                "base_confidence": 0.92,
                "conversion_bonus": 2.0,
                "support_hint": cnt,
            }
        )
    # 通用价目总览
    if len(best_by_pkg) >= 2:
        parts = [f"{p}{best_by_pkg[p][1]}{best_by_pkg[p][2]}" for p in ("3个月", "6个月", "12个月") if p in best_by_pkg]
        if parts:
            extras.append(
                {
                    "canon_id": "STD_PRICE_GENERAL",
                    "standard_q": std_q_map["STD_PRICE_GENERAL"],
                    "topic": "price",
                    "variant_q": "会员多少钱",
                    "answer": "常用档：" + " / ".join(parts) + "。要用户名即可开，付款后截图确认。以下单核实为准。",
                    "source": "aggregated_price_norm",
                    "dialog_id": None,
                    "peer_id": None,
                    "base_confidence": 0.9,
                    "conversion_bonus": 2.0,
                    "support_hint": sum(best_by_pkg[p][3] for p in best_by_pkg),
                }
            )
    return extras


def to_markdown(items: list[dict]) -> str:
    lines = [
        "# 标准化知识库 · 黄金问答（指令 4.1）",
        "",
        "相似问法已归入标准问题；黄金答案优先取高转化对话中的精准回复。",
        "",
    ]
    by_topic: dict[str, list] = defaultdict(list)
    for it in items:
        by_topic[it["topic"]].append(it)
    for topic in ("price", "process", "ops", "package"):
        group = by_topic.get(topic) or []
        if not group:
            continue
        lines.append(f"## {topic}")
        lines.append("")
        for it in group:
            lines.append(f"### {it['canon_id']} · {it['standard_q']}")
            lines.append("")
            lines.append(f"**黄金答案 (A):** {it['golden_a']}")
            lines.append("")
            lines.append(
                f"- score={it['golden_score']} · source={it['source']} · variants={it['variant_count']} · support≈{it.get('support_hint', 1)}"
            )
            if it.get("dialog_id"):
                lines.append(f"- evidence_dialog=`{it['dialog_id']}`")
            if it.get("variant_questions"):
                lines.append("- 相似问法:")
                for v in it["variant_questions"][:8]:
                    lines.append(f"  - {v}")
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="指令 4.1 高频问题与黄金答案")
    ap.add_argument(
        "--qa",
        type=Path,
        default=SKILL / "knowledge" / "qa" / "standard_qa.jsonl",
    )
    ap.add_argument(
        "--contexts",
        type=Path,
        default=SKILL / "knowledge" / "success_contexts" / "success_contexts.jsonl",
    )
    ap.add_argument(
        "--knowledge-dir",
        type=Path,
        default=SKILL / "knowledge" / "golden_qa",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=SKILL / "train_data_refined" / "module4_1",
    )
    args = ap.parse_args()

    qa_rows = load_jsonl(args.qa)
    contexts = load_jsonl(args.contexts)
    cands = collect_candidates(qa_rows, contexts)
    cands.extend(compose_normalized_goldens(cands))

    by_canon: dict[str, list] = defaultdict(list)
    for c in cands:
        by_canon[c["canon_id"]].append(c)

    items = []
    for cid, group in by_canon.items():
        golden, variants = pick_golden(group)
        if not golden:
            continue
        items.append(
            {
                "id": hashlib.sha1(cid.encode()).hexdigest()[:12],
                "canon_id": cid,
                "standard_q": golden["standard_q"],
                "topic": golden["topic"],
                "golden_a": golden["answer"],
                "golden_score": golden["golden_score"],
                "precision": golden.get("precision"),
                "source": golden.get("source"),
                "dialog_id": golden.get("dialog_id"),
                "peer_id": golden.get("peer_id"),
                "support_hint": golden.get("support_hint") or golden.get("hit_count") or len(group),
                "variant_count": len(variants),
                "variant_questions": variants,
                "conversion_bonus": golden.get("conversion_bonus"),
                "sample_type": "黄金标准答案",
                "instruction": "4.1",
            }
        )

    # 稳定排序：按目录顺序
    order = {c["id"]: i for i, c in enumerate(CANONICAL)}
    items.sort(key=lambda x: (order.get(x["canon_id"], 99), -x["golden_score"]))

    know = args.knowledge_dir if args.knowledge_dir.is_absolute() else SKILL / args.knowledge_dir
    out = args.output_dir if args.output_dir.is_absolute() else SKILL / args.output_dir
    know.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    jsonl_path = know / "golden_qa.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    md_path = know / "golden_qa.md"
    md_path.write_text(to_markdown(items), encoding="utf-8")

    # 训练行：标准问 → 黄金答
    train_path = out / "train_golden_qa.jsonl"
    with train_path.open("w", encoding="utf-8") as f:
        for it in items:
            variants = it.get("variant_questions") or [it["standard_q"]]
            # 标准问 + 若干变体各一条，指向同一黄金答
            for v in [it["standard_q"]] + variants[:5]:
                row = {
                    "instruction": "用标准化、简洁、可执行的黄金答案回答客户问题。保持真人短句风格，不要堆长广告。",
                    "input": v,
                    "output": it["golden_a"],
                    "canon_id": it["canon_id"],
                    "standard_q": it["standard_q"],
                    "sample_type": "黄金标准答案",
                    "sample_weight": 2.0,
                    "dialog_id": it.get("dialog_id") or f"golden_{it['canon_id']}",
                    "from_module": "4.1",
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    (out / "golden_qa.jsonl").write_text(jsonl_path.read_text(encoding="utf-8"), encoding="utf-8")
    (out / "golden_qa.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

    report = {
        "instruction": "4.1",
        "module": "kb_optimize_golden_qa",
        "qa_in": len(qa_rows),
        "contexts_in": len(contexts),
        "candidates": len(cands),
        "canonical_covered": len(items),
        "topic_counts": dict(Counter(it["topic"] for it in items)),
        "paths": {
            "golden_jsonl": str(jsonl_path),
            "golden_md": str(md_path),
            "train_jsonl": str(train_path),
        },
        "items": [
            {
                "canon_id": it["canon_id"],
                "standard_q": it["standard_q"],
                "golden_a": it["golden_a"][:120],
                "score": it["golden_score"],
                "variants": it["variant_count"],
                "source": it["source"],
            }
            for it in items
        ],
    }
    (out / "report_4_1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "last_run.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
