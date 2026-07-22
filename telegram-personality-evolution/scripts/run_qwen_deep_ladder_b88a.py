#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第五阶段：Qwen Deep 阶梯扩量

220 → 1000 → 2500 → 6935

每阶必须先过质量门禁（重复率 / 幻觉 / 一致性 / 稳定性），
禁止直接从 220 跳到 6935。
"""
from __future__ import annotations

import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import eval_rule_vs_qwen_deep as ev
import run_qwen_deep_strategy_pilot as pilot

SKILL = Path(__file__).resolve().parent
PIPE = Path("/Users/home/Downloads/tg_private_4y_monthly")
PILOT = SKILL / "outputs" / "deep_pilot"
LADDER_DIR = PILOT / "ladder"
DEEP_JSONL = PIPE / "06_full_coverage" / "deep_priority_le50.jsonl"
EXISTING_220 = PILOT / "pilot_sample_220.json"

# 阶梯目标（含已完成人数）
TIERS = [220, 1000, 2500, 6935]

# 门禁阈值（相对上阶或绝对）
GATES = {
    "fact_consistency_min": 0.85,
    "hallucination_max": 0.15,
    "few_msg_discipline_min": 0.95,
    "dup_delta_vs_rule_max": 0.10,  # qwen_dup <= rule_dup + 0.10
    "exec_delta_vs_rule_min": -0.10,  # qwen_exec >= rule_exec - 0.10
    # 稳定性：与上一阶指标漂移
    "stability_fact_drop_max": 0.05,
    "stability_halluc_rise_max": 0.05,
    "stability_dup_rise_max": 0.08,
}


def load_deep_priority() -> list[dict]:
    rows = []
    with DEEP_JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    rows.sort(key=lambda x: int(x.get("priority_rank") or 10**9))
    return rows


def stratified_extend(base: list[dict], pool: list[dict], target: int) -> list[dict]:
    """在保留 base 的前提下，从 pool 补到 target；优先 deep 排序，兼顾价值层。"""
    have = {str(x["peer_id"]) for x in base}
    out = list(base)
    if len(out) >= target:
        return out[:target]

    # 按价值层轮转补人，避免某一层垄断
    by_label: dict[str, list] = {}
    for p in pool:
        pid = str(p["peer_id"])
        if pid in have:
            continue
        lab = (p.get("value") or {}).get("label") or "未知"
        by_label.setdefault(lab, []).append(p)

    labels = sorted(by_label.keys(), key=lambda L: -len(by_label[L]))
    idx = {L: 0 for L in labels}
    while len(out) < target:
        progressed = False
        for L in labels:
            i = idx[L]
            arr = by_label[L]
            if i >= len(arr):
                continue
            p = arr[i]
            idx[L] = i + 1
            out.append(p)
            have.add(str(p["peer_id"]))
            progressed = True
            if len(out) >= target:
                break
        if not progressed:
            # 兜底：按优先级剩余全部
            for p in pool:
                pid = str(p["peer_id"])
                if pid in have:
                    continue
                out.append(p)
                have.add(pid)
                if len(out) >= target:
                    break
            break
    return out[:target]


def build_ladder_samples() -> dict[str, Path]:
    LADDER_DIR.mkdir(parents=True, exist_ok=True)
    pool = load_deep_priority()
    base = json.loads(EXISTING_220.read_text(encoding="utf-8")) if EXISTING_220.exists() else pool[:220]
    paths = {}
    current = list(base)
    for t in TIERS:
        current = stratified_extend(current, pool, t)
        path = LADDER_DIR / f"ladder_sample_{t}.json"
        path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        paths[str(t)] = path
        print(f"ladder sample {t}: {len(current)} -> {path}")
    # also write 6935 = full deep list order preserved in stratified result
    meta = {
        "tiers": TIERS,
        "samples": {k: str(v) for k, v in paths.items()},
        "policy": "220→1000→2500→6935；每阶质量门禁通过后才可升阶",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (LADDER_DIR / "ladder_manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return paths


def eval_tier(tier: int, peer_ids: list[str] | None = None) -> dict[str, Any]:
    """对当前已落盘的 Qwen 子集跑质量评估（复用 eval 指标逻辑）。"""
    # 复用 eval 主流程：临时构造对比集
    qwen_dir = pilot.BY_PEER
    rule_dir = ev.RULE_DIR
    ids = peer_ids
    if ids is None:
        sample = json.loads((LADDER_DIR / f"ladder_sample_{tier}.json").read_text(encoding="utf-8"))
        ids = [str(x["peer_id"]) for x in sample]

    present = [pid for pid in ids if (qwen_dir / f"{pid}.json").exists()]
    missing = [pid for pid in ids if pid not in set(present)]

    # 直接调用 eval 内部：写临时 sample 文件
    tmp = LADDER_DIR / f"_eval_subset_{tier}.json"
    tmp.write_text(
        json.dumps([{"peer_id": p} for p in present], ensure_ascii=False),
        encoding="utf-8",
    )

    # 手工聚合（与 eval 一致的核心指标）
    rows = []
    for pid in present:
        q = json.loads((qwen_dir / f"{pid}.json").read_text(encoding="utf-8"))
        rpath = rule_dir / f"{pid}.json"
        r = json.loads(rpath.read_text(encoding="utf-8")) if rpath.exists() else {}
        corpus, _ = ev.load_corpus(pid)
        # fact consistency / hallucination
        facts = q.get("fact_basis") or []
        supported = sum(1 for f in facts if ev.claim_supported(str(f), corpus))
        fact_c = (supported / len(facts)) if facts else 1.0
        halluc = 1.0 - fact_c if facts else 0.0
        # dup within strategies：排除「暂不判断」强制同文（少消息闸门的预期行为）
        def strategy_dup(strategies: dict) -> float:
            summaries = []
            for st in (strategies or {}).values():
                if not isinstance(st, dict):
                    continue
                s = str(st.get("summary") or "").strip()
                if not s or "暂不判断" in s:
                    continue
                summaries.append(s)
            if len(summaries) < 2:
                return 0.0
            normed = [ev.normalize(s) for s in summaries]
            same = total = 0
            for i in range(len(normed)):
                for j in range(i + 1, len(normed)):
                    total += 1
                    if normed[i] and normed[i] == normed[j]:
                        same += 1
            return same / total if total else 0.0

        dup = strategy_dup(q.get("strategies") or {})
        rdup = strategy_dup(r.get("strategies") or {})
        # executability
        exec_q = 0
        n_st = 0
        for st in (q.get("strategies") or {}).values():
            if not isinstance(st, dict):
                continue
            n_st += 1
            v = st.get("verdict")
            if v in ("可执行", "观察", "暂不判断") and (st.get("actions") or []):
                exec_q += 1
        exec_rate = exec_q / n_st if n_st else 0.0
        n_msg = int(q.get("valid_message_count") or 0)
        few = n_msg <= 5
        discipline_ok = True
        if few:
            # 极少消息应多为暂不判断
            bad = 0
            for st in (q.get("strategies") or {}).values():
                if isinstance(st, dict) and st.get("verdict") not in (None, "暂不判断", "观察"):
                    if st.get("verdict") == "可执行" and "暂不判断" not in str(st.get("summary") or ""):
                        bad += 1
            # also check insufficient flag or forced summaries
            if q.get("insufficient_evidence") or all(
                "暂不判断" in str((st or {}).get("summary") or "")
                for st in (q.get("strategies") or {}).values()
                if isinstance(st, dict)
            ):
                discipline_ok = True
            else:
                discipline_ok = bad == 0
        rows.append(
            {
                "peer_id": pid,
                "fact_consistency": fact_c,
                "hallucination": halluc,
                "dup_qwen": dup,
                "dup_rule": rdup,
                "exec_qwen": exec_rate,
                "few": few,
                "discipline_ok": discipline_ok,
            }
        )

    def mean(key):
        xs = [r[key] for r in rows]
        return sum(xs) / len(xs) if xs else 0.0

    few_rows = [r for r in rows if r["few"]]
    disc = (
        sum(1 for r in few_rows if r["discipline_ok"]) / len(few_rows) if few_rows else 1.0
    )
    metrics = {
        "tier": tier,
        "target": tier,
        "present": len(present),
        "missing": len(missing),
        "coverage_ok": len(present) >= tier and len(missing) == 0,
        "fact_consistency": mean("fact_consistency"),
        "hallucination": mean("hallucination"),
        "dup_qwen": mean("dup_qwen"),
        "dup_rule": mean("dup_rule"),
        "exec_qwen": mean("exec_qwen"),
        "few_msg_discipline": disc,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
    return metrics


def check_gates(metrics: dict, prev: dict | None = None) -> dict[str, Any]:
    checks = []
    def add(name, ok, detail=""):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})

    add(
        "coverage",
        metrics.get("coverage_ok") or metrics["present"] >= min(metrics["tier"], metrics["present"]),
        f"present={metrics['present']} missing={metrics['missing']}",
    )
    # soft coverage: allow eval on present subset when expanding mid-run
    add("fact_consistency", metrics["fact_consistency"] >= GATES["fact_consistency_min"],
        f"{metrics['fact_consistency']:.4f}")
    add("hallucination", metrics["hallucination"] <= GATES["hallucination_max"],
        f"{metrics['hallucination']:.4f}")
    add("few_msg_discipline", metrics["few_msg_discipline"] >= GATES["few_msg_discipline_min"],
        f"{metrics['few_msg_discipline']:.4f}")
    add(
        "dup_vs_rule",
        metrics["dup_qwen"] <= metrics["dup_rule"] + GATES["dup_delta_vs_rule_max"],
        f"qwen={metrics['dup_qwen']:.4f} rule={metrics['dup_rule']:.4f}",
    )

    if prev:
        add(
            "stability_fact",
            (prev["fact_consistency"] - metrics["fact_consistency"]) <= GATES["stability_fact_drop_max"],
            f"prev={prev['fact_consistency']:.4f} now={metrics['fact_consistency']:.4f}",
        )
        add(
            "stability_halluc",
            (metrics["hallucination"] - prev["hallucination"]) <= GATES["stability_halluc_rise_max"],
            f"prev={prev['hallucination']:.4f} now={metrics['hallucination']:.4f}",
        )
        add(
            "stability_dup",
            (metrics["dup_qwen"] - prev["dup_qwen"]) <= GATES["stability_dup_rise_max"],
            f"prev={prev['dup_qwen']:.4f} now={metrics['dup_qwen']:.4f}",
        )

    passed = all(c["pass"] for c in checks if c["name"] != "coverage")
    # coverage: for gate-to-next, require full tier present
    full = metrics["present"] >= metrics["tier"] and metrics["missing"] == 0
    return {
        "passed_quality": passed,
        "passed_full_coverage": full,
        "can_promote_next": passed and full,
        "checks": checks,
        "metrics": metrics,
        "recommendation": (
            "promote_next_tier"
            if passed and full
            else ("continue_fill_tier" if passed and not full else "halt_fix_quality")
        ),
    }


def run_expand(tier: int, workers: int = 3, limit: int = 0) -> dict:
    """把 ladder_sample_{tier} 中尚未落盘者跑完。"""
    sample_path = LADDER_DIR / f"ladder_sample_{tier}.json"
    if not sample_path.exists():
        build_ladder_samples()
    peers = json.loads(sample_path.read_text(encoding="utf-8"))
    if limit > 0:
        # only expand among missing, then slice
        have = {p.stem for p in pilot.BY_PEER.glob("*.json")}
        missing = [p for p in peers if str(p["peer_id"]) not in have]
        peers = missing[:limit]
        print(f"limit mode: processing {len(peers)} missing")
    else:
        have = {p.stem for p in pilot.BY_PEER.glob("*.json")}
        peers = [p for p in peers if str(p["peer_id"]) not in have]

    env = pilot.load_env()
    api_key = env.get("SILICONFLOW_API_KEY") or env.get("OPENAI_API_KEY")
    base_url = env.get("OPENAI_BASE_URL") or "https://api.siliconflow.cn/v1"
    model = env.get("OPENAI_MODEL") or "Qwen/Qwen3.5-397B-A17B"
    if not api_key:
        raise SystemExit("缺少 API Key")

    print(f"expand tier={tier} todo={len(peers)} workers={workers} model={model}")
    pilot.BY_PEER.mkdir(parents=True, exist_ok=True)
    jsonl_path = pilot.OUT_ROOT / f"ladder_{tier}_strategies.jsonl"
    state_path = LADDER_DIR / f"ladder_{tier}_run_state.json"
    lock = threading.Lock()
    ok = fail = 0
    done = set(have) if limit == 0 else {p.stem for p in pilot.BY_PEER.glob("*.json")}

    def work(peer: dict):
        pid = str(peer["peer_id"])
        try:
            rec = pilot.generate_one(peer, api_key, base_url, model, force_api_few=False)
            return pid, rec, None
        except Exception as e:
            return pid, None, str(e)

    with ThreadPoolExecutor(max_workers=workers) as ex, jsonl_path.open("a", encoding="utf-8") as jf:
        futs = {ex.submit(work, p): p for p in peers}
        total = len(futs)
        for i, fut in enumerate(as_completed(futs), 1):
            pid, rec, err = fut.result()
            with lock:
                if rec is not None:
                    (pilot.BY_PEER / f"{pid}.json").write_text(
                        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    jf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    jf.flush()
                    done.add(pid)
                    ok += 1
                    print(f"[{i}/{total}] OK {pid} msgs={rec['valid_message_count']} mode={rec['source_mode']}")
                else:
                    fail += 1
                    print(f"[{i}/{total}] FAIL {pid}: {err}")
                state_path.write_text(
                    json.dumps(
                        {
                            "tier": tier,
                            "ok": ok,
                            "fail": fail,
                            "done_total": len(done),
                            "todo": total,
                            "model": model,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
    return {"tier": tier, "ok": ok, "fail": fail, "done_total": len(done)}


def write_gate_report(tier: int, gate: dict) -> Path:
    LADDER_DIR.mkdir(parents=True, exist_ok=True)
    path = LADDER_DIR / f"gate_{tier}.json"
    path.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    md = LADDER_DIR / f"gate_{tier}.md"
    lines = [
        f"# Qwen Deep 阶梯门禁 · tier={tier}",
        "",
        f"- recommendation: **{gate['recommendation']}**",
        f"- quality_pass: {gate['passed_quality']}",
        f"- full_coverage: {gate['passed_full_coverage']}",
        f"- can_promote_next: {gate['can_promote_next']}",
        "",
        "## metrics",
        "",
        "```json",
        json.dumps(gate["metrics"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## checks",
        "",
    ]
    for c in gate["checks"]:
        lines.append(f"- {'PASS' if c['pass'] else 'FAIL'}: `{c['name']}` · {c['detail']}")
    lines += [
        "",
        "## 阶梯纪律",
        "",
        "220 → 1000 → 2500 → 6935；禁止跳阶。",
        "看重复率、幻觉、一致性、稳定性。",
        "",
    ]
    md.write_text("\n".join(lines), encoding="utf-8")
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-samples", action="store_true")
    ap.add_argument("--eval-tier", type=int, default=0)
    ap.add_argument("--expand-tier", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="仅扩 N 个缺失（烟测）")
    ap.add_argument("--auto-ladder", action="store_true", help="评估当前最高满阶并建议/扩下一阶")
    args = ap.parse_args()

    if args.build_samples or args.auto_ladder or args.expand_tier or args.eval_tier:
        if not (LADDER_DIR / "ladder_manifest.json").exists() or args.build_samples:
            build_ladder_samples()

    state_path = LADDER_DIR / "ladder_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
        "current_tier": 220,
        "gates": {},
    }

    if args.eval_tier:
        tier = args.eval_tier
        prev_m = None
        prev_tier = None
        for t in TIERS:
            if t < tier and t in state.get("gates", {}):
                prev_tier = t
                prev_m = state["gates"][str(t)]["metrics"]
        metrics = eval_tier(tier)
        # coverage_ok based on actual target file
        sample = json.loads((LADDER_DIR / f"ladder_sample_{tier}.json").read_text(encoding="utf-8"))
        ids = [str(x["peer_id"]) for x in sample]
        present = sum(1 for pid in ids if (pilot.BY_PEER / f"{pid}.json").exists())
        metrics["present"] = present
        metrics["missing"] = tier - present if present <= tier else 0
        metrics["coverage_ok"] = present >= tier
        gate = check_gates(metrics, prev_m)
        state.setdefault("gates", {})[str(tier)] = gate
        if gate["can_promote_next"]:
            state["current_tier"] = tier
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        md = write_gate_report(tier, gate)
        print(json.dumps({"tier": tier, "recommendation": gate["recommendation"], "report": str(md)}, ensure_ascii=False, indent=2))
        return

    if args.expand_tier:
        # require previous tier gate if expanding beyond 220
        tier = args.expand_tier
        idx = TIERS.index(tier)
        if idx > 0:
            prev = TIERS[idx - 1]
            gprev = state.get("gates", {}).get(str(prev))
            if not gprev:
                print(f"先评估上一阶 tier={prev}")
                metrics = eval_tier(prev)
                sample = json.loads((LADDER_DIR / f"ladder_sample_{prev}.json").read_text(encoding="utf-8"))
                ids = [str(x["peer_id"]) for x in sample]
                present = sum(1 for pid in ids if (pilot.BY_PEER / f"{pid}.json").exists())
                metrics["present"] = present
                metrics["missing"] = max(0, prev - present)
                metrics["coverage_ok"] = present >= prev
                gprev = check_gates(metrics, None)
                state.setdefault("gates", {})[str(prev)] = gprev
                write_gate_report(prev, gprev)
                state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            if not gprev.get("can_promote_next") and not args.limit:
                raise SystemExit(
                    f"上一阶 {prev} 未放行（{gprev.get('recommendation')}），禁止扩到 {tier}。"
                    "可用 --limit 做烟测，或先修质量。"
                )
        summary = run_expand(tier, workers=args.workers, limit=args.limit)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        # auto eval after expand
        metrics = eval_tier(tier)
        sample = json.loads((LADDER_DIR / f"ladder_sample_{tier}.json").read_text(encoding="utf-8"))
        ids = [str(x["peer_id"]) for x in sample]
        present = sum(1 for pid in ids if (pilot.BY_PEER / f"{pid}.json").exists())
        metrics["present"] = present
        metrics["missing"] = max(0, tier - present)
        metrics["coverage_ok"] = present >= tier
        prev_m = None
        if idx > 0:
            prev_m = state.get("gates", {}).get(str(TIERS[idx - 1]), {}).get("metrics")
        gate = check_gates(metrics, prev_m)
        state.setdefault("gates", {})[str(tier)] = gate
        if gate["can_promote_next"]:
            state["current_tier"] = tier
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        write_gate_report(tier, gate)
        print(json.dumps({"recommendation": gate["recommendation"]}, ensure_ascii=False))
        return

    if args.auto_ladder:
        # eval 220, then print next action
        for t in TIERS:
            sample = json.loads((LADDER_DIR / f"ladder_sample_{t}.json").read_text(encoding="utf-8"))
            ids = [str(x["peer_id"]) for x in sample]
            present = sum(1 for pid in ids if (pilot.BY_PEER / f"{pid}.json").exists())
            if present < t:
                print(f"highest_incomplete_tier={t} present={present}/{t}")
                metrics = eval_tier(t)
                metrics["present"] = present
                metrics["missing"] = t - present
                metrics["coverage_ok"] = False
                prev_m = None
                idx = TIERS.index(t)
                if idx > 0 and str(TIERS[idx - 1]) in state.get("gates", {}):
                    prev_m = state["gates"][str(TIERS[idx - 1])]["metrics"]
                elif idx > 0:
                    # eval prev fully
                    pm = eval_tier(TIERS[idx - 1])
                    ps = json.loads((LADDER_DIR / f"ladder_sample_{TIERS[idx-1]}.json").read_text(encoding="utf-8"))
                    pp = sum(1 for x in ps if (pilot.BY_PEER / f"{x['peer_id']}.json").exists())
                    pm["present"] = pp
                    pm["missing"] = max(0, TIERS[idx - 1] - pp)
                    pm["coverage_ok"] = pp >= TIERS[idx - 1]
                    gprev = check_gates(pm, None)
                    state.setdefault("gates", {})[str(TIERS[idx - 1])] = gprev
                    write_gate_report(TIERS[idx - 1], gprev)
                    prev_m = pm
                gate = check_gates(metrics, prev_m)
                state.setdefault("gates", {})[str(t)] = gate
                state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                write_gate_report(t, gate)
                print(json.dumps({
                    "action": f"expand_tier_{t}",
                    "recommendation": gate["recommendation"],
                    "prev_can_promote": (state.get("gates", {}).get(str(TIERS[idx-1]), {}) or {}).get("can_promote_next") if idx > 0 else True,
                }, ensure_ascii=False, indent=2))
                return
        print("all tiers complete")
        return

    if args.build_samples:
        return
    ap.print_help()


if __name__ == "__main__":
    main()
