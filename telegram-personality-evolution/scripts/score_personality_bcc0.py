#!/usr/bin/env python3
"""人格维度评分 / 校验：情绪、语气、专属表达、一致性。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def score_from_metrics(metrics: dict) -> dict:
    q = metrics.get("quality") or {}
    e = metrics.get("emotion") or {}
    t = metrics.get("tone") or {}
    n = metrics.get("sample_count") or 0
    conf = 0.15
    if n:
        conf = min(0.95, 0.2 + min(0.4, n / 200) + min(0.2, (metrics.get("peer_count") or 0) / 40))
    return {
        "personality_score": {
            "emotion_richness": round(
                (e.get("安慰比例") or 0)
                + (e.get("共情比例") or 0)
                + (e.get("陪伴比例") or 0),
                4,
            ),
            "tone_clarity": round(
                (t.get("简洁程度_短句占比") or 0) * 0.5
                + (t.get("口语化程度_语气词命中占比") or 0) * 0.5,
                4,
            ),
            "fragmentation": q.get("多行碎片化回复占比"),
            "coldness": t.get("冷淡或敷衍程度"),
            "style_keyword_n": len(metrics.get("style_keywords") or []),
            "confidence": round(conf, 4),
            "low_confidence": conf < 0.45 or n < 20,
        }
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    metrics = json.loads(Path(args.metrics).read_text(encoding="utf-8"))
    scored = score_from_metrics(metrics)
    metrics.update(scored)
    out = Path(args.out) if args.out else Path(args.metrics)
    out.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(scored, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
