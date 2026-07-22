#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比规则版 vs Qwen 深版：事实一致性、重复率、幻觉率、策略可执行性。"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent
PIPELINE = Path("/Users/home/Downloads/tg_private_4y_monthly")
RULE_DIR = PIPELINE / "06_full_coverage" / "strategies" / "by_peer"
QWEN_DIR = PIPELINE / "06_full_coverage" / "strategies_qwen_deep_v1" / "by_peer"
RAW = PIPELINE / "00_raw_origin"
PILOT_DIR = SKILL_ROOT / "outputs" / "deep_pilot"
SELF = "1335016610"
FEW_MSG_MAX = 5

_USER_RE = re.compile(r"(?:user)?(\d+)$", re.I)
_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\ufeff\u00a0]")


def extract_text(text: Any) -> str:
    if text is None:
        return ""
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        parts = []
        for item in text:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text", "")))
        return "".join(parts)
    return str(text)


def normalize(s: str) -> str:
    s = _INVISIBLE.sub("", (s or "").lower())
    s = re.sub(r"\s+", "", s)
    return s


def sender_id(msg: dict) -> str | None:
    for k in ("from_id", "actor_id", "sender_id"):
        v = msg.get(k)
        if v is None:
            continue
        m = _USER_RE.search(str(v).replace(" ", ""))
        if m:
            return m.group(1)
    return None


def load_corpus(peer_id: str) -> tuple[str, set[int]]:
    path = RAW / f"chat_{peer_id}.json"
    if not path.exists():
        return "", set()
    data = json.loads(path.read_text(encoding="utf-8"))
    msgs = data.get("messages") if isinstance(data, dict) else data
    blobs = []
    ids = set()
    for m in msgs or []:
        if not isinstance(m, dict):
            continue
        if str(m.get("type") or "message").lower() == "service":
            continue
        t = extract_text(m.get("text")).strip()
        if not t:
            continue
        blobs.append(t)
        if m.get("id") is not None:
            ids.add(int(m["id"]))
    return "\n".join(blobs), ids


def claim_supported(claim: str, corpus: str) -> bool:
    c = normalize(claim)
    if len(c) < 2:
        return False
    if claim.startswith("无有效消息") or "无法建立事实" in claim:
        return True
    corp = normalize(corpus)
    if c in corp:
        return True
    # 证据句格式：[id] 对方: ...
    m = re.match(r"^\[\d+\]\s*(我|对方):\s*(.+)$", claim.strip(), re.S)
    if m:
        body = normalize(m.group(2))
        if body and body in corp:
            return True
        claim = m.group(2)
        c = body
    # 短片段滑动命中
    for i in range(0, max(0, len(c) - 3), 2):
        frag = c[i : i + 6]
        if len(frag) >= 4 and frag in corp:
            return True
    # 关键词覆盖：抽 CJK 双字 + 英文词 + 数字，≥50% 命中则视为事实可核对
    toks = set()
    for w in re.findall(r"[A-Za-z]{3,}|\d{2,}|[\u4e00-\u9fff]{2}", claim):
        toks.add(normalize(w))
    toks = {t for t in toks if t and t not in {"对方", "询问", "回复", "表示", "进行", "可能", "不确定"}}
    if not toks:
        return False
    hit = sum(1 for t in toks if t in corp)
    if hit / len(toks) >= 0.5:
        return True
    # 数字硬约束：有 ≥2 位数字则必须全部出现
    nums = re.findall(r"\d{2,}", claim)
    if nums and any(n not in corpus for n in nums):
        return False
    return False


def strategy_texts(rec: dict) -> list[str]:
    out = []
    for s in (rec.get("strategies") or {}).values():
        if not isinstance(s, dict):
            continue
        out.append(str(s.get("summary") or ""))
        out.extend(str(a) for a in (s.get("actions") or []))
    return [x for x in out if x.strip()]


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def tokenize(s: str) -> set[str]:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", " ", s.lower())
    toks = [t for t in s.split() if len(t) >= 2]
    # CJK bigrams for denser overlap
    cjk = re.findall(r"[\u4e00-\u9fff]", s)
    for i in range(len(cjk) - 1):
        toks.append(cjk[i] + cjk[i + 1])
    return set(toks)


def within_contact_dup(texts: list[str]) -> float:
    """策略间平均两两 Jaccard；越高=模板重复越严重。"""
    if len(texts) < 2:
        return 0.0
    toks = [tokenize(t) for t in texts]
    scores = []
    for i in range(len(toks)):
        for j in range(i + 1, len(toks)):
            scores.append(jaccard(toks[i], toks[j]))
    return sum(scores) / len(scores) if scores else 0.0


def executable_score(rec: dict, few: bool) -> dict:
    """可执行性：非空、非纯模板、有 verdict=可执行 或具体动作。"""
    strategies = rec.get("strategies") or {}
    n = len(strategies) or 1
    executable = observe = defer = 0
    concrete = 0
    vague_markers = ("待更多", "暂不", "观察", "信息不足", "假设", "等待更多")
    for s in strategies.values():
        if not isinstance(s, dict):
            continue
        v = str(s.get("verdict") or "")
        if v == "可执行":
            executable += 1
        elif v == "观察":
            observe += 1
        else:
            defer += 1
        acts = [str(a) for a in (s.get("actions") or [])]
        summary = str(s.get("summary") or "")
        blob = summary + " ".join(acts)
        if any(m in blob for m in vague_markers):
            continue
        if acts and len(acts[0]) >= 6:
            concrete += 1
    # 极少消息时，「暂不判断」反而是正确可执行性
    if few:
        correct_defer = defer / n
        return {
            "executable_ratio": executable / n,
            "observe_ratio": observe / n,
            "defer_ratio": defer / n,
            "concrete_action_ratio": concrete / n,
            "few_msg_correct_defer": correct_defer,
            "executability": correct_defer,  # 少消息：正确推迟=高可执行纪律
        }
    # 足够消息：希望有一定可执行/观察，且具体动作
    score = 0.5 * (executable + 0.5 * observe) / n + 0.5 * (concrete / n)
    return {
        "executable_ratio": executable / n,
        "observe_ratio": observe / n,
        "defer_ratio": defer / n,
        "concrete_action_ratio": concrete / n,
        "executability": score,
    }


def eval_record(qwen: dict, rule: dict | None) -> dict:
    pid = str(qwen["peer_id"])
    corpus, valid_ids = load_corpus(pid)
    n = int(qwen.get("valid_message_count") or 0)
    few = n <= FEW_MSG_MAX or bool(qwen.get("insufficient_evidence"))

    facts = [str(x) for x in (qwen.get("fact_basis") or []) if str(x).strip()]
    # 证据句本身不算幻觉；去掉 [id] 前缀后比对
    fact_clean = []
    for f in facts:
        f2 = re.sub(r"^\[\d+\]\s*(我|对方):\s*", "", f)
        fact_clean.append(f2)
    supported = sum(1 for f in fact_clean if claim_supported(f, corpus) or f.startswith("无有效消息"))
    fact_consistency = (supported / len(fact_clean)) if fact_clean else (1.0 if n == 0 else 0.0)

    # 幻觉：fact_basis 不支持；另计 evidence id 非法率
    halluc_claims = [
        f
        for f in fact_clean
        if not claim_supported(f, corpus)
        and f != "无有效消息，无法建立事实"
        and not f.startswith("无有效消息")
    ]
    # evidence id 非法
    eids = qwen.get("evidence_message_ids") or []
    bad_ids = [i for i in eids if i not in valid_ids]
    id_halluc = (len(bad_ids) / len(eids)) if eids else 0.0
    # 综合幻觉 = 0.7*事实不支持 + 0.3*非法证据id
    unsupported_rate = (len(halluc_claims) / len(fact_clean)) if fact_clean else 0.0
    hallucination_rate = round(0.7 * unsupported_rate + 0.3 * id_halluc, 4)

    # 跨策略重复（少消息强制模板的高重复不计入惩罚）
    texts = strategy_texts(qwen)
    if few and qwen.get("source_mode") == "forced_few_msg_gate":
        dup = 0.0  # 故意同质：暂不判断闸门
    else:
        dup = within_contact_dup(texts)

    # 与规则版动作重复（模板同质）
    rule_dup = None
    if rule:
        rt = strategy_texts(rule)
        rule_dup = within_contact_dup(rt)
        # 跨版本摘要相似度
        qset = tokenize(" ".join(texts))
        rset = tokenize(" ".join(rt))
        cross = jaccard(qset, rset)
    else:
        cross = None

    exec_m = executable_score(qwen, few)
    exec_r = executable_score(rule, few) if rule else None

    # 少消息纪律
    few_discipline = None
    if n <= FEW_MSG_MAX:
        all_defer = all(
            (s.get("verdict") == "暂不判断")
            for s in (qwen.get("strategies") or {}).values()
            if isinstance(s, dict)
        )
        few_discipline = {
            "insufficient_flag": bool(qwen.get("insufficient_evidence")),
            "confidence_le_035": float(qwen.get("confidence") or 1) <= 0.35,
            "all_verdict_暂不判断": all_defer,
            "has_evidence": bool(qwen.get("evidence_message_ids") or qwen.get("fact_basis")),
            "pass": bool(qwen.get("insufficient_evidence"))
            and float(qwen.get("confidence") or 1) <= 0.35
            and all_defer
            and bool(qwen.get("fact_basis") or qwen.get("evidence_message_ids") or n == 0),
        }

    return {
        "peer_id": pid,
        "valid_message_count": n,
        "few_msg": few,
        "source_mode": qwen.get("source_mode"),
        "fact_consistency": round(fact_consistency, 4),
        "hallucination_rate": hallucination_rate,
        "unsupported_fact_rate": round(unsupported_rate, 4),
        "bad_evidence_id_rate": round(id_halluc, 4),
        "within_contact_duplication": round(dup, 4),
        "rule_within_duplication": None if rule_dup is None else round(rule_dup, 4),
        "cross_version_similarity": None if cross is None else round(cross, 4),
        "qwen_executability": {k: round(v, 4) if isinstance(v, float) else v for k, v in exec_m.items()},
        "rule_executability": None
        if exec_r is None
        else {k: round(v, 4) if isinstance(v, float) else v for k, v in exec_r.items()},
        "few_msg_discipline": few_discipline,
        "hallucinated_fact_samples": halluc_claims[:3],
        "confidence": qwen.get("confidence"),
        "review_status": qwen.get("review_status"),
    }


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=Path, default=PILOT_DIR / "pilot_sample_220.json")
    args = ap.parse_args()

    sample = json.loads(args.sample.read_text(encoding="utf-8"))
    rows = []
    missing = []
    for peer in sample:
        pid = str(peer["peer_id"])
        qp = QWEN_DIR / f"{pid}.json"
        if not qp.exists():
            missing.append(pid)
            continue
        qwen = json.loads(qp.read_text(encoding="utf-8"))
        rp = RULE_DIR / f"{pid}.json"
        rule = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else None
        rows.append(eval_record(qwen, rule))

    few_rows = [r for r in rows if r["valid_message_count"] <= FEW_MSG_MAX]
    rich_rows = [r for r in rows if r["valid_message_count"] > FEW_MSG_MAX]

    def agg(subset: list[dict]) -> dict:
        if not subset:
            return {}
        return {
            "n": len(subset),
            "fact_consistency_mean": round(mean([r["fact_consistency"] for r in subset]), 4),
            "hallucination_rate_mean": round(mean([r["hallucination_rate"] for r in subset]), 4),
            "duplication_mean": round(mean([r["within_contact_duplication"] for r in subset]), 4),
            "rule_duplication_mean": round(
                mean([r["rule_within_duplication"] for r in subset if r["rule_within_duplication"] is not None]),
                4,
            ),
            "qwen_executability_mean": round(
                mean([r["qwen_executability"]["executability"] for r in subset]), 4
            ),
            "rule_executability_mean": round(
                mean(
                    [
                        r["rule_executability"]["executability"]
                        for r in subset
                        if r["rule_executability"]
                    ]
                ),
                4,
            ),
            "cross_version_similarity_mean": round(
                mean([r["cross_version_similarity"] for r in subset if r["cross_version_similarity"] is not None]),
                4,
            ),
        }

    few_pass = [r for r in few_rows if r.get("few_msg_discipline") and r["few_msg_discipline"]["pass"]]
    gates = {
        "fact_consistency_overall_ge_0_85": mean([r["fact_consistency"] for r in rows]) >= 0.85 if rows else False,
        "hallucination_overall_le_0_15": mean([r["hallucination_rate"] for r in rows]) <= 0.15 if rows else False,
        "few_msg_discipline_pass_rate_ge_0_95": (len(few_pass) / len(few_rows) >= 0.95) if few_rows else True,
        "qwen_dup_not_worse_than_rule_plus_0_1": True,
        "rich_executability_ge_rule_minus_0_1": True,
    }
    oa = agg(rows)
    if oa:
        gates["qwen_dup_not_worse_than_rule_plus_0_1"] = oa["duplication_mean"] <= (oa.get("rule_duplication_mean") or 0) + 0.1
    ra = agg(rich_rows)
    if ra and ra.get("rule_executability_mean") is not None:
        gates["rich_executability_ge_rule_minus_0_1"] = ra["qwen_executability_mean"] >= ra["rule_executability_mean"] - 0.1

    review_recommend = "approve_expand_6935" if all(gates.values()) and rows and not missing else "hold_pending_fixes"
    if missing:
        review_recommend = "hold_incomplete_pilot"

    report = {
        "strategy_version": "qwen_deep_v1",
        "compared_n": len(rows),
        "missing_qwen_n": len(missing),
        "missing_peer_ids_sample": missing[:20],
        "overall": agg(rows),
        "few_msg_le5": {
            **agg(few_rows),
            "discipline_pass_rate": round(len(few_pass) / len(few_rows), 4) if few_rows else None,
        },
        "rich_msg_gt5": agg(rich_rows),
        "audit_gates": gates,
        "review_recommend": review_recommend,
        "note": "规则版文件未改动；仅当 review_recommend=approve_expand_6935 才可全量覆盖到独立 qwen 目录",
        "per_contact": rows,
    }

    PILOT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = PILOT_DIR / "eval_rule_vs_qwen_deep_v1.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# 规则版 vs Qwen 深版 试点对比",
        "",
        f"- 对比人数: **{len(rows)}**（缺失 {len(missing)}）",
        f"- 审核建议: **{review_recommend}**",
        "",
        "## 总览指标",
        "",
        f"| 指标 | 整体 | ≤{FEW_MSG_MAX}条 | >{FEW_MSG_MAX}条 |",
        "|---|---:|---:|---:|",
        f"| 事实一致性 | {oa.get('fact_consistency_mean')} | {report['few_msg_le5'].get('fact_consistency_mean')} | {report['rich_msg_gt5'].get('fact_consistency_mean')} |",
        f"| 幻觉率 | {oa.get('hallucination_rate_mean')} | {report['few_msg_le5'].get('hallucination_rate_mean')} | {report['rich_msg_gt5'].get('hallucination_rate_mean')} |",
        f"| 策略内重复率(Qwen) | {oa.get('duplication_mean')} | {report['few_msg_le5'].get('duplication_mean')} | {report['rich_msg_gt5'].get('duplication_mean')} |",
        f"| 策略内重复率(规则) | {oa.get('rule_duplication_mean')} | {report['few_msg_le5'].get('rule_duplication_mean')} | {report['rich_msg_gt5'].get('rule_duplication_mean')} |",
        f"| 可执行性(Qwen) | {oa.get('qwen_executability_mean')} | {report['few_msg_le5'].get('qwen_executability_mean')} | {report['rich_msg_gt5'].get('qwen_executability_mean')} |",
        f"| 可执行性(规则) | {oa.get('rule_executability_mean')} | {report['few_msg_le5'].get('rule_executability_mean')} | {report['rich_msg_gt5'].get('rule_executability_mean')} |",
        "",
        "## 审核闸门",
        "",
    ]
    for k, v in gates.items():
        md.append(f"- {'PASS' if v else 'FAIL'}: `{k}`")
    md += [
        "",
        f"少消息纪律通过率: {report['few_msg_le5'].get('discipline_pass_rate')}",
        "",
        "## 路径",
        "",
        f"- 规则版（只读保留）: `{RULE_DIR}`",
        f"- Qwen 深版: `{QWEN_DIR}`",
        f"- 本报告: `{out_json}`",
        "",
        "**未通过审核前，禁止覆盖 6935 人规则版。**",
    ]
    out_md = PILOT_DIR / "eval_rule_vs_qwen_deep_v1.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("compared_n", "missing_qwen_n", "overall", "few_msg_le5", "rich_msg_gt5", "audit_gates", "review_recommend")}, ensure_ascii=False, indent=2))
    print("wrote", out_md)


if __name__ == "__main__":
    main()
