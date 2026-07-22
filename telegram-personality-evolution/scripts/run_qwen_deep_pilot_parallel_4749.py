#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""并发续跑 Qwen 深版试点（仅处理尚未落盘的联系人）。"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import run_qwen_deep_strategy_pilot as pilot

SAMPLE = Path(__file__).resolve().parent / "outputs" / "deep_pilot" / "pilot_sample_220.json"
WORKERS = 3
lock = threading.Lock()


def main() -> None:
    env = pilot.load_env()
    api_key = env.get("SILICONFLOW_API_KEY") or env.get("OPENAI_API_KEY")
    base_url = env.get("OPENAI_BASE_URL") or "https://api.siliconflow.cn/v1"
    model = env.get("OPENAI_MODEL") or "Qwen/Qwen3.5-397B-A17B"
    if not api_key:
        raise SystemExit("missing api key")

    peers = json.loads(SAMPLE.read_text(encoding="utf-8"))
    have = {p.stem for p in pilot.BY_PEER.glob("*.json")}
    todo = [p for p in peers if str(p["peer_id"]) not in have]
    print(f"todo={len(todo)} workers={WORKERS} model={model}")

    pilot.BY_PEER.mkdir(parents=True, exist_ok=True)
    jsonl_path = pilot.OUT_ROOT / "pilot_strategies.jsonl"
    state_path = pilot.PILOT_DIR / "pilot_run_state.json"
    done = set(have)
    ok = fail = 0

    def work(peer: dict) -> tuple[str, dict | None, str | None]:
        pid = str(peer["peer_id"])
        try:
            rec = pilot.generate_one(peer, api_key, base_url, model, force_api_few=False)
            return pid, rec, None
        except Exception as e:
            return pid, None, str(e)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex, jsonl_path.open("a", encoding="utf-8") as jf:
        futs = {ex.submit(work, p): p for p in todo}
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
                    print(f"[{i}/{len(todo)}] OK {pid} msgs={rec['valid_message_count']} mode={rec['source_mode']}")
                else:
                    fail += 1
                    (pilot.PILOT_DIR / "errors.jsonl").open("a", encoding="utf-8").write(
                        json.dumps({"peer_id": pid, "error": err}, ensure_ascii=False) + "\n"
                    )
                    print(f"[{i}/{len(todo)}] FAIL {pid}: {err}")
                state_path.write_text(
                    json.dumps(
                        {
                            "done_peer_ids": sorted(done),
                            "ok": ok,
                            "fail": fail,
                            "model": model,
                            "strategy_version": pilot.STRATEGY_VERSION,
                            "parallel_workers": WORKERS,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

    summary = {
        "todo": len(todo),
        "ok": ok,
        "fail": fail,
        "done_total": len(done),
        "out_dir": str(pilot.OUT_ROOT),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    (pilot.PILOT_DIR / "pilot_parallel_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
