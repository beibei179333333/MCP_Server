#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""高价值机会审计：扫描「我」的短回应如何扼杀大额/深度机会。"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SELF_ID = "1335016610"
CHAT_DIR = Path("/Users/home/Downloads/tg_private_4y_monthly/00_raw_origin")
OUT_DIR = Path(__file__).resolve().parent / "reports" / "opportunity_audit"

OPPORTUNITY = re.compile(
    r"(量很大|量比较大|一天量|长期合作|有个项目|项目想找|能不能搞定|"
    r"给你介绍|介绍客户|渠道批发|批发商|带量|放量|想跟你合作|和你合作|"
    r"稳定拿货|比市场低|大单|走量)",
    re.I,
)
RESOURCE = re.compile(
    r"(账号|卡号|汇旺|额度|渠道|端口|线路|号码|靓号|API|接口|库存|"
    r"能量|TRX|会员|Premium|白资|公户|卡商|号商|码)",
    re.I,
)
ASK_RESOURCE = re.compile(
    r"(有没有|有吗|能给|给我|发我|多少钱|什么价|能不能|还有吗|现成|"
    r"帮忙弄|帮我开|帮我弄|求个|要一个)",
    re.I,
)
RELATIONAL = re.compile(
    r"(最近太难|太难了|还是你靠谱|你靠谱|下次一起|一起吃饭|喝一杯|"
    r"兄弟|老哥|谢谢你|多亏你|帮大忙|信任你|信得过|私人|"
    r"心情不好|压力大|不容易|照顾|记得你)",
    re.I,
)
SHORT_OK = re.compile(
    r"^(好的?|可以|没问题|稍等|嗯+|哦+|行|ok|OK|收到|在|有|没有|好|"
    r"可以的|没问题的|稍等一下|等下|好哒|好呀|嗯嗯|哦哦)[\s。.!！~～]*$",
    re.I,
)
COND_MARK = re.compile(
    r"(先|需要|前提|预算|定金|付款|打款|确认|条件|时效|今天|有效|"
    r"量|价|多少|规格|对接人|合同|保证金)",
    re.I,
)
BIZ_ONLY = re.compile(
    r"(多少钱|价格|开通|办理|链接|地址|汇旺|USDT|会员|号码|卡|"
    r"好了|已开|已办|发你|看下)",
    re.I,
)
TEMPLATE = re.compile(
    r"(自动回复|人工坐席|小本生意|哈喽！感谢|点击蓝色|正在转接)",
)


def text_of(m: dict) -> str:
    t = m.get("text")
    if isinstance(t, str):
        return t.strip()
    if isinstance(t, list):
        parts = []
        for x in t:
            if isinstance(x, str):
                parts.append(x)
            elif isinstance(x, dict):
                parts.append(str(x.get("text") or ""))
        return "".join(parts).strip()
    return ""


def from_id(m: dict) -> str:
    fid = str(m.get("from_id") or "")
    return fid.replace("user", "") if fid.startswith("user") else fid


def char_len(s: str) -> int:
    return len(re.sub(r"\s+", "", s))


def load_msgs(path: Path) -> tuple[str, str, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    peer = str(data.get("id") or path.stem.replace("chat_", ""))
    name = str(data.get("name") or peer)
    out = []
    for m in data.get("messages") or []:
        if m.get("type") not in (None, "message"):
            continue
        t = text_of(m)
        if not t:
            continue
        out.append(
            {
                "from_id": from_id(m),
                "text": t,
                "date": m.get("date"),
                "id": m.get("id"),
            }
        )
    return peer, name, out


def next_self_replies(msgs: list[dict], i: int, self_id: str, window: int = 4) -> list[dict]:
    reps = []
    for j in range(i + 1, min(i + 1 + window, len(msgs))):
        m = msgs[j]
        if from_id(m) if False else str(m["from_id"]) != str(self_id):
            # stop if peer speaks again before self? allow peer filler
            if str(m["from_id"]) != str(self_id):
                if reps:
                    break
                continue
        if str(m["from_id"]) == str(self_id):
            reps.append(m)
            if len(reps) >= 2:
                break
    return reps


def scan(limit_chats: int = 0) -> dict:
    paths = sorted(CHAT_DIR.glob("chat_*.json"))
    if limit_chats:
        paths = paths[:limit_chats]

    p1: list[dict] = []
    p2: list[dict] = []
    p3: list[dict] = []

    for path in paths:
        try:
            peer, name, msgs = load_msgs(path)
        except Exception:
            continue
        for i, m in enumerate(msgs):
            if str(m["from_id"]) == str(SELF_ID):
                continue
            peer_t = m["text"]
            if TEMPLATE.search(peer_t):
                continue
            reps = []
            for j in range(i + 1, min(i + 6, len(msgs))):
                nm = msgs[j]
                if str(nm["from_id"]) != str(SELF_ID):
                    if reps:
                        break
                    continue
                if TEMPLATE.search(nm["text"]):
                    continue
                reps.append(nm)
                if len(reps) >= 2:
                    break
            if not reps:
                continue
            my = reps[0]
            my_t = my["text"]
            my_len = char_len(my_t)

            # Pattern 1: opportunity + short empty reply
            if OPPORTUNITY.search(peer_t) and my_len <= 5 and SHORT_OK.match(my_t):
                if not COND_MARK.search(my_t):
                    p1.append(
                        {
                            "pattern": 1,
                            "peer_id": peer,
                            "name": name,
                            "date": m.get("date"),
                            "peer_quote": peer_t[:200],
                            "my_quote": my_t,
                            "opp_hits": OPPORTUNITY.findall(peer_t)[:5],
                            "score": 10 + len(OPPORTUNITY.findall(peer_t)) * 2,
                        }
                    )

            # Pattern 2: resource ask + instant confirm/provide without conditions
            if RESOURCE.search(peer_t) and ASK_RESOURCE.search(peer_t):
                provides = bool(
                    re.search(
                        r"(有|可以|能|给你|发你|这是|链接|http|地址|账号|卡号|\d{5,})",
                        my_t,
                        re.I,
                    )
                )
                short_yes = my_len <= 12 and SHORT_OK.match(my_t)
                if (provides or short_yes) and not COND_MARK.search(my_t):
                    # exclude pure "没有"
                    if re.fullmatch(r"没有[!！.。]*", my_t.strip()):
                        continue
                    p2.append(
                        {
                            "pattern": 2,
                            "peer_id": peer,
                            "name": name,
                            "date": m.get("date"),
                            "peer_quote": peer_t[:200],
                            "my_quote": my_t[:200],
                            "res_hits": RESOURCE.findall(peer_t)[:5],
                            "score": 8
                            + (5 if provides else 0)
                            + (3 if short_yes else 0)
                            + min(my_len, 40) // 10,
                        }
                    )

            # Pattern 3: relational signal ignored, biz-only reply
            if RELATIONAL.search(peer_t):
                rel_ack = bool(
                    re.search(
                        r"(吃饭|兄弟|理解|不容易|靠谱|难|压力|下次|喝|保重|哈哈)",
                        my_t,
                    )
                )
                biz = bool(BIZ_ONLY.search(my_t)) or my_len <= 8
                if not rel_ack and (biz or SHORT_OK.match(my_t) or my_len <= 15):
                    # if my reply is long but only biz
                    if my_len > 15 and not BIZ_ONLY.search(my_t) and not SHORT_OK.match(my_t):
                        # maybe emotional - skip
                        if not re.search(r"(钱|开|办|价|链|号|卡|汇)", my_t):
                            continue
                    p3.append(
                        {
                            "pattern": 3,
                            "peer_id": peer,
                            "name": name,
                            "date": m.get("date"),
                            "peer_quote": peer_t[:200],
                            "my_quote": my_t[:200],
                            "rel_hits": RELATIONAL.findall(peer_t)[:5],
                            "score": 9 + len(RELATIONAL.findall(peer_t)) * 2,
                        }
                    )

    def top(xs: list[dict], n: int = 12) -> list[dict]:
        # diversify by peer
        xs = sorted(xs, key=lambda x: -x["score"])
        seen = set()
        out = []
        for x in xs:
            if x["peer_id"] in seen:
                continue
            seen.add(x["peer_id"])
            out.append(x)
            if len(out) >= n:
                break
        return out

    return {
        "pattern1": top(p1, 15),
        "pattern2": top(p2, 15),
        "pattern3": top(p3, 15),
        "counts": {"p1": len(p1), "p2": len(p2), "p3": len(p3)},
        "scanned_chats": len(paths),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# --- handbook rewrite helpers ---

def rewrite_p1(peer_q: str, my_q: str) -> dict:
    return {
        "诊断": "价值归零式回应：把战略试探压成事务确认，主动权交回对方。",
        "错失": "长期/放量/项目对接的议价权与筛选权；对方只会把你当执行端。",
        "改造话术": _p1_line(peer_q),
        "策略意图": "先确认规模与决策人，再给路径；用问题夺回节奏，而不是用短词关单。",
    }


def _p1_line(peer_q: str) -> str:
    if re.search(r"(长期|合作|代理|渠道)", peer_q):
        return "可以谈长期。你先说月量和结算方式，我按量给你结构价。"
    if re.search(r"(项目|搞定|能不能)", peer_q):
        return "能做的前提我先核三件事：规模、时效、谁拍板。你按这三项回我。"
    if re.search(r"(量|批发|放量|上量)", peer_q):
        return "量我接。先报区间和交付节奏，我给你对应档位，不定口头价。"
    return "这单我接得住。你先把量和预算区间说清，我给你可执行方案。"


def rewrite_p2(peer_q: str, my_q: str) -> dict:
    return {
        "诊断": "资源免费确认式回应：核心资源被定价为「即取即用」，无门槛=廉价。",
        "暴露底牌": _expose(peer_q, my_q),
        "改造话术": _p2_line(peer_q),
        "策略意图": "条件后缀筛选真需求：时效、用途、对等承诺；不给无约束确认。",
    }


def _expose(peer_q: str, my_q: str) -> str:
    hits = RESOURCE.findall(peer_q) or RESOURCE.findall(my_q) or ["核心资源"]
    return f"向对方暴露/确认了「{'、'.join(hits[:3])}」可即时获得，且无需对等承诺。"


def _p2_line(peer_q: str) -> str:
    if re.search(r"(账号|卡号|汇旺)", peer_q):
        return "有，但只对接已确认用途和结算的客户。你先说用途和量，我再开通道。"
    if re.search(r"(额度|渠道|端口|线路)", peer_q):
        return "渠道在，不空口留位。今天有效的话你定意向，我按档位放。"
    if re.search(r"(靓号|号码|会员|Premium)", peer_q):
        return "有现货。你定规格和付款方式，我锁号；不定规格我不预留。"
    return "资源有，不白票。你先确认需求和付款节点，我再给你对接。"


def rewrite_p3(peer_q: str, my_q: str) -> dict:
    return {
        "诊断": "高价值关系事务化：对方给了「人」的信号，你只回了「事」。",
        "错过": "私人纽带、信任复利、转介绍与深度捆绑；对方会转向更懂人情的节点。",
        "改造话术": _p3_line(peer_q),
        "策略意图": "先接住人，再办成事；用一句人情换长期盟友位，而不是一次成交。",
    }


def _p3_line(peer_q: str) -> str:
    if re.search(r"(吃饭|喝)", peer_q):
        return "行，下次你定时间。正事我先给你落稳，饭局咱们另排。"
    if re.search(r"(靠谱|信任|信得过|多亏)", peer_q):
        return "这话我收下。你这边难点先说，我能扛的部分我扛，不能扛的我直说。"
    if re.search(r"(太难|压力|不容易|心情)", peer_q):
        return "这段确实难熬。事上我帮你把能定的先定住，你别一个人扛。"
    return "我听到了。事先办稳，你要是需要人搭把手，直接说。"


def build_handbook(scan_result: dict) -> str:
    lines = [
        "# 《高价值对话改造手册》",
        "",
        "> 角色：高价值机会审计官  ",
        f"> 扫描会话数：{scan_result['scanned_chats']}  ",
        f"> 检出：模式一 {scan_result['counts']['p1']} / 模式二 {scan_result['counts']['p2']} / 模式三 {scan_result['counts']['p3']}  ",
        f"> 生成时间：{scan_result['updated_at']}",
        "",
        "原则：罪证引用「我」的原话；改造话术 15–30 字短句；先夺节奏，再交付。",
        "",
        "---",
        "",
        "## 模式一：价值归零式回应",
        "",
        "**病症**：对方抛出高价值试探时，用「好的/可以/没问题/稍等」瞬间闭环，战略降级为事务。",
        "",
    ]

    cases1 = scan_result["pattern1"][:5]
    if len(cases1) < 3:
        # keep whatever we have
        pass
    for i, c in enumerate(cases1[:5], 1):
        rw = rewrite_p1(c["peer_quote"], c["my_quote"])
        lines += [
            f"### 场景 1.{i} · {c['name']}（`{c['peer_id']}`）· {c.get('date') or ''}",
            "",
            f"**对方原话**：",
            f"> {c['peer_quote']}",
            "",
            f"**我的原话（罪证）**：",
            f"> {c['my_quote']}",
            "",
            f"**机会信号**：{', '.join(c.get('opp_hits') or [])}",
            "",
            f"**问题诊断**：{rw['诊断']}",
            "",
            f"**我错失了什么**：{rw['错失']}",
            "",
            f"**改造后的标准话术**：",
            f"> {rw['改造话术']}",
            "",
            f"**话术背后的策略意图**：{rw['策略意图']}",
            "",
        ]

    lines += [
        "---",
        "",
        "## 模式二：资源免费确认式回应",
        "",
        "**病症**：核心资源被快速确认/放出，无门槛、无时效、无对等条件。",
        "",
    ]
    for i, c in enumerate(scan_result["pattern2"][:5], 1):
        rw = rewrite_p2(c["peer_quote"], c["my_quote"])
        lines += [
            f"### 场景 2.{i} · {c['name']}（`{c['peer_id']}`）· {c.get('date') or ''}",
            "",
            f"**对方原话**：",
            f"> {c['peer_quote']}",
            "",
            f"**我的原话（罪证）**：",
            f"> {c['my_quote']}",
            "",
            f"**资源信号**：{', '.join(c.get('res_hits') or [])}",
            "",
            f"**问题诊断**：{rw['诊断']}",
            "",
            f"**我暴露了什么**：{rw['暴露底牌']}",
            "",
            f"**改造后的标准话术（条件后缀）**：",
            f"> {rw['改造话术']}",
            "",
            f"**话术背后的策略意图**：{rw['策略意图']}",
            "",
        ]

    lines += [
        "---",
        "",
        "## 模式三：高价值关系事务化",
        "",
        "**病症**：对方示好/诉苦/邀约时，只处理业务流水，只有「事」没有「人」。",
        "",
    ]
    for i, c in enumerate(scan_result["pattern3"][:5], 1):
        rw = rewrite_p3(c["peer_quote"], c["my_quote"])
        lines += [
            f"### 场景 3.{i} · {c['name']}（`{c['peer_id']}`）· {c.get('date') or ''}",
            "",
            f"**对方原话**：",
            f"> {c['peer_quote']}",
            "",
            f"**我的原话（罪证）**：",
            f"> {c['my_quote']}",
            "",
            f"**关系信号**：{', '.join(c.get('rel_hits') or [])}",
            "",
            f"**问题诊断**：{rw['诊断']}",
            "",
            f"**我错过了什么**：{rw['错过']}",
            "",
            f"**改造后的标准话术**：",
            f"> {rw['改造话术']}",
            "",
            f"**话术背后的策略意图**：{rw['策略意图']}",
            "",
        ]

    # summary based on counts
    counts = scan_result["counts"]
    worst = max(counts, key=lambda k: counts[k])
    label = {
        "p1": "价值归零式回应——把「长期/放量/项目」瞬间压成事务确认，损失最大的是议价权与项目入场券",
        "p2": "资源免费确认——核心资源无门槛放出，损失最大的是稀缺定价权与真假客户筛选",
        "p3": "高价值关系事务化——忽略示好与信任信号，损失最大的是盟友级人脉与转介绍复利",
    }[worst]

    lines += [
        "---",
        "",
        "## 标准改造公式（可背）",
        "",
        "| 杀手模式 | 公式 |",
        "|----------|------|",
        "| 价值归零 | **确认可做 + 反问规模/决策人 + 给下一步** |",
        "| 资源免费 | **有/能 + 条件后缀（用途/量/付款/时效）** |",
        "| 关系事务化 | **先接住人（1句）+ 再办成事（1句）** |",
        "",
        "## 一句话总结",
        "",
        f"**我损失最大的一类机会是：{label}。**",
        "",
        "---",
        "",
        "## 附录：扫描统计",
        "",
        f"- 模式一检出条数：{counts['p1']}",
        f"- 模式二检出条数：{counts['p2']}",
        f"- 模式三检出条数：{counts['p3']}",
        "",
        "说明：规则扫描全库；手册正文按得分与 peer 去重选取典型场景。原话未润色。",
        "",
    ]
    return "\n".join(lines)


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-chats", type=int, default=0, help="0=全量")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = scan(args.limit_chats)
    (OUT_DIR / "opportunity_killers_raw.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md = build_handbook(result)
    out_md = OUT_DIR / "高价值对话改造手册.md"
    out_md.write_text(md, encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "counts": result["counts"],
                "scanned": result["scanned_chats"],
                "handbook": str(out_md),
                "top": {
                    "p1": len(result["pattern1"]),
                    "p2": len(result["pattern2"]),
                    "p3": len(result["pattern3"]),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
