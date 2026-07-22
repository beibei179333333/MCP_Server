#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模块二延伸：按标准处理文档模板，为成功上下文生成完整处理卷宗。

模板结构：
  元数据 → 原始对话 → 清洗提炼（1.1 精炼 + 2.1 Q/A + 2.2 高价值上下文）→ 分析备注

硬约束：
- 单 peer / 单 context 隔离，禁止串台
- Raw Transcript 保持原文不润色
- Refined Dialogue 仅在「清洗输出」区做短句合并（15–30 字目标）

示例：
  python3 generate_processing_docs.py
  python3 generate_processing_docs.py --limit 50
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from refine_conversation_1_1 import char_len, merge_to_target, split_utterances
from refine_conversation_1_2 import compress_texts

SKILL = Path(__file__).resolve().parent
RAW_DEFAULT = Path("/Users/home/Downloads/tg_private_4y_monthly/00_raw_origin")
SELF_USER_ID = "1335016610"

_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\ufeff\u00a0]")
ASK = re.compile(
    r"(多少钱|什么价|怎么开|怎么弄|开会员|几个月|报价|帮我开|给我开|开通|怎么付|怎么转)",
    re.I,
)
ANSWERISH = re.compile(
    r"(秒开|回购|\d+\s*[uU]|汇旺|用户名|开通|流程|只要|需要提供)",
    re.I,
)
BARGAIN = re.compile(r"(便宜|少点|优惠|再便宜|打折|最低|贵了|便宜点)", re.I)
DEAL = re.compile(r"(开好了|开通好了|已经开通|弄好了|搞定了)", re.I)


def extract_text(text: Any) -> str:
    if text is None:
        return ""
    if isinstance(text, str):
        return _INVISIBLE.sub("", text).strip()
    if isinstance(text, list):
        parts = []
        for x in text:
            if isinstance(x, str):
                parts.append(x)
            elif isinstance(x, dict):
                parts.append(str(x.get("text") or ""))
        return _INVISIBLE.sub("", "".join(parts)).strip()
    return _INVISIBLE.sub("", str(text)).strip()


def from_id_of(m: dict) -> str:
    fid = m.get("from_id")
    if fid is None:
        return ""
    s = str(fid)
    return s.replace("user", "") if s.startswith("user") else s


def load_raw_chat(peer_id: str, raw_dir: Path) -> dict | None:
    path = raw_dir / f"chat_{peer_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def infer_comm_type(stages: list[str], texts: str) -> str:
    # 优先用 2.2 阶段标签；售后/合作用强特征，避免广告词误伤
    if re.search(r"(售后找|申请退|投诉|没开通|没开上|没到账|重开一下|掉会员)", texts):
        return "售后支持"
    if re.search(r"(合作|代理加盟|加盟|渠道商|分销)", texts):
        return "业务合作"
    if "bargain" in stages and ("deal" in stages or "pay" in stages or "agree" in stages):
        return "销售咨询（含议价成交）"
    return "销售咨询"


def analysis_notes(ctx: dict, turns: list[dict], refined: list[dict]) -> dict:
    stages = set(ctx.get("stages") or [])
    findings = []
    if "bargain" in stages:
        findings.append("客户对价格有试探/议价行为，需保留议价收口话术。")
    if "followup" in stages:
        findings.append("存在追问（付款方式/用户名/流程），体现留白后的下一步推进。")
    if "deal" in stages:
        findings.append("出现明确成交确认，可作高转化示范。")
    if "pay" in stages:
        findings.append("对话中出现付款/截图相关信号。")
    if "agree" in stages and "deal" not in stages:
        findings.append("客户已给出同意/下单意向，属关键决策点。")
    if not findings:
        findings.append("标准询价→报价→决策链条，可作为常规销售节奏参考。")

    score = ctx.get("score") or 0
    tier = ctx.get("tier") or ""
    if tier == "tier1" or score >= 45:
        conv = "高：含成交确认，链条完整，建议纳入话术示范库。"
    elif tier == "tier2" or score >= 30:
        conv = "中高：达关键决策点（付款/同意/提交用户名），接近成交。"
    else:
        conv = "中：有询价与报价互动，收口偏软，可作过程样本。"

    edits = []
    raw_self = sum(1 for t in turns if t["role"] == "self")
    ref_self = sum(1 for t in refined if t["role"] == "self")
    if ref_self < raw_self:
        edits.append(f"我方连续碎句已合并：原始约 {raw_self} 条 → 精炼 {ref_self} 条。")
    long_tpl = sum(1 for t in turns if t["role"] == "self" and char_len(t["text"]) > 80)
    if long_tpl:
        edits.append("精炼区对超长价目模板按行截断展示，未改写 Raw Transcript 原文。")
    short_keep = sum(1 for t in refined if char_len(t["text"]) < 15)
    if short_keep:
        edits.append(f"保留 {short_keep} 条超短确认语（如「好」「在」），避免过度合并失真。")
    if not edits:
        edits.append("本段精炼以同说话人合并为主，语气未做大幅改写。")

    return {
        "findings": findings,
        "conversion": conv,
        "edits": edits,
    }


def refine_dialogue(turns: list[dict]) -> list[dict]:
    """同说话人连续短句合并，再按 1.1 压到约 15–30 字。"""
    if not turns:
        return []
    bursts: list[dict] = []
    buf_role = turns[0]["role"]
    buf_texts = [turns[0]["text"]]
    buf_date = turns[0].get("date")
    for t in turns[1:]:
        if t["role"] == buf_role:
            buf_texts.append(t["text"])
        else:
            bursts.append({"role": buf_role, "text": compress_texts(buf_texts), "date": buf_date})
            buf_role = t["role"]
            buf_texts = [t["text"]]
            buf_date = t.get("date")
    bursts.append({"role": buf_role, "text": compress_texts(buf_texts), "date": buf_date})

    refined: list[dict] = []
    for b in bursts:
        utts = split_utterances(b["text"])
        merged = merge_to_target(utts, min_len=15, max_len=30)
        if not merged:
            t = b["text"].strip()
            if t:
                refined.append({"role": b["role"], "text": t, "date": b.get("date")})
            continue
        for m in merged:
            refined.append({"role": b["role"], "text": m, "date": b.get("date")})
    return refined


def extract_local_qa(turns: list[dict], limit: int = 3) -> list[dict]:
    """从本段上下文抽 Q/A（单 context 内，不跨 peer）。"""
    pairs: list[dict] = []
    for i, t in enumerate(turns):
        if t["role"] != "peer":
            continue
        q = t["text"].strip()
        if not ASK.search(q) or len(q) < 4 or len(q) > 80:
            continue
        ans = None
        for j in range(i + 1, min(len(turns), i + 8)):
            if turns[j]["role"] != "self":
                continue
            a = turns[j]["text"].strip()
            if ANSWERISH.search(a) and len(a) >= 4:
                ans = a
                break
        if not ans:
            continue
        a_show = ans
        truncated = False
        if char_len(ans) > 120:
            lines = [ln.strip() for ln in ans.splitlines() if ln.strip()]
            keep = []
            for ln in lines:
                keep.append(ln)
                if ANSWERISH.search(ln) and char_len(" ".join(keep)) >= 40:
                    break
                if len(keep) >= 4:
                    break
            a_show = "\n".join(keep)
            truncated = True
        pairs.append({"q": q, "a": a_show, "a_truncated": truncated})
        if len(pairs) >= limit:
            break
    return pairs


def match_global_qa(local_qs: list[str], qa_items: list[dict], limit: int = 2) -> list[dict]:
    """用问题关键词弱匹配全局 2.1 标准答（仅作补充，标明来源）。"""
    out = []
    for q in local_qs:
        keys = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}", q))
        best = None
        best_score = 0
        for it in qa_items:
            iq = it.get("q") or ""
            score = sum(1 for k in keys if k in iq)
            if "价" in q and it.get("topic") == "price":
                score += 2
            if score > best_score:
                best_score = score
                best = it
        if best and best_score >= 2:
            out.append(best)
        if len(out) >= limit:
            break
    seen = set()
    uniq = []
    for it in out:
        k = (it.get("q"), it.get("a"))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
    return uniq


def format_raw_block(turns: list[dict]) -> str:
    lines = []
    for i, t in enumerate(turns, 1):
        who = "我方" if t["role"] == "self" else "客户"
        ts = t.get("date") or ""
        text = t["text"].replace("\r\n", "\n")
        lines.append(f"{i}. [{ts}] {who}:")
        for ln in text.split("\n"):
            lines.append(f"   {ln}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_refined_block(turns: list[dict]) -> str:
    lines = []
    for i, t in enumerate(turns, 1):
        who = "我方" if t["role"] == "self" else "客户"
        text = t["text"].replace("\n", " ")
        n = char_len(text)
        mark = f"（{n}字）" if n else ""
        lines.append(f"{i}. {who}{mark}: {text}")
    return "\n".join(lines) + "\n"


def render_doc(
    *,
    file_id: str,
    display_name: str,
    peer_id: str,
    comm_type: str,
    total_turns: int,
    process_date: str,
    status: str,
    raw_block: str,
    refined_block: str,
    qa_pairs: list[dict],
    global_qa: list[dict],
    context_id: str,
    context_desc: str,
    context_snippet: str,
    notes: dict,
) -> str:
    qa_lines = []
    if qa_pairs or global_qa:
        for i, p in enumerate(qa_pairs, 1):
            qa_lines.append(f"* **问题 (Q):** {p['q']}")
            note = "（答复已截取关键句，完整见原文）" if p.get("a_truncated") else ""
            qa_lines.append(f"* **标准回答 (A):** {p['a']}{note}")
            qa_lines.append("")
        for g in global_qa:
            qa_lines.append(f"* **问题 (Q):** {g.get('q')} 〔补充自全局知识库 topic={g.get('topic')}〕")
            qa_lines.append(f"* **标准回答 (A):** {g.get('a')}")
            qa_lines.append("")
    else:
        qa_lines.append("* **问题 (Q):** （本段未抽出清晰标准问）")
        qa_lines.append("* **标准回答 (A):** （见原始报价/流程原文）")
        qa_lines.append("")

    findings = "\n".join(f"* {x}" for x in notes["findings"])
    edits = "\n".join(f"* {x}" for x in notes["edits"])

    return f"""# 【文档元数据】
**文件编号 (ID):** {file_id}
**用户/联系人名称:** {display_name}
**沟通类型:** {comm_type}
**总对话轮次:** {total_turns}
**处理日期:** {process_date}
**处理状态:** {status}

---

# 【原始对话记录 (Raw Transcript)】
{raw_block}
---

# 【清洗与提炼后的输出 (Cleaned Output)】
### 1. 精炼后的流畅对话 (Refined Dialogue)
{refined_block}
### 2. 关键信息提取 (Key Extraction Summary)
**[模块一：标准问答示例]**
{chr(10).join(qa_lines)}
**[模块二：高价值上下文示例 (仅在有)]**
* **上下文编号:** {context_id}
* **描述:** {context_desc}
* **对话片段:**
{context_snippet}

---
# 【分析与备注 (Analysis & Notes)】
**[分析师备注]:**
* **关键发现:**
{findings}
* **转化率评估:** {notes["conversion"]}
* **人工修改说明:**
{edits}
"""


def context_desc_of(ctx: dict) -> str:
    stages = ctx.get("stages") or []
    parts = []
    if "bargain" in stages:
        parts.append("成功议价")
    if "deal" in stages:
        parts.append("成交确认")
    elif "pay" in stages or "agree" in stages:
        parts.append("关键决策点")
    if "followup" in stages:
        parts.append("追问推进")
    if not parts:
        parts.append("高转化销售流程")
    return f"{' + '.join(parts)}（tier={ctx.get('tier')}, score={ctx.get('score')}）"


def snippet_from_turns(turns: list[dict], max_lines: int = 24) -> str:
    lines = []
    for t in turns[:max_lines]:
        who = "我方" if t["role"] == "self" else "客户"
        labels = t.get("stage_labels") or []
        tag = f" [{'/'.join(labels)}]" if labels else ""
        text = t["text"].replace("\n", " / ")
        if len(text) > 160:
            text = text[:160] + "…"
        lines.append(f"  - {who}{tag}: {text}")
    if len(turns) > max_lines:
        lines.append(f"  - …（另有 {len(turns) - max_lines} 轮，见 Raw Transcript）")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="生成标准处理文档卷宗")
    ap.add_argument(
        "--contexts",
        type=Path,
        default=SKILL / "knowledge" / "success_contexts" / "success_contexts.jsonl",
    )
    ap.add_argument(
        "--qa",
        type=Path,
        default=SKILL / "knowledge" / "qa" / "standard_qa.jsonl",
    )
    ap.add_argument("--raw-dir", type=Path, default=RAW_DEFAULT)
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=SKILL / "knowledge" / "processing_docs",
    )
    ap.add_argument("--limit", type=int, default=0, help="0=全部成功上下文")
    ap.add_argument("--process-date", type=str, default=date.today().isoformat())
    args = ap.parse_args()

    contexts = []
    with args.contexts.open(encoding="utf-8") as f:
        for line in f:
            contexts.append(json.loads(line))
    contexts.sort(key=lambda x: (-x.get("score", 0), x.get("peer_id", "")))
    if args.limit and args.limit > 0:
        contexts = contexts[: args.limit]

    qa_items = []
    if args.qa.exists():
        with args.qa.open(encoding="utf-8") as f:
            for line in f:
                qa_items.append(json.loads(line))

    out_dir = args.output_dir if args.output_dir.is_absolute() else SKILL / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    index_rows = []
    written = 0
    for n, ctx in enumerate(contexts, 1):
        peer_id = str(ctx["peer_id"])
        turns = ctx.get("turns") or []
        if len(turns) < 4:
            continue

        raw_chat = load_raw_chat(peer_id, args.raw_dir)
        display_name = None
        if raw_chat:
            display_name = raw_chat.get("name") or None
        display_name = display_name or f"peer_{peer_id}"

        ym = (ctx.get("year_month") or "000000").replace("-", "")
        file_id = f"User_{peer_id}_{ym}_C{n:03d}"
        context_id = f"Context_{n:03d}"
        blob = "\n".join(t["text"] for t in turns)
        comm_type = infer_comm_type(ctx.get("stages") or [], blob)

        refined = refine_dialogue(turns)
        local_qa = extract_local_qa(turns)
        global_qa = match_global_qa([p["q"] for p in local_qa], qa_items, limit=2)
        # 避免与 local 完全重复
        local_qset = {p["q"] for p in local_qa}
        global_qa = [g for g in global_qa if g.get("q") not in local_qset]

        notes = analysis_notes(ctx, turns, refined)
        doc = render_doc(
            file_id=file_id,
            display_name=f"{display_name}（ID: {peer_id}）",
            peer_id=peer_id,
            comm_type=comm_type,
            total_turns=len(turns),
            process_date=args.process_date,
            status="知识提取完成",
            raw_block=format_raw_block(turns),
            refined_block=format_refined_block(refined),
            qa_pairs=local_qa,
            global_qa=global_qa,
            context_id=context_id,
            context_desc=context_desc_of(ctx),
            context_snippet=snippet_from_turns(turns),
            notes=notes,
        )

        out_path = out_dir / f"{file_id}.md"
        out_path.write_text(doc, encoding="utf-8")
        written += 1
        index_rows.append(
            {
                "file_id": file_id,
                "context_id": context_id,
                "peer_id": peer_id,
                "display_name": display_name,
                "comm_type": comm_type,
                "n_turns": len(turns),
                "tier": ctx.get("tier"),
                "score": ctx.get("score"),
                "path": str(out_path.name),
            }
        )

    # index
    idx_md = ["# 处理文档索引（标准卷宗）", "", f"生成日期: {args.process_date}", f"文档数: {written}", ""]
    idx_md.append("| 文件编号 | 上下文 | peer | 类型 | 轮次 | tier | score |")
    idx_md.append("|---|---|---|---|---:|---|---:|")
    for r in index_rows:
        idx_md.append(
            f"| `{r['file_id']}` | {r['context_id']} | {r['peer_id']} | {r['comm_type']} | {r['n_turns']} | {r['tier']} | {r['score']} |"
        )
    (out_dir / "INDEX.md").write_text("\n".join(idx_md) + "\n", encoding="utf-8")
    (out_dir / "index.json").write_text(
        json.dumps({"process_date": args.process_date, "count": written, "items": index_rows}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    # blank template for manual use
    template_path = SKILL / "references" / "processing_doc_template.md"
    if not template_path.exists():
        template_path.write_text(
            """# 【文档元数据】
**文件编号 (ID):** [例如：User_001_20231026]
**用户/联系人名称:** [完整昵称或ID]
**沟通类型:** [例如：销售咨询 / 业务合作 / 售后支持]
**总对话轮次:** [计算总条数]
**处理日期:** [YYYY-MM-DD]
**处理状态:** [待处理 / 已清洗 / 知识提取完成]
---

# 【原始对话记录 (Raw Transcript)】
[这里粘贴原始的、未经过任何清洗的完整聊天记录。
请严格按照时间顺序（时间戳或序号）排列。]

---

# 【清洗与提炼后的输出 (Cleaned Output)】
### 1. 精炼后的流畅对话 (Refined Dialogue)
[这里粘贴经过指令 1.1 处理后的、**短句合并、控制在15-30字内**的、模拟真人口吻的对话版本。]

### 2. 关键信息提取 (Key Extraction Summary)
**[模块一：标准问答示例]**
* **问题 (Q):** [提取出的核心问题]
* **标准回答 (A):** [提取出的黄金答案]

**[模块二：高价值上下文示例 (仅在有)]**
* **上下文编号:** [例如：Context_001]
* **描述:** [简述该上下文的价值，例如：成功议价流程]
* **对话片段:** [粘贴最成功的完整多轮对话片段]

---
# 【分析与备注 (Analysis & Notes)】
**[分析师备注]:**
* **关键发现:** [此处记录本次对话中发现的特殊点，如：用户对某价格的反复试探等。]
* **转化率评估:** [基于该对话的初步评估]
* **人工修改说明:** [记录AI在哪里进行了关键的语气调整，以供后续人工校对。]
""",
            encoding="utf-8",
        )

    report = {
        "module": "processing_docs",
        "written": written,
        "output_dir": str(out_dir),
        "comm_type_counts": dict(Counter(r["comm_type"] for r in index_rows)),
        "tier_counts": dict(Counter(r["tier"] for r in index_rows)),
        "sample": index_rows[:5],
    }
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
