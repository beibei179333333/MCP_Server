#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第四阶段：为 7988 联系人生成 person/{peer_id}.json

Agent 直接读取，无需重新分析。
核心六字段：relationship / trust / business / emotion / strategy / risk
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PIPELINE = Path("/Users/home/Downloads/tg_private_4y_monthly")
SKILL = Path(__file__).resolve().parent
UNIVERSE = PIPELINE / "06_full_coverage" / "contact_universe.json"
RULE_BY = PIPELINE / "06_full_coverage" / "strategies" / "by_peer"
QWEN_BY = PIPELINE / "06_full_coverage" / "strategies_qwen_deep_v1" / "by_peer"

OUT_DIRS = [
    PIPELINE / "person",
    SKILL / "person",
    Path("/Users/home/Downloads/压缩包/monthly_agent_tasks_2022-2026-07/person"),
]

TRUST_STAGE = {
    "陌生": "低",
    "初识": "偏低",
    "熟悉": "中",
    "合作": "中高",
    "长期": "高",
    "淡化": "下滑",
    "失联": "断裂",
}


def load_json(p: Path) -> dict | None:
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def join_actions(st: dict, limit: int = 3) -> str:
    acts = [str(a).strip() for a in (st.get("actions") or []) if str(a).strip()]
    return "；".join(acts[:limit])


def pick_strategy_summary(strategies: dict) -> str:
    if not strategies:
        return "暂无可用策略摘要"
    # 优先有实质 summary 且非模板「暂不判断」的
    ranked = []
    for name, st in strategies.items():
        if not isinstance(st, dict):
            continue
        summary = str(st.get("summary") or "").strip()
        conf = float(st.get("confidence") or 0)
        verdict = str(st.get("verdict") or "")
        score = conf
        if "暂不判断" in summary:
            score -= 0.5
        if verdict == "可执行":
            score += 0.2
        ranked.append((score, name, summary, join_actions(st)))
    ranked.sort(key=lambda x: -x[0])
    parts = []
    for score, name, summary, acts in ranked[:4]:
        bit = f"【{name}】{summary}"
        if acts:
            bit += f" → {acts}"
        parts.append(bit)
    return " | ".join(parts) if parts else "暂无可用策略摘要"


def build_person(contact: dict, rule: dict | None, qwen: dict | None) -> dict[str, Any]:
    peer_id = str(contact["peer_id"])
    stage = contact.get("relationship_stage") or (rule or {}).get("relationship_stage") or "陌生"
    attitude = contact.get("my_attitude") or (rule or {}).get("my_attitude") or "被动"
    n = int(contact.get("valid_message_count") or (rule or {}).get("valid_message_count") or 0)
    value = contact.get("value") or (rule or {}).get("value") or {}
    conf = float(
        (qwen or {}).get("confidence")
        or contact.get("confidence")
        or (rule or {}).get("confidence")
        or 0
    )
    deep = bool(contact.get("deep_analysis") or (rule or {}).get("deep_analysis"))

    # prefer qwen strategies when present
    strategies = (qwen or {}).get("strategies") or (rule or {}).get("strategies") or {}
    risk_st = strategies.get("风险审核") or {}
    emotion_st = strategies.get("情绪杠杆") or {}
    biz_st = strategies.get("利益捆绑") or strategies.get("筹码对调") or {}
    long_st = strategies.get("长期关系经营") or {}

    trust_level = TRUST_STAGE.get(str(stage), "未知")
    if attitude == "高投入" and trust_level in ("中", "偏低"):
        trust_level = "中高（态度抬升）"
    if n <= 2:
        trust_note = "样本极少，信任判断低置信"
    elif conf < 0.3:
        trust_note = "置信偏低，信任仅作假设"
    else:
        trust_note = "可由阶段与互动密度支撑"

    relationship = (
        f"阶段={stage}；我方态度={attitude}；有效消息={n}；"
        f"价值={value.get('label', '')}({value.get('range', '')})；"
        f"深分析={'是' if deep else '否'}。"
        f"{(long_st.get('summary') or '')[:160]}"
    ).strip()

    trust = f"信任档={trust_level}；置信={conf:.3f}；{trust_note}。"

    business = (
        str(biz_st.get("summary") or "").strip()
        or f"价值档={value.get('label', '未知')}；阶段={stage}下的商务线索以规则/深版策略为准。"
    )
    if qwen and (qwen.get("fact_basis") or []):
        facts = "；".join(str(x)[:80] for x in qwen["fact_basis"][:3])
        business = f"{business} 事实摘录：{facts}"

    emotion = (
        str(emotion_st.get("summary") or "").strip()
        or f"情绪策略暂以阶段={stage}、态度={attitude}推断；消息少时不做深情假设。"
    )

    strategy = pick_strategy_summary(strategies)

    risk = (
        str(risk_st.get("risk") or risk_st.get("summary") or "").strip()
        or "常规风险：资金验证、越权索取、广告污染、低样本幻觉。"
    )
    if qwen and qwen.get("insufficient_evidence"):
        risk = f"证据不足闸门已开；{risk}"

    source = "qwen_deep_v1+rule" if qwen else "rule_v1"
    return {
        "peer_id": peer_id,
        "name": contact.get("name") or (rule or {}).get("name") or (qwen or {}).get("name"),
        "relationship": relationship,
        "trust": trust,
        "business": business,
        "emotion": emotion,
        "strategy": strategy,
        "risk": risk,
        # 便于 Agent 直接取用的结构化镜像（不替代六字段）
        "meta": {
            "valid_message_count": n,
            "value": value,
            "deep_analysis": deep,
            "confidence": conf,
            "relationship_stage": stage,
            "my_attitude": attitude,
            "source": source,
            "has_qwen_deep": bool(qwen),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": "person_v1",
        },
    }


def main() -> int:
    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    contacts = universe.get("contacts") or []
    for d in OUT_DIRS:
        d.mkdir(parents=True, exist_ok=True)

    qwen_ids = {p.stem for p in QWEN_BY.glob("*.json")} if QWEN_BY.exists() else set()
    n_ok = 0
    for i, c in enumerate(contacts, 1):
        pid = str(c["peer_id"])
        rule = load_json(RULE_BY / f"{pid}.json")
        qwen = load_json(QWEN_BY / f"{pid}.json") if pid in qwen_ids else None
        person = build_person(c, rule, qwen)
        blob = json.dumps(person, ensure_ascii=False, indent=2)
        for d in OUT_DIRS:
            (d / f"{pid}.json").write_text(blob, encoding="utf-8")
        n_ok += 1
        if i % 1000 == 0:
            print(f"  person {i}/{len(contacts)}")

    index = {
        "phase": 4,
        "contact_count": len(contacts),
        "written": n_ok,
        "with_qwen_deep": len(qwen_ids),
        "schema": ["relationship", "trust", "business", "emotion", "strategy", "risk"],
        "paths": [str(d) for d in OUT_DIRS],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Agent 直接读取 person/{peer_id}.json，无需重新分析。",
    }
    for d in OUT_DIRS:
        (d / "_INDEX.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(index, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
