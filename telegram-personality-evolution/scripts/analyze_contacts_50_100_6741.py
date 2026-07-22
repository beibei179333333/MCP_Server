#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析 valid_message_count ∈ [50,100] 的全部联系人。

- 永久删除政策：empty_media / service / invalid 不恢复、不进入训练
- 深分析：Qwen Deep 策略 + 对话摘要画像 → cohort/ + 更新 person/
"""
from __future__ import annotations

import argparse
import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import run_qwen_deep_strategy_pilot as pilot
from build_person_portraits import build_person, load_json

SKILL = Path(__file__).resolve().parent
PIPE = Path("/Users/home/Downloads/tg_private_4y_monthly")
UNIVERSE = PIPE / "06_full_coverage" / "contact_universe.json"
RULE_BY = PIPE / "06_full_coverage" / "strategies" / "by_peer"
QWEN_BY = PIPE / "06_full_coverage" / "strategies_qwen_deep_v1" / "by_peer"
COHORT = PIPE / "06_full_coverage" / "cohort_50_100"
OUT_DIRS_PERSON = [
    PIPE / "person",
    SKILL / "person",
    Path("/Users/home/Downloads/压缩包/monthly_agent_tasks_2022-2026-07/person"),
]
MSG_MIN, MSG_MAX = 50, 100


def select_cohort() -> list[dict]:
    u = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    rows = [
        c
        for c in (u.get("contacts") or [])
        if MSG_MIN <= int(c.get("valid_message_count") or 0) <= MSG_MAX
    ]
    rows.sort(key=lambda c: (int(c.get("valid_message_count") or 0), str(c["peer_id"])))
    return rows


def write_policy() -> None:
    text = f"""# 消息过滤永久删除政策

更新：{datetime.now(timezone.utc).isoformat()}

以下类别 **永久删除**，禁止恢复、禁止进入 clean / 上下文 / 标签 / 训练集：

1. **empty_media** — 无有效文字的纯媒体
2. **service** — 系统服务消息
3. **invalid** — 空文本 / 坏时间 / 无发送者

`07_filtered_restored/` 已删除。原始 `00_raw_origin` 只读保留，但不回灌上述三类。

本批次分析对象：有效对话条数 **{MSG_MIN}–{MSG_MAX}** 的全部联系人。
"""
    for p in (
        PIPE / "FILTER_DELETE_POLICY.md",
        SKILL / "FILTER_DELETE_POLICY.md",
        COHORT / "FILTER_DELETE_POLICY.md",
    ):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def analyze_dialogue_brief(peer_id: str, n_show: int = 12) -> dict:
    """从原始 chat 抽有效文字回合摘要（不含 service/empty_media/invalid）。"""
    path = PIPE / "00_raw_origin" / f"chat_{peer_id}.json"
    if not path.exists():
        return {"peer_id": peer_id, "turns": [], "error": "missing_raw"}
    data = json.loads(path.read_text(encoding="utf-8"))
    msgs = data.get("messages") if isinstance(data, dict) else data
    turns = []
    for m in msgs or []:
        if not isinstance(m, dict):
            continue
        if str(m.get("type") or "message").lower() == "service":
            continue
        text = pilot.normalize_msg_text(pilot.extract_text(m.get("text")))
        if not text.strip():
            continue
        if not m.get("date"):
            continue
        sid = pilot.sender_id(m)
        if not sid:
            continue
        who = "我" if sid == pilot.SELF else "对方"
        turns.append({"date": m.get("date"), "who": who, "text": text[:300], "id": m.get("id")})
    # sample head+tail
    if len(turns) <= n_show:
        sample = turns
    else:
        sample = turns[: n_show // 2] + turns[-(n_show // 2) :]
    return {
        "peer_id": peer_id,
        "valid_text_turns": len(turns),
        "sample_turns": sample,
        "first_date": turns[0]["date"] if turns else None,
        "last_date": turns[-1]["date"] if turns else None,
    }


def build_contact_analysis(contact: dict, qwen: dict | None, rule: dict | None, brief: dict) -> dict:
    strategies = (qwen or rule or {}).get("strategies") or {}
    top = []
    for name, st in strategies.items():
        if not isinstance(st, dict):
            continue
        top.append(
            {
                "type": name,
                "summary": st.get("summary"),
                "verdict": st.get("verdict"),
                "actions": (st.get("actions") or [])[:3],
                "risk": st.get("risk"),
                "confidence": st.get("confidence"),
            }
        )
    return {
        "peer_id": str(contact["peer_id"]),
        "name": contact.get("name"),
        "valid_message_count": contact.get("valid_message_count"),
        "value": contact.get("value"),
        "relationship_stage": (qwen or contact).get("relationship_stage")
        or contact.get("relationship_stage"),
        "my_attitude": (qwen or contact).get("my_attitude") or contact.get("my_attitude"),
        "confidence": (qwen or contact).get("confidence") or contact.get("confidence"),
        "source": "qwen_deep_v1" if qwen else "rule_v1",
        "fact_basis": (qwen or {}).get("fact_basis") or [],
        "inference": (qwen or {}).get("inference") or [],
        "strategies_top": top[:6],
        "dialogue": brief,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "cohort": f"{MSG_MIN}_{MSG_MAX}",
        "filter_policy": "empty_media/service/invalid permanently deleted",
    }


def expand_qwen(peers: list[dict], workers: int = 4, limit: int = 0) -> dict:
    env = pilot.load_env()
    api_key = env.get("SILICONFLOW_API_KEY") or env.get("OPENAI_API_KEY")
    base_url = env.get("OPENAI_BASE_URL") or "https://api.siliconflow.cn/v1"
    model = env.get("OPENAI_MODEL") or "Qwen/Qwen3.5-397B-A17B"
    if not api_key:
        raise SystemExit("缺少 API Key")

    have = {p.stem for p in QWEN_BY.glob("*.json")}
    todo = [p for p in peers if str(p["peer_id"]) not in have]
    if limit > 0:
        todo = todo[:limit]
    print(f"qwen expand 50-100: todo={len(todo)} workers={workers} model={model}")

    pilot.BY_PEER.mkdir(parents=True, exist_ok=True)
    COHORT.mkdir(parents=True, exist_ok=True)
    jsonl = COHORT / "qwen_strategies_50_100.jsonl"
    state_path = COHORT / "run_state.json"
    lock = threading.Lock()
    ok = fail = 0

    def work(peer):
        try:
            rec = pilot.generate_one(peer, api_key, base_url, model, force_api_few=False)
            return str(peer["peer_id"]), rec, None
        except Exception as e:
            return str(peer["peer_id"]), None, str(e)

    with ThreadPoolExecutor(max_workers=workers) as ex, jsonl.open("a", encoding="utf-8") as jf:
        futs = {ex.submit(work, p): p for p in todo}
        total = len(futs)
        for i, fut in enumerate(as_completed(futs), 1):
            pid, rec, err = fut.result()
            with lock:
                if rec is not None:
                    (QWEN_BY / f"{pid}.json").write_text(
                        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    jf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    jf.flush()
                    ok += 1
                    print(f"[{i}/{total}] OK {pid} msgs={rec.get('valid_message_count')} mode={rec.get('source_mode')}")
                else:
                    fail += 1
                    print(f"[{i}/{total}] FAIL {pid}: {err}")
                state_path.write_text(
                    json.dumps(
                        {
                            "ok": ok,
                            "fail": fail,
                            "todo": total,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
    return {"ok": ok, "fail": fail, "todo": len(todo)}


def write_all_analyses(peers: list[dict]) -> dict:
    COHORT.mkdir(parents=True, exist_ok=True)
    by_peer = COHORT / "by_peer"
    by_peer.mkdir(exist_ok=True)
    stage_c = Counter()
    att_c = Counter()
    src_c = Counter()
    rows_index = []

    for i, c in enumerate(peers, 1):
        pid = str(c["peer_id"])
        qwen = load_json(QWEN_BY / f"{pid}.json")
        rule = load_json(RULE_BY / f"{pid}.json")
        brief = analyze_dialogue_brief(pid)
        analysis = build_contact_analysis(c, qwen, rule, brief)
        (by_peer / f"{pid}.json").write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # refresh person
        person = build_person(c, rule, qwen)
        blob = json.dumps(person, ensure_ascii=False, indent=2)
        for d in OUT_DIRS_PERSON:
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{pid}.json").write_text(blob, encoding="utf-8")

        stage_c[analysis["relationship_stage"]] += 1
        att_c[analysis["my_attitude"]] += 1
        src_c[analysis["source"]] += 1
        rows_index.append(
            {
                "peer_id": pid,
                "valid_message_count": c.get("valid_message_count"),
                "relationship_stage": analysis["relationship_stage"],
                "my_attitude": analysis["my_attitude"],
                "source": analysis["source"],
                "confidence": analysis["confidence"],
            }
        )
        if i % 50 == 0:
            print(f"  analysis write {i}/{len(peers)}")

    summary = {
        "cohort": f"{MSG_MIN}-{MSG_MAX}",
        "contact_count": len(peers),
        "relationship_stage": dict(stage_c),
        "my_attitude": dict(att_c),
        "source": dict(src_c),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paths": {
            "by_peer": str(by_peer),
            "index": str(COHORT / "index.jsonl"),
            "report": str(COHORT / "cohort_report.md"),
        },
    }
    (COHORT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (COHORT / "index.jsonl").open("w", encoding="utf-8") as f:
        for r in rows_index:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # markdown report
    lines = [
        f"# 联系人深分析 · 有效对话 {MSG_MIN}–{MSG_MAX} 条",
        "",
        f"- 人数：**{len(peers)}**",
        f"- 生成：{summary['generated_at']}",
        f"- 过滤政策：empty_media / service / invalid **已永久删除**（不恢复）",
        f"- 数据源：规则版全覆盖 + Qwen 深版（若已生成）",
        "",
        "## 关系阶段分布",
        "",
    ]
    for k, v in stage_c.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 我方态度分布", ""]
    for k, v in att_c.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 策略来源", ""]
    for k, v in src_c.most_common():
        lines.append(f"- {k}: {v}")
    lines += [
        "",
        "## 产物",
        "",
        f"- 逐人分析：`{by_peer}/{{peer_id}}.json`",
        f"- 索引：`index.jsonl`",
        f"- person 已刷新对应 {len(peers)} 人",
        "",
    ]
    # top samples
    lines += ["## 样例（前 15）", ""]
    for r in rows_index[:15]:
        lines.append(
            f"- `{r['peer_id']}` msgs={r['valid_message_count']} "
            f"stage={r['relationship_stage']} attitude={r['my_attitude']} "
            f"src={r['source']} conf={r['confidence']}"
        )
    (COHORT / "cohort_report.md").write_text("\n".join(lines), encoding="utf-8")

    # mirrors
    for mirror in (
        SKILL / "outputs" / "cohort_50_100",
        Path("/Users/home/Downloads/压缩包/monthly_agent_tasks_2022-2026-07") / "outputs" / "cohort_50_100",
    ):
        mirror.mkdir(parents=True, exist_ok=True)
        (mirror / "cohort_report.md").write_text("\n".join(lines), encoding="utf-8")
        (mirror / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (mirror / "PATH.txt").write_text(f"完整 by_peer 在：\n{by_peer}\n", encoding="utf-8")

    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-qwen", action="store_true", help="只写分析不调 API")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--qwen-only", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    write_policy()
    peers = select_cohort()
    sample_path = COHORT / "cohort_sample_50_100.json"
    COHORT.mkdir(parents=True, exist_ok=True)
    sample_path.write_text(json.dumps(peers, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"cohort size={len(peers)} -> {sample_path}")

    if not args.report_only and not args.skip_qwen:
        expand_qwen(peers, workers=args.workers, limit=args.limit)

    if args.qwen_only:
        return

    summary = write_all_analyses(peers)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
