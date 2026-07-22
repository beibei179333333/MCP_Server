#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""高净值交易漏损审计：类型 A/B/C → 结构化样本（按严重度排序）。"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

SELF_ID = "1335016610"
CHAT_DIR = Path("/Users/home/Downloads/tg_private_4y_monthly/00_raw_origin")
OUT_DIR = Path(__file__).resolve().parent / "reports" / "leakage_audit"

# --- signals ---
INTENT_A = re.compile(
    r"(量很大|量大|一天量|长期|合作|项目|渠道|对接|搞一笔|有没有办法|"
    r"介绍客户|给你介绍|批发|带量|放量|稳定拿|能不能搞定|有个项目)",
    re.I,
)
ASK_B = re.compile(
    r"(账号|卡号|汇旺|价格|多少钱|什么价|报价|额度|号码|靓号|发我|给我|"
    r"有没有|发一个|挑个|频道|链接)",
    re.I,
)
RESOURCE_HINT = re.compile(
    r"(账号|卡号|汇旺|价格|价|额度|号码|靓号|码|渠道|库存)",
    re.I,
)
EMO_C = re.compile(
    r"(难啊|太难了|累了|还是你靠谱|你靠谱|下次聚|一起吃饭|最近烦|"
    r"欠你个人情|压力大|不容易|帮大忙|多亏你|兄弟价|资金不足)",
    re.I,
)

SHORT_CONFIRM = re.compile(
    r"^(好的?|可以|没问题|稍等|嗯+|哦+|行|ok|OK|收到|在|有|好|1|嗯嗯|"
    r"可以的|没问题的|稍等一下|等下|好哒|好了|好了已经)[\s。.!！~～]*$",
    re.I,
)
HAS_COUNTER = re.compile(
    r"([?？]|多少|怎么|哪|谁|先|需要|预算|量|条件|下一步|你报|你说|"
    r"区间|规格|定金|付款|时效|今天)",
    re.I,
)
HAS_CONDITION = re.compile(
    r"(有效|今天|时效|前提|条件|先付|定金|打款|付款后|用途|保密|"
    r"别外传|锁号|锁|意向|回款|对等|互惠|货到付款除外)",
    re.I,
)
TEMPLATE = re.compile(
    r"(自动回复|人工坐席|小本生意|哈喽！感谢|点击蓝色|正在转接)",
)
AD_SPAM = re.compile(
    r"(官方蓝V|戒赌机器人|私信全网|系统将立即开始处理| #\w+ #\w+ #\w+)",
)
EMO_ACK = re.compile(
    r"(吃饭|聚|理解|不容易|靠谱|难|累|烦|压力|人情|下次|保重|辛苦|哈哈收到)",
    re.I,
)
BIZ_ONLY = re.compile(
    r"(多少钱|价格|开通|办理|链接|地址|汇旺|USDT|会员|号码|好了|已开|"
    r"发你|看下|/menu|报价|卡|钱|赊账|淘宝)",
    re.I,
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


def is_ad(t: str) -> bool:
    if AD_SPAM.search(t):
        return True
    if t.count("\n") >= 8 and len(t) > 400:
        return True
    if t.count("USD") >= 3 and len(t) > 300:
        return True
    return False


def load_chat(path: Path) -> tuple[str, str, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    peer = str(data.get("id") or path.stem.replace("chat_", ""))
    name = str(data.get("name") or peer)
    msgs = []
    for m in data.get("messages") or []:
        if m.get("type") not in (None, "message"):
            continue
        t = text_of(m)
        if not t:
            continue
        msgs.append(
            {
                "id": m.get("id"),
                "from_id": from_id(m),
                "text": t,
                "date": m.get("date"),
            }
        )
    return peer, name, msgs


def next_self_within(msgs: list[dict], i: int, n: int = 3) -> list[dict]:
    """接下来最多看 n 条「我方」消息（中间可夹对方短插话则中断计数逻辑按我方条数）。"""
    out = []
    for j in range(i + 1, len(msgs)):
        m = msgs[j]
        if str(m["from_id"]) != str(SELF_ID):
            if out:
                # 对方又开口：仍允许继续找我方，但不超过窗口消息跨度
                if j - i > 8:
                    break
            continue
        if TEMPLATE.search(m["text"]):
            continue
        out.append(m)
        if len(out) >= n:
            break
    return out


def first_self(msgs: list[dict], i: int) -> dict | None:
    for j in range(i + 1, min(i + 8, len(msgs))):
        m = msgs[j]
        if str(m["from_id"]) != str(SELF_ID):
            continue
        if TEMPLATE.search(m["text"]):
            continue
        return m
    return None


def corrected_a(peer_t: str) -> str:
    if re.search(r"介绍", peer_t):
        return "介绍我收。客户要什么、预算多少，你先说，我优先排。"
    if re.search(r"(量|批发|渠道)", peer_t):
        return "量我接。你报日量区间，我按量给两档价，今天有效。"
    if re.search(r"(项目|合作|长期|对接|搞一笔)", peer_t):
        return "能谈。你先说规模和谁拍板，我给你可执行下一步。"
    return "可以往下走。你先把关键条件和量说清，我再给你路径。"


def corrected_b(peer_t: str) -> str:
    if re.search(r"(靓号|号码|码)", peer_t):
        return "有现货。你定规律和预算，我锁号；不定规不预留，今天有效。"
    if re.search(r"(汇旺|账号|卡号)", peer_t):
        return "账号我发。先确认用途和结算节点；仅本次有效，勿外传。"
    if re.search(r"(价格|多少钱|报价)", peer_t):
        return "价按量走。你报量级，我给对应档；口头价今天有效。"
    if re.search(r"额度", peer_t):
        return "额度可开。先定用途和回款节奏，我对等放量。"
    return "资源有。你先确认需求和付款节点，我再对接；附使用条件。"


def corrected_c(peer_t: str) -> str:
    if re.search(r"(吃饭|聚)", peer_t):
        return "行，你定时间。正事我先给你稳住，聚另排。"
    if re.search(r"(靠谱|人情|多亏|帮大忙)", peer_t):
        return "这话我收下。你难点先说，我能扛的扛，不能扛的直说。"
    if re.search(r"(难|累|烦|压力|资金不足)", peer_t):
        return "这段确实紧。事上我帮你把能定的先定住，你别一个人扛。"
    return "我听到了。先把人安住，事我按能做的部分推进。"


def severity_a(peer_t: str, my_t: str) -> int:
    s = 50
    for w, pts in [
        ("介绍", 25),
        ("量", 20),
        ("批发", 18),
        ("渠道", 15),
        ("长期", 15),
        ("项目", 15),
        ("合作", 12),
        ("搞一笔", 20),
        ("对接", 10),
    ]:
        if w in peer_t:
            s += pts
    if my_t.strip() in {"好", "1", "嗯", "在", "有", "行"}:
        s += 10
    if "稍等" in my_t:
        s += 8
    return s


def severity_b(peer_t: str, my_t: str) -> int:
    s = 55
    if re.search(r"(\d{7,}[\s\S]*){3,}", my_t):
        s += 30  # inventory dump
    if re.search(r"https?://", my_t):
        s += 15  # full channel
    if re.search(r"(货到付款)", my_t):
        s += 12
    if SHORT_CONFIRM.match(my_t) and RESOURCE_HINT.search(peer_t):
        s += 18
    if re.search(r"(汇旺|账号|卡号|靓号|号码|额度)", peer_t):
        s += 10
    return s


def severity_c(peer_t: str, my_t: str) -> int:
    s = 48
    for w, pts in [
        ("一起吃饭", 22),
        ("下次聚", 20),
        ("靠谱", 18),
        ("人情", 16),
        ("太难了", 14),
        ("难啊", 14),
        ("累了", 12),
        ("最近烦", 12),
        ("兄弟价", 15),
        ("资金不足", 12),
    ]:
        if w in peer_t:
            s += pts
    if SHORT_CONFIRM.match(my_t) or char_len(my_t) <= 6:
        s += 8
    if BIZ_ONLY.search(my_t):
        s += 10
    return s


def scan() -> list[dict]:
    samples: list[dict] = []
    paths = sorted(CHAT_DIR.glob("chat_*.json"))

    for path in paths:
        try:
            peer, name, msgs = load_chat(path)
        except Exception:
            continue
        dialog_base = f"peer_{peer}"

        for i, m in enumerate(msgs):
            if str(m["from_id"]) == str(SELF_ID):
                continue
            pt = m["text"]
            if TEMPLATE.search(pt) or is_ad(pt) or len(pt) > 500:
                continue

            # ---- Type A ----
            if INTENT_A.search(pt) and len(pt) < 320:
                selves = next_self_within(msgs, i, n=3)
                leak = None
                for sm in selves:
                    if char_len(sm["text"]) <= 5 and SHORT_CONFIRM.match(sm["text"]):
                        if not HAS_COUNTER.search(sm["text"]):
                            leak = sm
                            break
                    # 若前几条已有反问/条件，则不算漏损
                    if HAS_COUNTER.search(sm["text"]) and char_len(sm["text"]) > 5:
                        leak = None
                        break
                if leak:
                    sev = severity_a(pt, leak["text"])
                    samples.append(
                        {
                            "type": "A",
                            "dialog_id": f"{dialog_base}_msg{m.get('id')}",
                            "peer_id": peer,
                            "peer_name": name,
                            "date": m.get("date"),
                            "context": [f"对方说：{pt[:180]}", f"我说：{leak['text']}"],
                            "loss_summary": "意图信号出现后用短确认关单，错失反问/条件/下一步掌控权。",
                            "corrected_response": corrected_a(pt),
                            "severity": sev,
                            "meta": {
                                "peer_signal": INTENT_A.findall(pt)[:5],
                                "leak_reply": leak["text"],
                            },
                        }
                    )

            # ---- Type B ----
            if ASK_B.search(pt) and RESOURCE_HINT.search(pt) and len(pt) < 200:
                sm = first_self(msgs, i)
                if not sm:
                    continue
                mt = sm["text"]
                gives_info = bool(
                    re.search(
                        r"(https?://|\d{6,}|选号频道|@\w+|汇旺\s*\d|账号|卡号|\$\s*\d|\d+\s*U)",
                        mt,
                        re.I,
                    )
                ) or (SHORT_CONFIRM.match(mt) and re.search(r"(有|可以|能)", mt))
                # 直接给具体信息
                concrete = bool(
                    re.search(r"(https?://|\d{7,}|选号频道|@\w{3,})", mt)
                ) or (
                    SHORT_CONFIRM.match(mt)
                    and re.search(r"(靓号|号码|账号|汇旺|价格|多少钱)", pt)
                )
                if not (gives_info or concrete):
                    continue
                if HAS_CONDITION.search(mt):
                    continue
                # 排除纯拒绝
                if re.fullmatch(r"没有[!！.。]*", mt.strip()):
                    continue
                sev = severity_b(pt, mt)
                ask_what = "、".join(dict.fromkeys(RESOURCE_HINT.findall(pt))) or "资源"
                samples.append(
                    {
                        "type": "B",
                        "dialog_id": f"{dialog_base}_msg{m.get('id')}",
                        "peer_id": peer,
                        "peer_name": name,
                        "date": m.get("date"),
                        "context": [f"对方说：{pt[:180]}", f"我说：{mt[:220]}"],
                        "loss_summary": f"无条件释放「{ask_what}」相关信息，暴露底牌且无筛选。",
                        "corrected_response": corrected_b(pt),
                        "severity": sev,
                        "meta": {"ask": ask_what, "has_link_or_list": bool(re.search(r"https?://|\d{7,}", mt))},
                    }
                )

            # ---- Type C ----
            if EMO_C.search(pt) and len(pt) < 280:
                sm = first_self(msgs, i)
                if not sm:
                    continue
                mt = sm["text"]
                if EMO_ACK.search(mt) and not (
                    BIZ_ONLY.search(mt) and not re.search(r"(理解|不容易|难|累|吃饭|聚)", mt)
                ):
                    # 有情绪承接则跳过（除非完全业务）
                    if re.search(r"(理解|不容易|吃饭|聚|靠谱这话|人情)", mt):
                        continue
                # 无视：短确认 / 纯业务 / 跳转自己话题
                ignored = (
                    SHORT_CONFIRM.match(mt)
                    or (BIZ_ONLY.search(mt) and not EMO_ACK.search(mt))
                    or (
                        char_len(mt) <= 18
                        and not EMO_ACK.search(mt)
                        and not re.search(r"(理解|听到|知道了你)", mt)
                    )
                )
                # 自己吐槽抢戏也算无视
                if re.search(r"(我也不|我这边|这两天碰|我就图)", mt) and not re.search(
                    r"(你|理解你|确实难)", mt
                ):
                    ignored = True
                if not ignored:
                    continue
                sev = severity_c(pt, mt)
                sig = "、".join(dict.fromkeys(EMO_C.findall(pt))) or "情感信号"
                samples.append(
                    {
                        "type": "C",
                        "dialog_id": f"{dialog_base}_msg{m.get('id')}",
                        "peer_id": peer,
                        "peer_name": name,
                        "date": m.get("date"),
                        "context": [f"对方说：{pt[:180]}", f"我说：{mt[:220]}"],
                        "loss_summary": f"忽略「{sig}」，关系未能从客户升级为盟友。",
                        "corrected_response": corrected_c(pt),
                        "severity": sev,
                        "meta": {"emotion_signal": sig},
                    }
                )

    # diversify: keep best per (type, peer_id), then global sort
    best: dict[tuple[str, str], dict] = {}
    for s in samples:
        key = (s["type"], s["peer_id"])
        if key not in best or s["severity"] > best[key]["severity"]:
            best[key] = s
    ranked = sorted(best.values(), key=lambda x: -x["severity"])
    return ranked, samples, len(paths)


def to_delivery_obj(s: dict) -> dict:
    return {
        "type": s["type"],
        "dialog_id": s["dialog_id"],
        "context": s["context"],
        "loss_summary": s["loss_summary"],
        "corrected_response": s["corrected_response"],
        "severity": s["severity"],
        "peer_name": s.get("peer_name"),
        "date": s.get("date"),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ranked, raw, n_chats = scan()
    top = [to_delivery_obj(s) for s in ranked[:40]]
    # ensure >=20 and mix types if possible
    if len(top) < 20:
        # fallback: allow same peer different types already in ranked
        pass

    report = {
        "role": "高净值交易漏损审计师",
        "scanned_chats": n_chats,
        "raw_hits": len(raw),
        "unique_peer_type_hits": len(ranked),
        "type_counts_unique": {
            "A": sum(1 for s in ranked if s["type"] == "A"),
            "B": sum(1 for s in ranked if s["type"] == "B"),
            "C": sum(1 for s in ranked if s["type"] == "C"),
        },
        "delivered": len(top),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "samples": top,
    }

    out_json = OUT_DIR / "leakage_samples.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # markdown view of top 20+
    lines = [
        "# 高净值交易漏损审计报告",
        "",
        f"- 扫描会话：{n_chats}",
        f"- 初筛命中：{len(raw)}",
        f"- peer×类型去重后：{len(ranked)}（A={report['type_counts_unique']['A']} / B={report['type_counts_unique']['B']} / C={report['type_counts_unique']['C']}）",
        f"- 交付样本：{len(top)}（按 severity 降序）",
        f"- 生成时间：{report['updated_at']}",
        "",
        "---",
        "",
    ]
    for i, s in enumerate(top[:25], 1):
        lines += [
            f"## #{i} · 类型{s['type']} · severity={s['severity']}",
            "",
            f"- dialog_id: `{s['dialog_id']}`",
            f"- 对象: {s.get('peer_name')} · {s.get('date') or ''}",
            "",
            "```json",
            json.dumps(
                {
                    "type": s["type"],
                    "dialog_id": s["dialog_id"],
                    "context": s["context"],
                    "loss_summary": s["loss_summary"],
                    "corrected_response": s["corrected_response"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
        ]
    (OUT_DIR / "leakage_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "scanned": n_chats,
                "raw_hits": len(raw),
                "unique": len(ranked),
                "delivered": len(top),
                "type_counts": report["type_counts_unique"],
                "top_types": [s["type"] for s in top[:20]],
                "out_json": str(out_json),
                "out_md": str(OUT_DIR / "leakage_report.md"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
