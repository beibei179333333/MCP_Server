#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""训练模块三 · 指令 3.1：多轮对话逻辑构建（连贯性示范 + 逻辑链分析）。

从 2.2 高转化多轮上下文出发，标记「示范样本」，并为每一拍回复标注：
- 上下文记忆槽（意图/套餐/报价/用户名/付款/成交）
- 衔接类型（承接 / 推进 / 回顾 / 收口）
- 如何避免跳跃与重复

硬约束：单 peer / 单 context 隔离；原文不润色。

示例：
  python3 build_multiturn_logic_3_1.py
  python3 build_multiturn_logic_3_1.py --limit 120
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

SKILL = Path(__file__).resolve().parent

ASK = re.compile(
    r"(多少钱|什么价|怎么开|开会员|帮我开|给我开|代开|几个月|报价|开通|弄个)",
    re.I,
)
FOLLOW = re.compile(
    r"(怎么付|怎么转|转哪|用户名|汇旺|U钱包|截图|然后|还要什么|发用户名)",
    re.I,
)
BARGAIN = re.compile(r"(便宜|少点|优惠|再便宜|打折|最低|贵了|便宜点)", re.I)
QUOTE = re.compile(
    r"(秒开|回购|\d+\s*个月|\d+\s*[uUＵ]|汇旺|只要\s*\d+|需要提供|用户名即可)",
    re.I,
)
AGREE = re.compile(
    r"(就这个|开3|开6|开12|开一年|开三个月|开六个月|要3|要6|要12|行吧|那就开|开吧|定了|两个半年)",
    re.I,
)
PAY = re.compile(r"(转好了|转了|付款了|付了|已经转|截图|到账|U转)", re.I)
DEAL = re.compile(r"(开好了|开通好了|已经开通|都开好了|弄好了|搞定了)", re.I)
USERNAME = re.compile(r"^@?[A-Za-z][A-Za-z0-9_]{3,32}$")
GREET = re.compile(r"^(老铁|在吗|在不|你好|哈喽|hi|hello|上班没|我在|好)$", re.I)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def text_sig(s: str) -> str:
    """用于重复检测的粗指纹（去空白、截断）。"""
    t = re.sub(r"\s+", "", s)
    t = re.sub(r"[—\-_=]{3,}", "", t)
    return t[:80]


def update_memory(mem: dict[str, Any], role: str, text: str, labels: list[str]) -> list[str]:
    """根据本轮更新记忆槽，返回本轮写入的槽位名。"""
    wrote: list[str] = []
    t = text.strip()

    def set_slot(k: str, v: Any) -> None:
        if mem.get(k) != v:
            mem[k] = v
            wrote.append(k)

    if role == "peer":
        if GREET.search(t) or len(t) <= 4:
            set_slot("rapport", True)
        if ASK.search(t) or "提问" in labels:
            set_slot("intent", "开通/询价")
        if FOLLOW.search(t) or "追问" in labels:
            set_slot("open_question", norm(t)[:40])
        if BARGAIN.search(t) or "议价" in labels:
            set_slot("bargain", True)
        if AGREE.search(t) or "同意" in labels:
            set_slot("package_choice", norm(t)[:40])
            set_slot("decision", "同意下单")
        if PAY.search(t) or "付款" in labels:
            set_slot("payment", "客户已表态付款/截图")
        if USERNAME.match(t) or (t.startswith("@") and len(t) <= 40):
            set_slot("username", t)
        # 数量/套餐口语
        m = re.search(r"(两个|三个|\d+)\s*(半年|三个月|六个月|12个月|一年)", t)
        if m:
            set_slot("package_choice", m.group(0))
    else:
        if QUOTE.search(t) or "报价" in labels:
            set_slot("quoted", True)
            pm = re.search(r"(\d+\s*个月.{0,8}\d+\s*[uUＵ]?)", t, re.I)
            if pm:
                set_slot("last_quote_hint", pm.group(1))
            # 报价即回应追问/询价，清空未决追问避免链路上「假回顾」
            if mem.get("open_question"):
                mem.pop("open_question", None)
                wrote.append("open_question:cleared")
        if DEAL.search(t) or "成交" in labels:
            set_slot("deal", True)
            set_slot("status", "已开通")
            mem.pop("open_question", None)
        if re.match(r"^(好|好的|是|在|嗯+|OK)$", t, re.I):
            set_slot("acked", True)
        # 短答复也视为回应了上一追问
        if mem.get("open_question") and 2 <= len(t) <= 60 and not QUOTE.search(t):
            mem.pop("open_question", None)
            wrote.append("open_question:cleared")

    return wrote


def classify_link(
    role: str,
    text: str,
    labels: list[str],
    mem_before: dict[str, Any],
    wrote: list[str],
    prev_role: str | None,
    prev_text: str | None,
    seen_sigs: list[str],
) -> dict[str, Any]:
    """为当前轮生成衔接分析。"""
    link_type = "铺垫"
    advance = ""
    recall = []
    avoids = []

    sig = text_sig(text)
    is_repeat = False
    if role == "self" and len(sig) > 30:
        for old in seen_sigs:
            if old and sig == old:
                is_repeat = True
                break
            # 价目模板重复：高度重合
            if old and len(old) > 40 and sig[:40] == old[:40] and QUOTE.search(text):
                is_repeat = True
                break

    if role == "peer":
        if ASK.search(text):
            link_type = "提出需求"
            advance = "客户抛出业务意图，后续应承接而非跳主题。"
        elif FOLLOW.search(text):
            link_type = "追问澄清"
            advance = "客户就上一步信息追问，回复须直接回答该点。"
            if mem_before.get("quoted"):
                recall.append("已报价，客户在确认操作细节")
        elif BARGAIN.search(text):
            link_type = "议价试探"
            advance = "在已报价基础上压价，应回顾原价再给让步/拒绝理由。"
            if mem_before.get("last_quote_hint"):
                recall.append(f"回顾报价线索：{mem_before['last_quote_hint']}")
        elif AGREE.search(text) or USERNAME.match(text.strip()):
            link_type = "决策推进"
            advance = "客户给出选择或用户名，进入履约。"
            if mem_before.get("intent"):
                recall.append(f"意图仍是：{mem_before['intent']}")
        elif PAY.search(text):
            link_type = "付款确认"
            advance = "付款信号出现，下一步应对账/开通，勿再重复整份价目。"
        else:
            link_type = "关系铺垫"
            advance = "寒暄或补充信息，保持同主题。"
    else:
        # 我方：核心示范对象
        if DEAL.search(text) or "成交" in labels:
            link_type = "收口成交"
            advance = "兑现已确认的套餐/用户名，闭环。"
            for k in ("package_choice", "username", "payment"):
                if mem_before.get(k):
                    recall.append(f"{k}={mem_before[k]}")
            avoids.append("跳跃：未确认用户名/套餐就报「开好了」")
            avoids.append("重复：成交后再贴一遍完整价目广告")
        elif QUOTE.search(text) or "报价" in labels:
            link_type = "推进报价"
            if mem_before.get("intent"):
                recall.append(f"回应对方意图：{mem_before['intent']}")
                advance = "在确认需求后给出价目/流程，完成「问→答」衔接。"
            else:
                advance = "主动报价；更优示范是先确认意图再报价。"
            avoids.append("跳跃：对方还在寒暄就甩长模板（可接受但非最优）")
            avoids.append("重复：短时间内再次粘贴同一价目墙")
        elif re.match(r"^(好|好的|是|在|嗯+|OK|1)$", text.strip(), re.I):
            link_type = "承接确认"
            advance = "短承接，把话轮交回客户，符合留白原则。"
            if prev_text:
                recall.append(f"承接上一句：{norm(prev_text)[:30]}")
            avoids.append("跳跃：忽略客户问题直接换话题")
            avoids.append("重复：连续堆确认词不给信息")
        elif mem_before.get("open_question") and len(text) < 40:
            link_type = "回答追问"
            advance = "针对客户未决问题作答。"
            recall.append(f"回顾追问：{mem_before['open_question']}")
            avoids.append("跳跃：答非所问")
        else:
            link_type = "推进下一步"
            advance = "根据当前记忆推进流程（要数量/要用户名/给地址等）。"
            if mem_before.get("package_choice"):
                recall.append(f"已选：{mem_before['package_choice']}")
            if mem_before.get("username"):
                recall.append(f"用户名：{mem_before['username']}")
            avoids.append("跳跃：跳过已问信息重复再问")
            avoids.append("重复：无视客户新信息仍复读旧话术")

    if is_repeat:
        link_type = "⚠重复风险"
        avoids.insert(0, "本轮与先前我方长回复高度相似，示范库中作反面对照或降权")

    # 连贯性评分启发
    coherence = 0.55
    if role == "self":
        coherence = 0.7
        if recall:
            coherence += 0.1
        if link_type in {"承接确认", "回答追问", "收口成交", "推进报价"}:
            coherence += 0.1
        if is_repeat:
            coherence -= 0.35
        if link_type == "推进报价" and not mem_before.get("intent") and not mem_before.get("rapport"):
            coherence -= 0.1
        # 收口时有用户名/套餐记忆加分
        if link_type == "收口成交" and (mem_before.get("username") or mem_before.get("package_choice")):
            coherence += 0.1
    else:
        coherence = 0.75

    coherence = max(0.15, min(0.98, coherence))

    return {
        "link_type": link_type,
        "advance": advance,
        "recall": recall,
        "avoids": avoids[:3],
        "memory_writes": wrote,
        "coherence": round(coherence, 2),
        "is_repeat_risk": is_repeat,
    }


def analyze_context(ctx: dict) -> dict | None:
    turns = ctx.get("turns") or []
    if len(turns) < 6 or len(turns) > 45:
        return None

    mem: dict[str, Any] = {}
    chain: list[dict] = []
    seen_self_sigs: list[str] = []
    prev_role = None
    prev_text = None
    self_links = 0
    good_links = 0

    for i, t in enumerate(turns):
        role = t["role"]
        text = t.get("text") or ""
        labels = list(t.get("stage_labels") or [])
        mem_before = dict(mem)
        wrote = update_memory(mem, role, text, labels)
        link = classify_link(
            role,
            text,
            labels,
            mem_before,
            wrote,
            prev_role,
            prev_text,
            seen_self_sigs,
        )
        if role == "self":
            self_links += 1
            if link["coherence"] >= 0.65 and not link["is_repeat_risk"]:
                good_links += 1
            if len(text_sig(text)) > 30:
                seen_self_sigs.append(text_sig(text))

        chain.append(
            {
                "turn_idx": i + 1,
                "role": role,
                "text": text,
                "date": t.get("date"),
                "stage_labels": labels,
                "memory_before": {k: mem_before[k] for k in mem_before},
                "memory_after": {k: mem[k] for k in mem},
                "logic": link,
            }
        )
        prev_role = role
        prev_text = text

    # 整段示范资格：至少若干高质量我方衔接 + 有意图与收口/决策
    if self_links < 2:
        return None
    ratio = good_links / max(1, self_links)
    stages = set(ctx.get("stages") or [])
    has_arc = bool(stages & {"ask", "followup"}) and bool(
        stages & {"deal", "agree", "pay", "decision"}
    )
    if not has_arc and ratio < 0.5:
        return None

    demo_score = (
        (ctx.get("score") or 0) * 0.5
        + ratio * 40
        + min(15, len(turns))
        + (8 if "deal" in stages else 0)
        + (5 if "bargain" in stages else 0)
        - sum(3 for c in chain if c["logic"].get("is_repeat_risk"))
    )

    # 逻辑链摘要（自然语言）
    summary_steps = []
    for c in chain:
        if c["role"] != "self":
            continue
        lg = c["logic"]
        bit = f"T{c['turn_idx']}〔{lg['link_type']}〕"
        if lg["recall"]:
            bit += " 回顾:" + "/".join(lg["recall"][:2])
        bit += " → " + (lg["advance"][:36] if lg["advance"] else "")
        summary_steps.append(bit)

    sample_id = hashlib.sha1(
        f"{ctx.get('peer_id')}:{ctx.get('id')}:3.1".encode()
    ).hexdigest()[:12]

    return {
        "id": sample_id,
        "sample_type": "示范样本",
        "instruction": "3.1",
        "module": "multiturn_logic",
        "source_context_id": ctx.get("id"),
        "peer_id": ctx.get("peer_id"),
        "dialog_id": ctx.get("dialog_id"),
        "year_month": ctx.get("year_month"),
        "tier": ctx.get("tier"),
        "source_score": ctx.get("score"),
        "demo_score": round(demo_score, 2),
        "n_turns": len(turns),
        "stages": ctx.get("stages"),
        "final_memory": mem,
        "coherence_ratio": round(ratio, 3),
        "logic_chain_summary": summary_steps,
        "chain": chain,
        # 训练友好视图：历史→下一句（仅高质量我方轮）
        "training_pairs": build_training_pairs(chain),
    }


def build_training_pairs(chain: list[dict], max_pairs: int = 6) -> list[dict]:
    """构造「上文 → 示范回复」对，附逻辑说明。"""
    pairs = []
    for i, c in enumerate(chain):
        if c["role"] != "self":
            continue
        lg = c["logic"]
        if lg.get("is_repeat_risk") or lg["coherence"] < 0.6:
            continue
        history = []
        for h in chain[:i]:
            who = "客户" if h["role"] == "peer" else "我方"
            history.append(f"{who}: {norm(h['text'])[:120]}")
        pairs.append(
            {
                "history": history[-8:],
                "demo_reply": c["text"],
                "link_type": lg["link_type"],
                "recall": lg["recall"],
                "advance": lg["advance"],
                "avoids": lg["avoids"],
                "memory": c["memory_before"],
                "coherence": lg["coherence"],
            }
        )
        if len(pairs) >= max_pairs:
            break
    # 丢掉无客户历史的弱对
    return [p for p in pairs if any(h.startswith("客户:") for h in p["history"])]


def to_markdown(samples: list[dict]) -> str:
    lines = [
        "# 多轮对话逻辑示范（指令 3.1）",
        "",
        "样本类型均为 **示范样本**。每段展示：完整多轮流程 + 逻辑链（推进/回顾）+ 反跳跃/反重复要点。",
        "",
    ]
    for i, s in enumerate(samples, 1):
        lines.append(
            f"## Demo_{i:03d} · peer=`{s['peer_id']}` · score={s['demo_score']} · {s.get('year_month')}"
        )
        lines.append("")
        lines.append(f"- sample_type: **{s['sample_type']}**")
        lines.append(f"- stages: {', '.join(s.get('stages') or [])}")
        lines.append(f"- coherence_ratio: {s['coherence_ratio']}")
        lines.append(f"- final_memory: `{json.dumps(s.get('final_memory') or {}, ensure_ascii=False)}`")
        lines.append("")
        lines.append("### 逻辑链摘要")
        for step in s.get("logic_chain_summary") or []:
            lines.append(f"- {step}")
        lines.append("")
        lines.append("### 逐轮标注")
        for c in s["chain"]:
            who = "客户" if c["role"] == "peer" else "我方"
            lg = c["logic"]
            text = norm(c["text"])
            if len(text) > 100:
                text = text[:100] + "…"
            lines.append(
                f"- **T{c['turn_idx']} {who}** 〔{lg['link_type']}〕 coh={lg['coherence']}: {text}"
            )
            if lg.get("recall"):
                lines.append(f"  - 回顾: {'; '.join(lg['recall'])}")
            if lg.get("advance"):
                lines.append(f"  - 推进: {lg['advance']}")
            if lg.get("avoids") and c["role"] == "self":
                lines.append(f"  - 避免: {'; '.join(lg['avoids'])}")
        lines.append("")
        if s.get("training_pairs"):
            lines.append("### 训练切片示例（上文→示范回复）")
            p0 = s["training_pairs"][0]
            lines.append("```")
            lines.append("【历史】")
            lines.extend(p0["history"])
            lines.append("【示范回复】")
            lines.append(norm(p0["demo_reply"])[:200])
            lines.append(f"【衔接】{p0['link_type']} | {p0['advance'][:60]}")
            lines.append("```")
            lines.append("")
    return "\n".join(lines)


def to_alpaca_rows(samples: list[dict]) -> list[dict]:
    """导出可供微调的多轮连贯示范行。"""
    rows = []
    for s in samples:
        for p in s.get("training_pairs") or []:
            mem = p.get("memory") or {}
            mem_txt = "；".join(f"{k}={v}" for k, v in mem.items()) if mem else "（空）"
            instruction = (
                "根据以下多轮对话历史回复对方。保持逻辑连贯：先承接上下文，"
                "再推进下一步；回顾已确认信息，避免跳跃换题或重复粘贴相同话术。"
            )
            inp = "对话历史：\n" + "\n".join(p["history"])
            inp += f"\n\n当前记忆槽：{mem_txt}"
            inp += f"\n衔接目标：{p['link_type']}"
            if p.get("recall"):
                inp += "\n需回顾：" + "；".join(p["recall"])
            rows.append(
                {
                    "instruction": instruction,
                    "input": inp,
                    "output": p["demo_reply"],
                    "sample_type": "示范样本",
                    "dialog_id": s.get("dialog_id"),
                    "peer_id": s.get("peer_id"),
                    "logic_meta": {
                        "link_type": p["link_type"],
                        "advance": p["advance"],
                        "avoids": p["avoids"],
                        "coherence": p["coherence"],
                        "demo_id": s["id"],
                    },
                    "sample_weight": 1.5,
                    "from_module": "3.1",
                }
            )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="指令 3.1 多轮对话逻辑示范构建")
    ap.add_argument(
        "--contexts",
        type=Path,
        default=SKILL / "knowledge" / "success_contexts" / "success_contexts.jsonl",
    )
    ap.add_argument("--limit", type=int, default=150, help="示范样本上限")
    ap.add_argument(
        "--knowledge-dir",
        type=Path,
        default=SKILL / "knowledge" / "multiturn_logic",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=SKILL / "train_data_refined" / "module3_1",
    )
    args = ap.parse_args()

    contexts = []
    with args.contexts.open(encoding="utf-8") as f:
        for line in f:
            contexts.append(json.loads(line))

    samples = []
    for ctx in contexts:
        s = analyze_context(ctx)
        if s:
            samples.append(s)
    samples.sort(key=lambda x: (-x["demo_score"], -x["coherence_ratio"], x["peer_id"]))
    # peer 去重：每 peer 最多 2 条
    selected: list[dict] = []
    per_peer: Counter[str] = Counter()
    for s in samples:
        if per_peer[s["peer_id"]] >= 2:
            continue
        selected.append(s)
        per_peer[s["peer_id"]] += 1
        if len(selected) >= args.limit:
            break

    know = args.knowledge_dir if args.knowledge_dir.is_absolute() else SKILL / args.knowledge_dir
    out = args.output_dir if args.output_dir.is_absolute() else SKILL / args.output_dir
    know.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    jsonl_path = know / "demo_samples.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for s in selected:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    md_path = know / "demo_samples.md"
    md_path.write_text(to_markdown(selected), encoding="utf-8")

    # 精简人读版：只放摘要 + 链，不带全文 memory（md 已有逐轮）
    summary = []
    for s in selected:
        summary.append(
            {
                "id": s["id"],
                "sample_type": s["sample_type"],
                "peer_id": s["peer_id"],
                "demo_score": s["demo_score"],
                "coherence_ratio": s["coherence_ratio"],
                "logic_chain_summary": s["logic_chain_summary"],
                "final_memory": s["final_memory"],
                "n_training_pairs": len(s.get("training_pairs") or []),
            }
        )
    (know / "demo_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 训练对：跳过「空历史 + 纯寒暄」弱样本
    alpaca = [r for r in to_alpaca_rows(selected) if r.get("input") and "客户:" in r["input"]]
    # 若过滤过狠则回退
    if len(alpaca) < 50:
        alpaca = to_alpaca_rows(selected)
    train_path = out / "train_logic_demo.jsonl"
    with train_path.open("w", encoding="utf-8") as f:
        for row in alpaca:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    (out / "demo_samples.jsonl").write_text(jsonl_path.read_text(encoding="utf-8"), encoding="utf-8")
    (out / "demo_samples.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

    report = {
        "instruction": "3.1",
        "module": "multiturn_logic",
        "contexts_in": len(contexts),
        "candidates": len(samples),
        "selected_demos": len(selected),
        "training_pairs": len(alpaca),
        "avg_coherence_ratio": round(
            sum(s["coherence_ratio"] for s in selected) / max(1, len(selected)), 3
        ),
        "link_type_counts": dict(
            Counter(
                c["logic"]["link_type"]
                for s in selected
                for c in s["chain"]
                if c["role"] == "self"
            )
        ),
        "paths": {
            "demo_jsonl": str(jsonl_path),
            "demo_md": str(md_path),
            "train_jsonl": str(train_path),
            "module_dir": str(out),
        },
        "examples": [
            {
                "id": s["id"],
                "peer_id": s["peer_id"],
                "demo_score": s["demo_score"],
                "summary": s["logic_chain_summary"][:5],
                "final_memory": s["final_memory"],
            }
            for s in selected[:5]
        ],
    }
    (out / "report_3_1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / "last_run.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
