#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""训练模块二 · 指令 2.1：从清洗对话提取标准问答（价格/流程/操作）。

硬约束：
- 单条样本内取证（dialog_id 隔离），禁止跨客户拼答案
- 答案优先取我方 output 中的明确信息；原文可追溯
- 输出 Q/A 供 knowledge/qa 使用

示例：
  python3 extract_standard_qa_2_1.py \\
    --input train_data_final/train.jsonl \\
    --refined train_data_refined/module1_1/train_refined_1_1.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

SKILL = Path(__file__).resolve().parent

# 对方侧：像在问标准信息
Q_HINT = re.compile(
    r"(多少钱|什么价|价格|报价|怎么开|怎么弄|怎么搞|怎么操作|流程|步骤|"
    r"如何开通|怎么开通|多少[uU]|几个月|会员|能量|闪兑|汇旺|地址|账号|"
    r"服务包|套餐|合同|续费|回购)",
    re.I,
)

# 我方侧：像在给标准答案
A_HINT = re.compile(
    r"(只要|需要提供|秒开|回购|流程|第一步|第二步|转账|汇旺|地址|用户名|"
    r"\d+\s*[uUＵ刀\$￥]|个月|开通|办理|步骤)",
    re.I,
)

# 结构化价目
PRICE_LINE = re.compile(
    r"(?:秒开|回购)\s*[【\[]?(?P<pkg>\d+\s*个月(?:会员)?)[】\]]?\s*(?P<price>\d+(?:\.\d+)?)\s*(?P<unit>[uUＵ刀\$￥]|USD|USDT)?",
    re.I,
)
PRICE_INLINE = re.compile(
    r"(?P<pkg>\d+\s*个月(?:会员)?)\s*(?P<price>\d+(?:\.\d+)?)\s*(?P<unit>[uUＵ刀\$￥])",
    re.I,
)

TOPIC_PRICE = re.compile(r"(价|多少钱|多少[uU]|报价|回购|秒开|\d+\s*[uUＵ])", re.I)
TOPIC_PROCESS = re.compile(r"(流程|步骤|怎么开|怎么弄|如何|开通|办理|操作)", re.I)
TOPIC_PACKAGE = re.compile(r"(套餐|服务包|个月|会员|能量|闪兑|靓号)", re.I)
TOPIC_OPS = re.compile(r"(用户名|地址|汇旺|转账|截图|账号|续费)", re.I)

TEMPLATE_NOISE = re.compile(r"[—\-_=]{4,}|💖|祝您每天|自动回复消息")
HEAVY_TEMPLATE = re.compile(
    r"(代开(?:会员)?只需提供|秒开【\d+个月|老客户二次回购|包售后包维护|"
    r"欢迎选择.支付|代开飞机会员流程|飞机会员开通流程|无人值守，自动开通|"
    r"成为尊贵的Premium|仅飞机用户名即可开通)",
    re.I,
)
Q_PREFIX_NOISE = re.compile(r"^[\d一二三四五六七八九十\.、，,\s号]+")


AUTO_REPLY = re.compile(
    r"(北北已收到|正在转接人工|自动回复|请直接留言|我可能正在忙|因近期业务激增|"
    r"点击下方机器人|点击下方蓝色|业务繁忙|暂时不在请留言|看到会第一时间回复)",
    re.I,
)


def is_bad_question(q: str) -> bool:
    if not q or len(q) < 4 or len(q) > 48:
        return True
    if q.count("http") or "t.me/" in q:
        return True
    if HEAVY_TEMPLATE.search(q):
        return True
    # 纯粘贴价目不当问题
    if q.count("U/$") >= 2 or q.count("秒开") >= 1:
        return True
    return False


def is_bad_answer(a: str) -> bool:
    if not a or len(a) < 4:
        return True
    if AUTO_REPLY.search(a):
        return True
    if a.count("💸") >= 3:
        return True
    return False


def is_heavy_template(a: str) -> bool:
    if HEAVY_TEMPLATE.search(a) and (a.count("\n") >= 3 or len(a) > 140):
        return True
    # 长广告体 + 含多条价目
    if len(a) > 160 and len(extract_price_facts(a)) >= 2:
        return True
    return False


def clean_question(q: str) -> str:
    q = q.strip()
    # 反复去掉开头序号/噪音
    for _ in range(4):
        nq = Q_PREFIX_NOISE.sub("", q).strip(" ，,。")
        if nq == q:
            break
        q = nq
    return q.strip(" ，,") or q

def norm_ws(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def last_question_chunk(text: str, *, max_chars: int = 80) -> str:
    """从对方 input 取末尾更像「当前问题」的片段。"""
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    if not lines:
        return ""
    # 从后往前找带问询词的行
    for ln in reversed(lines):
        if Q_HINT.search(ln) and len(ln) <= max_chars:
            return ln
    # 合并末尾 1–3 条短句
    tail = lines[-3:]
    joined = "，".join(tail)
    if len(joined) > max_chars:
        joined = lines[-1][:max_chars]
    return joined


def clean_answer(text: str, *, max_chars: int = 280) -> str:
    lines = []
    for ln in text.replace("\r\n", "\n").split("\n"):
        ln = ln.strip()
        if not ln or TEMPLATE_NOISE.fullmatch(ln) or set(ln) <= set("-—_=✨💎"):
            continue
        # 去掉纯装饰行
        if re.fullmatch(r"[—\-_=]{3,}", ln):
            continue
        lines.append(ln)
    out = norm_ws("\n".join(lines))
    if len(out) > max_chars:
        out = out[: max_chars - 1].rstrip() + "…"
    return out


def detect_topic(q: str, a: str) -> str:
    blob = q + "\n" + a
    scores = {
        "price": 1 if TOPIC_PRICE.search(blob) else 0,
        "process": 1 if TOPIC_PROCESS.search(blob) else 0,
        "package": 1 if TOPIC_PACKAGE.search(blob) else 0,
        "ops": 1 if TOPIC_OPS.search(blob) else 0,
    }
    # 价目行加权
    if PRICE_LINE.search(a) or PRICE_INLINE.search(a):
        scores["price"] += 2
        scores["package"] += 1
    topic = max(scores, key=lambda k: scores[k])
    if scores[topic] == 0:
        return "general"
    return topic


def extract_price_facts(answer: str) -> list[dict]:
    facts = []
    for rx in (PRICE_LINE, PRICE_INLINE):
        for m in rx.finditer(answer):
            pkg = re.sub(r"\s+", "", m.group("pkg"))
            price = m.group("price")
            unit = (m.group("unit") or "U").upper().replace("Ｕ", "U")
            if unit in ("刀", "$"):
                unit = "U"
            # 过滤噪声包名
            if not re.search(r"月|年", pkg):
                continue
            if len(pkg) > 12 or re.search(r"(汇旺|现价|开通|流程|账号|\$)", pkg):
                continue
            try:
                if float(price) <= 0 or float(price) > 500:
                    continue
            except ValueError:
                continue
            pkg = re.sub(r"会员$", "", pkg)
            if "个月" not in pkg and "年" not in pkg:
                continue
            facts.append({"package": pkg, "price": price, "unit": unit})
    # dedupe（3个月 / 3个月会员 合并到 3个月）
    seen = set()
    out = []
    for f in facts:
        key = (f["package"], f["price"], f["unit"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out

def qa_key(q: str, a: str) -> str:
    qn = re.sub(r"\s+", "", q.lower())
    an = re.sub(r"\s+", "", a.lower())[:120]
    return hashlib.sha1(f"{qn}|{an}".encode("utf-8")).hexdigest()[:16]


def row_to_candidates(row: dict) -> list[dict]:
    inp = row.get("input_refined") or row.get("input") or ""
    out = row.get("output_refined") or row.get("output") or ""
    if not inp.strip() or not out.strip():
        return []
    if not Q_HINT.search(inp):
        return []
    if not A_HINT.search(out) and not extract_price_facts(out):
        # 无标准信息信号则跳过
        return []

    q = clean_question(last_question_chunk(inp))
    a = clean_answer(out)
    if not q or not a or len(a) < 4:
        return []
    if is_bad_question(q) or is_bad_answer(a):
        return []

    # 过滤过空确认
    if re.fullmatch(r"(好的?|嗯+|哦+|在|ok|OK|收到)+", a):
        return []

    topic = detect_topic(q, a)
    facts = extract_price_facts(a)
    conf = 0.55
    if facts:
        conf += 0.15
    if (row.get("balanced_category") or row.get("category")) == "business":
        conf += 0.1
    if TOPIC_PROCESS.search(q) and TOPIC_PROCESS.search(a):
        conf += 0.12
        topic = "process" if topic == "general" else topic
    if TOPIC_OPS.search(q) and TOPIC_OPS.search(a) and not facts:
        topic = "ops"
        conf += 0.08

    heavy = is_heavy_template(a)
    if heavy:
        # 重模板：只保留抽取出的价目事实，改写成干净标准答
        if not facts:
            return []
        items = []
        for f in facts[:6]:
            qq = f"{f['package']}多少钱？"
            aa = f"{f['package']} {f['price']}{f['unit']}（以当时核实为准）。"
            items.append(
                {
                    "q": qq,
                    "a": aa,
                    "topic": "price",
                    "price_facts": [f],
                    "dialog_id": row.get("dialog_id"),
                    "year_month": row.get("year_month"),
                    "peer_id": row.get("peer_id"),
                    "confidence": 0.88,
                    "source": "template_price_fact",
                    "refine_instruction": "2.1",
                }
            )
        # 另抽一条「怎么开」标准操作（短）
        if "用户名" in a or "提供" in a:
            items.append(
                {
                    "q": "飞机会员怎么开通？",
                    "a": "提供飞机用户名，选好月份套餐，按约定渠道付款后截图确认即可开通。",
                    "topic": "process",
                    "price_facts": [],
                    "dialog_id": row.get("dialog_id"),
                    "year_month": row.get("year_month"),
                    "peer_id": row.get("peer_id"),
                    "confidence": 0.86,
                    "source": "template_process_norm",
                    "refine_instruction": "2.1",
                }
            )
        return items

    conf = min(0.95, conf)
    # 价目题才压缩成长答；流程/操作题保留短专业答
    if len(a) > 120 and facts and topic == "price":
        a = "；".join(f"{f['package']}{f['price']}{f['unit']}" for f in facts[:4])
        a = f"价格参考：{a}。以下单核实为准。"
    elif len(a) > 160 and topic in ("process", "ops"):
        # 取前两句可执行信息
        parts = re.split(r"[。！？\n]", a)
        parts = [p.strip() for p in parts if p.strip() and not TEMPLATE_NOISE.search(p)]
        a = "。".join(parts[:2])
        if a and not a.endswith("。"):
            a += "。"

    item = {
        "q": q,
        "a": a if len(a) <= 200 else a[:199] + "…",
        "topic": topic,
        "price_facts": facts,
        "dialog_id": row.get("dialog_id"),
        "year_month": row.get("year_month"),
        "peer_id": row.get("peer_id"),
        "confidence": round(conf, 3),
        "source": "dialog",
        "refine_instruction": "2.1",
    }
    return [item]

def synthesize_from_facts(fact_counter: Counter) -> list[dict]:
    """高频价目事实合成标准 Q/A（跨对话聚合统计，不串单人隐私）。"""
    items = []
    for (pkg, price, unit), cnt in fact_counter.most_common(40):
        if cnt < 3:
            continue
        q = f"{pkg}会员多少钱？" if "月" in pkg or "年" in pkg else f"{pkg}什么价格？"
        a = f"{pkg}标准价 {price}{unit}。以下单/报价时核实为准。"
        items.append(
            {
                "q": q,
                "a": a,
                "topic": "price",
                "price_facts": [{"package": pkg, "price": price, "unit": unit}],
                "dialog_id": None,
                "year_month": None,
                "peer_id": None,
                "confidence": round(min(0.9, 0.5 + 0.02 * cnt), 3),
                "source": "aggregated_price_fact",
                "support_count": cnt,
                "refine_instruction": "2.1",
            }
        )
    return items


def to_markdown(items: list[dict]) -> str:
    by_topic: dict[str, list] = defaultdict(list)
    for it in items:
        by_topic[it.get("topic") or "general"].append(it)
    order = ["price", "package", "process", "ops", "general"]
    lines = [
        "# 标准问答知识库（指令 2.1）",
        "",
        "从清洗对话提取的价格 / 套餐 / 流程 / 操作标准问答。答案可追溯 dialog；聚合价目来自高频统计。",
        "",
    ]
    titles = {
        "price": "价格",
        "package": "服务包 / 套餐",
        "process": "业务流程",
        "ops": "标准操作",
        "general": "其他",
    }
    for topic in order:
        bucket = by_topic.get(topic) or []
        if not bucket:
            continue
        lines.append(f"## {titles.get(topic, topic)}")
        lines.append("")
        for i, it in enumerate(bucket, 1):
            lines.append(f"### Q{i}. {it['q']}")
            lines.append("")
            lines.append(f"**A:** {it['a']}")
            lines.append("")
            meta = []
            if it.get("confidence") is not None:
                meta.append(f"confidence={it['confidence']}")
            if it.get("dialog_id"):
                meta.append(f"dialog=`{it['dialog_id']}`")
            if it.get("support_count"):
                meta.append(f"support={it['support_count']}")
            if meta:
                lines.append(f"- " + " · ".join(meta))
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Module2 Instruction2.1 standard QA extract")
    ap.add_argument("--input", type=Path, default=SKILL / "train_data_final" / "train.jsonl")
    ap.add_argument(
        "--refined",
        type=Path,
        default=SKILL / "train_data_refined" / "module1_1" / "train_refined_1_1.jsonl",
    )
    ap.add_argument("--output-dir", type=Path, default=SKILL / "train_data_refined" / "module2_1")
    ap.add_argument("--knowledge-dir", type=Path, default=SKILL / "knowledge" / "qa")
    ap.add_argument("--max-rows", type=int, default=0)
    ap.add_argument("--min-confidence", type=float, default=0.55)
    ap.add_argument("--max-qa", type=int, default=800)
    args = ap.parse_args()

    # 优先用 1.1 精炼集（有 raw 可回溯）
    src = args.refined if args.refined.exists() else args.input
    rows = load_jsonl(src if src.is_absolute() else SKILL / src)
    if args.max_rows:
        rows = rows[: args.max_rows]

    candidates: list[dict] = []
    fact_counter: Counter = Counter()
    for row in rows:
        if row.get("from_knowledge"):
            continue
        for c in row_to_candidates(row):
            candidates.append(c)
            for f in c.get("price_facts") or []:
                fact_counter[(f["package"], f["price"], f["unit"])] += 1

    # 去重：同 q 保留更干净来源
    source_rank = {
        "aggregated_price_fact": 3,
        "template_price_fact": 2,
        "template_process_norm": 2,
        "dialog": 1,
    }
    best: dict[str, dict] = {}
    for c in candidates:
        if c["confidence"] < args.min_confidence:
            continue
        if is_bad_question(c["q"]) or is_bad_answer(c["a"]):
            continue
        qk = re.sub(r"\s+", "", c["q"].lower())
        prev = best.get(qk)
        if not prev:
            best[qk] = c
            continue
        pr = source_rank.get(prev.get("source"), 0)
        cr = source_rank.get(c.get("source"), 0)
        if cr > pr or (
            cr == pr
            and (
                c["confidence"] > prev["confidence"]
                or (c["confidence"] == prev["confidence"] and len(c["a"]) < len(prev["a"]))
            )
        ):
            best[qk] = c

    items = list(best.values())
    # 话题配额：严格按配额取样，避免 ops 淹没价目/流程
    quotas = {"price": 250, "package": 80, "process": 200, "ops": 150, "general": 0}
    bucket: dict[str, list] = defaultdict(list)
    for it in items:
        bucket[it["topic"]].append(it)
    for t in bucket:
        bucket[t].sort(
            key=lambda x: (
                -{"aggregated_price_fact": 3, "template_price_fact": 2, "template_process_norm": 2, "dialog": 1}.get(
                    x.get("source"), 0
                ),
                -x["confidence"],
                len(x["a"]),
            )
        )
    selected: list[dict] = []
    for t, lim in quotas.items():
        selected.extend(bucket.get(t, [])[:lim])
    # 合成高频价目置顶
    synth = synthesize_from_facts(fact_counter)
    existing_q = {re.sub(r"\s+", "", x["q"].lower()) for x in selected}
    for s in synth:
        qk = re.sub(r"\s+", "", s["q"].lower())
        if qk not in existing_q:
            selected.insert(0, s)
            existing_q.add(qk)
    # 不够再补高置信 dialog
    if len(selected) < args.max_qa:
        used = {id(x) for x in selected}
        rest = [x for x in items if id(x) not in used]
        rest.sort(key=lambda x: (-x["confidence"], x["topic"]))
        selected.extend(rest[: max(0, args.max_qa - len(selected))])
    items = selected[: args.max_qa]
    items.sort(key=lambda x: (x["topic"], -x["confidence"], x["q"]))
    for it in items:
        it["id"] = qa_key(it["q"], it["a"])

    out_dir = args.output_dir if args.output_dir.is_absolute() else SKILL / args.output_dir
    know_dir = args.knowledge_dir if args.knowledge_dir.is_absolute() else SKILL / args.knowledge_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    know_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = know_dir / "standard_qa.jsonl"
    md_path = know_dir / "standard_qa.md"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    md_path.write_text(to_markdown(items), encoding="utf-8")

    # 同步一份到 module2_1
    (out_dir / "standard_qa.jsonl").write_text(jsonl_path.read_text(encoding="utf-8"), encoding="utf-8")
    (out_dir / "standard_qa.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

    topic_counts = Counter(it["topic"] for it in items)
    report = {
        "instruction": "2.1",
        "module": "knowledge_base",
        "source": str(src),
        "candidates": len(candidates),
        "qa_out": len(items),
        "topic_counts": dict(topic_counts),
        "top_price_facts": [
            {"package": k[0], "price": k[1], "unit": k[2], "count": v}
            for k, v in fact_counter.most_common(15)
        ],
        "knowledge_jsonl": str(jsonl_path),
        "knowledge_md": str(md_path),
        "examples": [
            {"q": it["q"], "a": it["a"][:160], "topic": it["topic"], "confidence": it["confidence"]}
            for it in items[:5]
        ],
        "principles": "references/training_module_02_knowledge.md",
    }
    (out_dir / "report_2_1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (know_dir / "README.md").write_text(
        "\n".join(
            [
                "# 标准问答知识库",
                "",
                "由指令 **2.1** 从清洗对话提取。",
                "",
                "- `standard_qa.jsonl` — 机器可读",
                "- `standard_qa.md` — 人读",
                "",
                "规范：`references/training_module_02_knowledge.md`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
