#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""训练模块二 · 指令 2.2：高转化率对话上下文抽取 (Success Context Mining)。

从 00_raw_origin 单 peer 私聊中，切出「提问→追问→议价→成交/关键决策」完整链条。
硬约束：单 peer 隔离；原文不润色；产出 100–300 段代表性长流程。

示例：
  python3 extract_success_context_2_2.py
  python3 extract_success_context_2_2.py --min-out 100 --max-out 300
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
RAW_DEFAULT = Path("/Users/home/Downloads/tg_private_4y_monthly/00_raw_origin")
SELF_USER_ID = "1335016610"

_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\ufeff\u00a0]")

BIZ = re.compile(
    r"(会员|Premium|汇旺|秒开|回购|飞机会员|能量|闪兑|USDT|[uUＵ]|靓号|代开)",
    re.I,
)
ASK = re.compile(
    r"(多少钱|什么价|怎么开|怎么弄|怎么搞|如何开通|开会员|要开|开通|"
    r"几个月|报价|帮我开|给我开|弄个会员|开一下|还有吗|怎么买|能开吗|"
    r"多少[uU]|啥价|什么套餐)",
    re.I,
)
FOLLOW = re.compile(
    r"(怎么付|怎么转|转哪|地址|用户名|用汇旺|U钱包|付哪里|转账|"
    r"然后呢|还有呢|截图发哪|发哪个|用什么付|支持什么)",
    re.I,
)
BARGAIN = re.compile(
    r"(便宜|少点|优惠|再便宜|打折|最低|兄弟价|熟客|能不能少|贵了|便宜点|"
    r"少一点|给个价|友情价|内部价)",
    re.I,
)
QUOTE = re.compile(
    r"(秒开|回购|\d+\s*个月|\d+\s*[uUＵ刀\$]|汇旺|只要\s*\d+|需要提供|"
    r"用户名即可|1688)",
    re.I,
)
PAY = re.compile(
    r"(转好了|转了|付款了|付了|已经转|转过去|截图|到账|付完|汇旺转|"
    r"U转了|转给你了|发你了)",
    re.I,
)
AGREE = re.compile(
    r"(就这个|开3个|开6个|开12|开一年|开三个月|开六个月|要3个|要6个|要12|"
    r"行吧|可以了|那就开|开吧|转给你|好的开|就开|定了|要这个)",
    re.I,
)
DEAL = re.compile(
    r"(已经给您开通好了|飞机会员已经给您开通|给你开通好了|帮你开好了|"
    r"已经开好|开通好了|开好了|弄好了|搞好了|搞定了|办好了|处理好了|"
    r"已经帮你开|给你开上了|会员开好|已经开通|都开好了|开好了宝)",
    re.I,
)
SOFT_CONFIRM = re.compile(
    r"^(好的?|收到|嗯+|OK|ok|好了|马上|稍等|等下就开|开了|好的稍等|马上开)",
    re.I,
)
NOISE_DEAL = re.compile(
    r"(激活流程|1800\*213|弄好了吗|词都给你搞好|自然就帮我们搞定|"
    r"商城开好了|网站：https|后台网站)",
    re.I,
)
HEAVY_AD = re.compile(
    r"(代开(?:会员)?只需提供|欢迎选择.支付|无人值守，自动开通|"
    r"成为尊贵的Premium|有机会来我店里喝茶)",
    re.I,
)


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
    if s.startswith("user"):
        return s.replace("user", "")
    return s


def load_messages(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    peer_id = str(data.get("id") or path.stem.replace("chat_", ""))
    out: list[dict] = []
    for m in data.get("messages") or []:
        if m.get("type") and m.get("type") != "message":
            continue
        t = extract_text(m.get("text"))
        if not t:
            continue
        ts = m.get("date_unixtime")
        try:
            ts = int(ts) if ts is not None else None
        except Exception:
            ts = None
        role = "self" if from_id_of(m) == SELF_USER_ID else "peer"
        out.append(
            {
                "role": role,
                "text": t,
                "ts": ts,
                "id": m.get("id"),
                "date": m.get("date"),
                "peer_id": peer_id,
            }
        )
    return out


def tag_stages(window: list[dict]) -> set[str]:
    stages: set[str] = set()
    for x in window:
        tx = x["text"]
        role = x["role"]
        if role == "peer" and ASK.search(tx):
            stages.add("ask")
        if role == "peer" and FOLLOW.search(tx):
            stages.add("followup")
        if role == "peer" and BARGAIN.search(tx):
            stages.add("bargain")
        if role == "peer" and AGREE.search(tx):
            stages.add("agree")
        if role == "self" and QUOTE.search(tx):
            stages.add("quote")
        if PAY.search(tx):
            stages.add("pay")
        if role == "self" and DEAL.search(tx) and not NOISE_DEAL.search(tx):
            stages.add("deal")
        if role == "self" and SOFT_CONFIRM.search(tx.strip()) and len(tx) <= 20:
            stages.add("soft_confirm")
    return stages


def score_funnel(stages: set[str], n: int, flips: int) -> tuple[int, str]:
    """返回 (score, tier)。tier1 最完整。"""
    core = stages & {
        "ask",
        "followup",
        "bargain",
        "quote",
        "pay",
        "agree",
        "deal",
        "soft_confirm",
    }
    score = len(core) * 3
    tier = "tier3"

    has_open = "ask" in stages or "followup" in stages
    has_quote = "quote" in stages
    has_close = bool(stages & {"deal", "agree", "pay", "soft_confirm"})

    if not (has_open and has_quote and has_close):
        return -1, "reject"

    if {"ask", "quote", "deal"} <= stages:
        score += 12
        tier = "tier1"
    elif {"ask", "quote", "pay"} <= stages or {"ask", "quote", "agree"} <= stages:
        score += 8
        tier = "tier2"
    elif {"followup", "quote"} <= stages and has_close:
        score += 5
        tier = "tier3"
    else:
        score += 2
        tier = "tier3"

    if "bargain" in stages:
        score += 6
    if "followup" in stages:
        score += 3
    if "pay" in stages:
        score += 4
    if "deal" in stages:
        score += 5
    if 12 <= n <= 40:
        score += 5
    elif 8 <= n < 12 or 40 < n <= 60:
        score += 2
    elif n > 70:
        score -= 4

    score += min(6, flips // 3)
    return score, tier


def msg_unix(m: dict) -> int | None:
    if m.get("ts") is not None:
        return m["ts"]
    d = m.get("date")
    if isinstance(d, str) and "T" in d:
        try:
            from datetime import datetime

            return int(datetime.fromisoformat(d).timestamp())
        except Exception:
            return None
    return None


def trim_after_deal(window: list[dict], pad: int = 2) -> list[dict]:
    """成交后只留少量确认，避免串入下一单。"""
    deal_i = None
    for i, x in enumerate(window):
        if x["role"] == "self" and DEAL.search(x["text"]) and not NOISE_DEAL.search(x["text"]):
            deal_i = i
            break
    if deal_i is None:
        return window
    return window[: min(len(window), deal_i + pad + 1)]


def drop_peer_ad_echo(window: list[dict]) -> list[dict]:
    """去掉客户侧误粘贴的价目广告墙。"""
    out = []
    for x in window:
        if x["role"] == "peer" and HEAVY_AD.search(x["text"]) and len(x["text"]) > 120:
            continue
        if x["role"] == "peer" and x["text"].count("秒开") >= 2 and x["text"].count("回购") >= 1:
            continue
        out.append(x)
    return out if len(out) >= 8 else window


USERNAME_ONLY = re.compile(r"^@?[A-Za-z][A-Za-z0-9_]{4,31}$")


def find_anchors(msgs: list[dict]) -> list[tuple[int, str]]:
    anchors: list[tuple[int, str]] = []
    for i, m in enumerate(msgs):
        if m["role"] == "self" and DEAL.search(m["text"]) and not NOISE_DEAL.search(m["text"]):
            anchors.append((i, "deal"))
        elif m["role"] == "peer" and (PAY.search(m["text"]) or AGREE.search(m["text"])):
            for k in range(i + 1, min(len(msgs), i + 12)):
                mk = msgs[k]
                if mk["role"] != "self":
                    continue
                if DEAL.search(mk["text"]) and not NOISE_DEAL.search(mk["text"]):
                    anchors.append((k, "deal_after_pay"))
                    break
                if SOFT_CONFIRM.search(mk["text"].strip()) and len(mk["text"]) <= 24:
                    anchors.append((i, "decision"))
                    break
        elif m["role"] == "peer" and BARGAIN.search(m["text"]):
            for k in range(i + 1, min(len(msgs), i + 25)):
                if msgs[k]["role"] == "peer" and AGREE.search(msgs[k]["text"]):
                    anchors.append((k, "bargain_decision"))
                    break
        elif m["role"] == "peer" and USERNAME_ONLY.match(m["text"].strip()):
            # 询价后发用户名 = 关键转化动作
            prev_blob = "\n".join(x["text"] for x in msgs[max(0, i - 20) : i])
            if QUOTE.search(prev_blob) and BIZ.search(prev_blob):
                anchors.append((i, "username_commit"))
    return anchors


def overlap_ratio(a: tuple[int, int], b: tuple[int, int]) -> float:
    s1, e1 = a
    s2, e2 = b
    inter = max(0, min(e1, e2) - max(s1, s2))
    if inter <= 0:
        return 0.0
    union = max(e1, e2) - min(s1, s2)
    return inter / union if union else 0.0


def annotate_turns(window: list[dict]) -> list[dict]:
    """给每轮打阶段标签，便于知识库阅读。"""
    turns = []
    for x in window:
        labels = []
        tx, role = x["text"], x["role"]
        if role == "peer" and ASK.search(tx):
            labels.append("提问")
        if role == "peer" and FOLLOW.search(tx):
            labels.append("追问")
        if role == "peer" and BARGAIN.search(tx):
            labels.append("议价")
        if role == "self" and QUOTE.search(tx):
            labels.append("报价")
        if PAY.search(tx):
            labels.append("付款")
        if role == "peer" and AGREE.search(tx):
            labels.append("同意")
        if role == "self" and DEAL.search(tx) and not NOISE_DEAL.search(tx):
            labels.append("成交")
        turns.append(
            {
                "role": role,
                "text": tx,
                "date": x.get("date"),
                "msg_id": x.get("id"),
                "stage_labels": labels,
            }
        )
    return turns


def funnel_id(peer_id: str, start_id: Any, end_id: Any) -> str:
    raw = f"{peer_id}:{start_id}:{end_id}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def mine_peer(path: Path) -> list[dict]:
    msgs = load_messages(path)
    if len(msgs) < 8:
        return []
    peer_id = msgs[0]["peer_id"]
    anchors = find_anchors(msgs)
    if not anchors:
        return []

    raw_cands: list[tuple[tuple[int, int], dict]] = []

    for anchor_i, kind in anchors:
        start = anchor_i
        t0 = msg_unix(msgs[anchor_i])
        for j in range(anchor_i - 1, -1, -1):
            if anchor_i - j > 90:
                break
            tj = msg_unix(msgs[j])
            if t0 and tj and t0 - tj > 5 * 86400:
                break
            # 相邻消息若跨天过大也切断（缺 unixtime 时用 date）
            if t0 and tj is None:
                tj2 = msg_unix(msgs[j])
                if tj2 and t0 - tj2 > 5 * 86400:
                    break
            start = j
        end = min(len(msgs), anchor_i + 6)
        window = msgs[start:end]
        window = trim_after_deal(window, pad=2)
        window = drop_peer_ad_echo(window)
        n = len(window)
        if n < 8 or n > 80:
            continue
        blob = "\n".join(x["text"] for x in window)
        if not BIZ.search(blob):
            continue
        self_n = sum(1 for x in window if x["role"] == "self")
        ad_lines = sum(1 for x in window if x["role"] == "self" and HEAVY_AD.search(x["text"]))
        if self_n and ad_lines >= 3 and ad_lines / self_n > 0.6:
            continue

        stages = tag_stages(window)
        if kind.startswith("deal"):
            stages.add("deal")
        if kind in {"decision", "bargain_decision", "username_commit"}:
            stages.add("decision")
        if kind == "username_commit":
            stages.add("agree")

        flips = sum(1 for a, b in zip(window, window[1:]) if a["role"] != b["role"])
        score, tier = score_funnel(stages, n, flips)
        if score < 0:
            continue
        # username_commit：前文有报价即可，提问可弱化为 followup/报价互动
        if "ask" not in stages and "followup" not in stages:
            if kind != "username_commit":
                continue
            # 弱提问：窗口内客户有业务短句
            if not any(
                x["role"] == "peer" and BIZ.search(x["text"]) for x in window
            ):
                continue
            stages.add("ask")
            score, tier = score_funnel(stages, n, flips)
            if score < 0:
                continue

        span_ids = (window[0]["id"], window[-1]["id"])
        item = {
            "id": funnel_id(peer_id, span_ids[0], span_ids[1]),
            "peer_id": peer_id,
            "dialog_id": f"{peer_id}_{span_ids[0]}_{span_ids[1]}",
            "year_month": (window[0].get("date") or "")[:7],
            "anchor_kind": kind,
            "tier": tier,
            "score": score,
            "stages": sorted(stages),
            "n_turns": n,
            "n_flips": flips,
            "start_msg_id": span_ids[0],
            "end_msg_id": span_ids[1],
            "start_date": window[0].get("date"),
            "end_date": window[-1].get("date"),
            "turns": annotate_turns(window),
            "source": "00_raw_origin",
            "instruction": "2.2",
        }
        raw_cands.append(((start, end), item))

    # 同 peer 去重叠：高分优先
    raw_cands.sort(key=lambda x: -x[1]["score"])
    kept: list[dict] = []
    kept_spans: list[tuple[int, int]] = []
    for span, item in raw_cands:
        if any(overlap_ratio(span, prev) >= 0.55 for prev in kept_spans):
            continue
        kept.append(item)
        kept_spans.append(span)
    return kept


def select_diverse(items: list[dict], min_out: int, max_out: int) -> list[dict]:
    items = sorted(items, key=lambda x: (-x["score"], -len(x["stages"]), x["n_turns"]))
    selected: list[dict] = []
    per_peer: Counter[str] = Counter()
    per_month: Counter[str] = Counter()
    per_tier: Counter[str] = Counter()

    # 先保 tier1/tier2
    for prefer_tier in ("tier1", "tier2", "tier3"):
        for it in items:
            if it["tier"] != prefer_tier:
                continue
            if len(selected) >= max_out:
                break
            pid = it["peer_id"]
            ym = it.get("year_month") or "unknown"
            if per_peer[pid] >= 3:
                continue
            if per_month[ym] >= max(40, max_out // 6) and len(selected) > min_out // 2:
                continue
            selected.append(it)
            per_peer[pid] += 1
            per_month[ym] += 1
            per_tier[it["tier"]] += 1

    # 不够则放宽 peer 限制
    if len(selected) < min_out:
        have = {it["id"] for it in selected}
        for it in items:
            if it["id"] in have:
                continue
            if len(selected) >= min_out:
                break
            if per_peer[it["peer_id"]] >= 5:
                continue
            selected.append(it)
            per_peer[it["peer_id"]] += 1

    return selected[:max_out]


def to_markdown(items: list[dict]) -> str:
    lines = [
        "# 高转化对话上下文（指令 2.2）",
        "",
        "筛选自单客户完整私聊：提问 → 追问 → 议价 → 成交/关键决策。原文不润色。",
        "",
    ]
    stage_order = ["提问", "追问", "议价", "报价", "付款", "同意", "成交"]
    for i, it in enumerate(items, 1):
        lines.append(f"## S{i}. peer=`{it['peer_id']}` · {it.get('year_month')} · score={it['score']} · {it['tier']}")
        lines.append("")
        lines.append(f"- stages: {', '.join(it['stages'])}")
        lines.append(f"- turns: {it['n_turns']} · {it.get('start_date')} → {it.get('end_date')}")
        lines.append("")
        # 流程摘要
        hit = []
        for lab in stage_order:
            if any(lab in t.get("stage_labels") or [] for t in it["turns"]):
                hit.append(lab)
        if hit:
            lines.append(f"**链条:** {' → '.join(hit)}")
            lines.append("")
        for t in it["turns"]:
            who = "我" if t["role"] == "self" else "客"
            tag = f" [{'/'.join(t['stage_labels'])}]" if t.get("stage_labels") else ""
            text = t["text"].replace("\n", " / ")
            if len(text) > 220:
                text = text[:220] + "…"
            lines.append(f"- **{who}**{tag}: {text}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="指令 2.2 高转化对话上下文抽取")
    ap.add_argument("--raw-dir", type=Path, default=RAW_DEFAULT)
    ap.add_argument("--min-out", type=int, default=100)
    ap.add_argument("--max-out", type=int, default=300)
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=SKILL / "train_data_refined" / "module2_2",
    )
    ap.add_argument(
        "--knowledge-dir",
        type=Path,
        default=SKILL / "knowledge" / "success_contexts",
    )
    ap.add_argument("--max-peers", type=int, default=0, help="调试：最多扫 N 个 peer，0=全量")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    files = sorted(args.raw_dir.glob("chat_*.json"))
    if args.max_peers and args.max_peers > 0:
        files = files[: args.max_peers]

    all_items: list[dict] = []
    errors = 0
    if args.workers <= 1:
        for fp in files:
            try:
                all_items.extend(mine_peer(fp))
            except Exception:
                errors += 1
    else:
        from concurrent.futures import ProcessPoolExecutor, as_completed

        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(mine_peer, fp): fp for fp in files}
            for fut in as_completed(futs):
                try:
                    all_items.extend(fut.result())
                except Exception:
                    errors += 1

    selected = select_diverse(all_items, args.min_out, args.max_out)
    selected.sort(key=lambda x: (-x["score"], x.get("year_month") or "", x["peer_id"]))

    out_dir = args.output_dir if args.output_dir.is_absolute() else SKILL / args.output_dir
    know_dir = args.knowledge_dir if args.knowledge_dir.is_absolute() else SKILL / args.knowledge_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    know_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = know_dir / "success_contexts.jsonl"
    md_path = know_dir / "success_contexts.md"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for it in selected:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    md_path.write_text(to_markdown(selected), encoding="utf-8")

    (out_dir / "success_contexts.jsonl").write_text(jsonl_path.read_text(encoding="utf-8"), encoding="utf-8")
    (out_dir / "success_contexts.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

    report = {
        "instruction": "2.2",
        "module": "success_context_mining",
        "peers_scanned": len(files),
        "candidates": len(all_items),
        "selected": len(selected),
        "min_out": args.min_out,
        "max_out": args.max_out,
        "errors": errors,
        "tier_counts": dict(Counter(x["tier"] for x in selected)),
        "stage_set_top": Counter(tuple(x["stages"]) for x in selected).most_common(12),
        "month_counts": dict(Counter(x.get("year_month") or "?" for x in selected).most_common()),
        "score_range": {
            "max": selected[0]["score"] if selected else None,
            "min": selected[-1]["score"] if selected else None,
        },
        "avg_turns": round(sum(x["n_turns"] for x in selected) / len(selected), 1) if selected else 0,
        "paths": {
            "jsonl": str(jsonl_path),
            "md": str(md_path),
            "module_dir": str(out_dir),
        },
        "examples": [
            {
                "id": x["id"],
                "peer_id": x["peer_id"],
                "tier": x["tier"],
                "score": x["score"],
                "stages": x["stages"],
                "n_turns": x["n_turns"],
                "chain": [
                    "/".join(t["stage_labels"]) or t["role"]
                    for t in x["turns"]
                    if t.get("stage_labels")
                ][:12],
            }
            for x in selected[:8]
        ],
    }
    (out_dir / "report_2_2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "last_run.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
