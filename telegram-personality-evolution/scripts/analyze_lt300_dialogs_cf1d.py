#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析个人对话 valid_message_count < 300 的联系人子集。

产出：规模分布、模式 A/B/C、漏损信号、高价值短会话清单、Markdown 报告。
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SELF_ID = "1335016610"
SKILL = Path(__file__).resolve().parent
UNIVERSE = Path(
    "/Users/home/Downloads/tg_private_4y_monthly/06_full_coverage/contact_universe.json"
)
CHAT_DIR = Path("/Users/home/Downloads/tg_private_4y_monthly/00_raw_origin")
OUT_DIR = SKILL / "reports" / "lt300_analysis"

INTENT_A = re.compile(
    r"(量很大|量大|长期|合作|项目|渠道|对接|搞一笔|介绍客户|批发|带量)",
    re.I,
)
ASK_RES = re.compile(r"(账号|卡号|汇旺|价格|多少钱|额度|号码|靓号|发我|给我)", re.I)
EMO = re.compile(r"(太难了|难啊|累了|靠谱|一起吃饭|下次聚|最近烦|人情|资金不足)", re.I)
SHORT = re.compile(
    r"^(好的?|可以|没问题|稍等|嗯+|哦+|行|ok|OK|收到|在|有|好|1|好了已经)[\s。.!！~～]*$",
    re.I,
)
TEMPLATE = re.compile(r"(自动回复|人工坐席|小本生意|哈喽！感谢|点击蓝色)")


def text_of(m: dict) -> str:
    t = m.get("text")
    if isinstance(t, str):
        return t.strip()
    if isinstance(t, list):
        return "".join(
            x if isinstance(x, str) else str((x or {}).get("text") or "") for x in t
        ).strip()
    return ""


def from_id(m: dict) -> str:
    fid = str(m.get("from_id") or "")
    return fid.replace("user", "") if fid.startswith("user") else fid


def char_len(s: str) -> int:
    return len(re.sub(r"\s+", "", s))


def load_msgs(peer_id: str) -> list[dict]:
    path = CHAT_DIR / f"chat_{peer_id}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for m in data.get("messages") or []:
        if m.get("type") not in (None, "message"):
            continue
        t = text_of(m)
        if not t:
            continue
        out.append({"from_id": from_id(m), "text": t, "date": m.get("date"), "id": m.get("id")})
    return out


def classify_dialog(msgs: list[dict]) -> dict:
    """轻量模式分 + 漏损计数。"""
    peer_t, self_t = [], []
    for m in msgs:
        if str(m["from_id"]) == str(SELF_ID):
            self_t.append(m["text"])
        else:
            peer_t.append(m["text"])
    all_peer = "\n".join(peer_t)
    all_self = "\n".join(self_t)
    a = len(INTENT_A.findall(all_peer)) + (2 if re.search(r"(自动回复|会员|收款)", all_self) else 0)
    b = len(re.findall(r"(在吗|忙吗|哈哈|晚安|朋友)", all_peer + all_self))
    b += len(EMO.findall(all_peer))
    mode = "A" if a >= b and a > 0 else ("B" if b > 0 else ("A" if a > 0 else "B"))
    if not peer_t and self_t:
        mode = "C"

    leak_a = leak_b = leak_c = 0
    examples = {"A": [], "B": [], "C": []}
    for i, m in enumerate(msgs):
        if str(m["from_id"]) == str(SELF_ID):
            continue
        pt = m["text"]
        if TEMPLATE.search(pt) or len(pt) > 400:
            continue
        # next self
        sm = None
        for j in range(i + 1, min(i + 6, len(msgs))):
            if str(msgs[j]["from_id"]) == str(SELF_ID) and not TEMPLATE.search(msgs[j]["text"]):
                sm = msgs[j]
                break
        if not sm:
            continue
        mt = sm["text"]
        if INTENT_A.search(pt) and char_len(mt) <= 5 and SHORT.match(mt):
            leak_a += 1
            if len(examples["A"]) < 2:
                examples["A"].append({"peer": pt[:100], "me": mt})
        if ASK_RES.search(pt) and (
            re.search(r"(https?://|\d{7,}|选号频道)", mt)
            or (SHORT.match(mt) and re.search(r"有", mt))
        ):
            if not re.search(r"(先|预算|定金|付款|条件|时效|锁|规格|用途|今天有效)", mt):
                leak_b += 1
                if len(examples["B"]) < 2:
                    examples["B"].append({"peer": pt[:100], "me": mt[:120]})
        if EMO.search(pt):
            if not re.search(r"(吃饭|聚|理解|不容易|靠谱|难|累|烦|下次|保重)", mt):
                if SHORT.match(mt) or re.search(r"(多少|价|开|办|链接|汇旺|号|赊账)", mt) or char_len(mt) <= 15:
                    leak_c += 1
                    if len(examples["C"]) < 2:
                        examples["C"].append({"peer": pt[:100], "me": mt[:120]})

    return {
        "mode": mode,
        "scores_hint": {"A_signals": a, "B_signals": b},
        "leak": {"A": leak_a, "B": leak_b, "C": leak_c, "total": leak_a + leak_b + leak_c},
        "examples": examples,
        "n_self": len(self_t),
        "n_peer": len(peer_t),
    }


def bucket(n: int) -> str:
    if n <= 10:
        return "1-10"
    if n <= 50:
        return "11-50"
    if n <= 100:
        return "51-100"
    if n <= 200:
        return "101-200"
    return "201-299"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    uni = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    contacts = uni.get("contacts") or []
    lt300 = [c for c in contacts if int(c.get("valid_message_count") or 0) < 300]
    ge300 = [c for c in contacts if int(c.get("valid_message_count") or 0) >= 300]

    # stats without reading all chats first
    by_bucket = Counter()
    by_tier = Counter()
    by_stage = Counter()
    by_deep = Counter()
    for c in lt300:
        n = int(c.get("valid_message_count") or 0)
        by_bucket[bucket(n)] += 1
        val = c.get("value") or {}
        by_tier[str(val.get("label") or val.get("stars") or "?")] += 1
        by_stage[str(c.get("relationship_stage") or "?")] += 1
        by_deep["deep" if c.get("deep_analysis") else "skip"] += 1

    # prioritize: high value stars + has messages, sample deep scan
    def score_contact(c: dict) -> float:
        stars = int((c.get("value") or {}).get("stars") or 0)
        n = int(c.get("valid_message_count") or 0)
        # prefer mid-short with value (not pure 1-msg noise unless stars high)
        return stars * 20 + min(n, 80) * 0.5 + (10 if c.get("deep_analysis") else 0)

    ranked = sorted(lt300, key=score_contact, reverse=True)

    # deep-analyze top N and also stratified sample
    to_scan: list[dict] = []
    seen = set()
    for c in ranked[:400]:
        pid = str(c["peer_id"])
        if pid in seen:
            continue
        seen.add(pid)
        to_scan.append(c)
    # ensure each bucket represented
    for bname in ["1-10", "11-50", "51-100", "101-200", "201-299"]:
        for c in lt300:
            if bucket(int(c.get("valid_message_count") or 0)) == bname:
                pid = str(c["peer_id"])
                if pid not in seen and int(c.get("valid_message_count") or 0) >= 3:
                    seen.add(pid)
                    to_scan.append(c)
                    break

    analyzed = []
    mode_c = Counter()
    leak_sum = Counter()
    high_leak = []
    for c in to_scan[:500]:
        pid = str(c["peer_id"])
        msgs = load_msgs(pid)
        if not msgs:
            continue
        # use actual loaded count cap
        info = classify_dialog(msgs)
        mode_c[info["mode"]] += 1
        for k, v in info["leak"].items():
            if k != "total":
                leak_sum[k] += v
        rec = {
            "peer_id": pid,
            "name": c.get("name"),
            "valid_message_count": c.get("valid_message_count"),
            "raw_message_count": c.get("raw_message_count"),
            "bucket": bucket(int(c.get("valid_message_count") or 0)),
            "value": c.get("value"),
            "relationship_stage": c.get("relationship_stage"),
            "my_attitude": c.get("my_attitude"),
            "deep_analysis": c.get("deep_analysis"),
            "deep_reason": c.get("deep_reason"),
            **info,
        }
        analyzed.append(rec)
        if info["leak"]["total"] >= 1 and int((c.get("value") or {}).get("stars") or 0) >= 3:
            high_leak.append(rec)

    high_leak.sort(key=lambda x: (-x["leak"]["total"], -int((x.get("value") or {}).get("stars") or 0)))

    # high-value short list: stars>=4 and msgs 5-299
    hv_short = [
        c
        for c in lt300
        if int((c.get("value") or {}).get("stars") or 0) >= 4
        and 5 <= int(c.get("valid_message_count") or 0) < 300
    ]
    hv_short.sort(key=lambda c: (-int((c.get("value") or {}).get("stars") or 0), int(c.get("valid_message_count") or 0)))

    summary = {
        "rule": "valid_message_count < 300",
        "total_contacts": len(contacts),
        "lt300_count": len(lt300),
        "ge300_count": len(ge300),
        "lt300_pct": round(100 * len(lt300) / max(len(contacts), 1), 2),
        "bucket_dist": dict(by_bucket),
        "value_tier_dist": dict(by_tier),
        "relationship_stage_dist": dict(by_stage),
        "deep_flag_dist": dict(by_deep),
        "scanned": len(analyzed),
        "mode_dist_scanned": dict(mode_c),
        "leak_hits_scanned": dict(leak_sum),
        "high_value_short_count": len(hv_short),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # write JSON
    (OUT_DIR / "lt300_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "lt300_analyzed_sample.json").write_text(
        json.dumps(analyzed[:200], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "lt300_high_leak.json").write_text(
        json.dumps(high_leak[:50], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "lt300_high_value_list.json").write_text(
        json.dumps(
            [
                {
                    "peer_id": c["peer_id"],
                    "name": c.get("name"),
                    "valid_message_count": c.get("valid_message_count"),
                    "value": c.get("value"),
                    "relationship_stage": c.get("relationship_stage"),
                    "deep_analysis": c.get("deep_analysis"),
                }
                for c in hv_short[:200]
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # index of all lt300 peer ids
    (OUT_DIR / "lt300_peer_index.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "peer_id": c["peer_id"],
                    "name": c.get("name"),
                    "valid_message_count": c.get("valid_message_count"),
                    "stars": (c.get("value") or {}).get("stars"),
                    "label": (c.get("value") or {}).get("label"),
                    "deep_analysis": c.get("deep_analysis"),
                    "relationship_stage": c.get("relationship_stage"),
                },
                ensure_ascii=False,
            )
            + "\n"
            for c in sorted(lt300, key=lambda x: int(x.get("valid_message_count") or 0))
        ),
        encoding="utf-8",
    )

    # Markdown report
    lines = [
        "# 个人对话 <300 条 · 分析报告",
        "",
        f"> 规则：`valid_message_count < 300`  ",
        f"> 生成：{summary['updated_at']}  ",
        f"> 本人 ID：`{SELF_ID}`",
        "",
        "## 一、规模总览",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 联系人总数 | {summary['total_contacts']} |",
        f"| **<300 条** | **{summary['lt300_count']}**（{summary['lt300_pct']}%） |",
        f"| ≥300 条 | {summary['ge300_count']} |",
        f"| 其中 deep_analysis 旗标 | {by_deep.get('deep', 0)} |",
        "",
        "### 消息量分层",
        "",
        "| 区间 | 人数 |",
        "|------|------|",
    ]
    for k in ["1-10", "11-50", "51-100", "101-200", "201-299"]:
        lines.append(f"| {k} | {by_bucket.get(k, 0)} |")

    lines += [
        "",
        "### 价值分层（<300 子集）",
        "",
        "| 标签 | 人数 |",
        "|------|------|",
    ]
    for k, v in by_tier.most_common():
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "### 关系阶段（<300 子集）",
        "",
        "| 阶段 | 人数 |",
        "|------|------|",
    ]
    for k, v in by_stage.most_common():
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "## 二、抽样深扫（模式 + 漏损）",
        "",
        f"扫描会话数：{len(analyzed)}（按价值优先 + 分层补样，上限 500）",
        "",
        f"- 模式分布：{dict(mode_c)}",
        f"- 漏损命中合计：A={leak_sum.get('A',0)} / B={leak_sum.get('B',0)} / C={leak_sum.get('C',0)}",
        "",
        "### 高价值 × 有漏损（Top 15）",
        "",
    ]
    for i, r in enumerate(high_leak[:15], 1):
        lines += [
            f"#### {i}. {r.get('name') or r['peer_id']}（`{r['peer_id']}`）· {r['valid_message_count']} 条 · stars={(r.get('value') or {}).get('stars')}",
            "",
            f"- 模式倾向：{r['mode']} · 漏损 A/B/C = {r['leak']['A']}/{r['leak']['B']}/{r['leak']['C']}",
            f"- 关系：{r.get('relationship_stage')} / 态度：{r.get('my_attitude')}",
        ]
        for t in ("A", "B", "C"):
            for ex in r.get("examples", {}).get(t) or []:
                lines.append(f"- 例[{t}] 对方：{ex['peer'][:80]} → 我：{ex['me'][:60]}")
        lines.append("")

    lines += [
        "## 三、高价值短会话清单（stars≥4 且 5–299 条）",
        "",
        f"共 **{len(hv_short)}** 人；下列前 30：",
        "",
        "| peer_id | 名称 | 条数 | stars | 阶段 |",
        "|---------|------|------|-------|------|",
    ]
    for c in hv_short[:30]:
        lines.append(
            f"| `{c['peer_id']}` | {c.get('name') or '-'} | {c.get('valid_message_count')} | "
            f"{(c.get('value') or {}).get('stars')} | {c.get('relationship_stage')} |"
        )

    lines += [
        "",
        "## 四、结论与行动",
        "",
        "1. **<300 条是主体**：多数关系停在浅层，深分析优先级应继续压在 ≤100（及高价值短会话）。",
        "2. **短会话一样会漏损**：抽样中仍见「好/稍等/有」关单与无条件甩号；条数少 ≠ 机会小。",
        "3. **优先队列**：`lt300_high_value_list.json` + `lt300_high_leak.json` 应先于长会话做话术改造与人工回访。",
        "4. **单会话复盘**：`python3 analyze_chat_modes.py --chat .../chat_<peer>.json`",
        "",
        "## 产物路径",
        "",
        "```text",
        f"{OUT_DIR}/",
        "  lt300_summary.json",
        "  lt300_peer_index.jsonl",
        "  lt300_analyzed_sample.json",
        "  lt300_high_leak.json",
        "  lt300_high_value_list.json",
        "  lt300_report.md",
        "```",
        "",
    ]
    (OUT_DIR / "lt300_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
