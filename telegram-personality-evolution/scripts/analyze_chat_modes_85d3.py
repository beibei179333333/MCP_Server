#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析流程：自动判断模式 A/B/C 并生成结构化报告。

模式 A — 客户/白嫖分析
模式 B — 朋友/社交分析
模式 C — 自我沟通画像

原则：先分类后分析；证据驱动；事实/推断分离；行动导向。
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SELF_USER_ID = "1335016610"
SKILL = Path(__file__).resolve().parent
DEFAULT_CHAT_DIR = Path("/Users/home/Downloads/tg_private_4y_monthly/00_raw_origin")

# ---------- 特征词典 ----------

A_PRICE = re.compile(
    r"(多少钱|什么价|报价|价格|费用|收费|便宜|打折|优惠|免费|白嫖|试用|"
    r"先做|帮我看|帮忙|方案|怎么买|怎么开|开通|代开|会员)",
    re.I,
)
A_PRESSURE = re.compile(
    r"(朋友吗|就这点忙|不就|随便做|很快的|能不能先|先试试|回头再|"
    r"考虑一下|再看看|太贵|能不能便宜|给个面子)",
    re.I,
)
B_SOCIAL = re.compile(
    r"(在吗|忙吗|吃了吗|晚安|早安|哈哈|哈哈哈|嗯嗯|想你|心情|"
    r"最近怎样|聊聊|没事|无聊|朋友|网友)",
    re.I,
)
B_EMO = re.compile(r"(难过|开心|生气|烦|累|焦虑|委屈|开心|郁闷|想吐槽)", re.I)

TRAP_TAGS = [
    ("索取价值", re.compile(r"(多少钱|报价|价格|费用|免费|帮忙|帮我)")),
    ("情绪施压", re.compile(r"(朋友|就这点|随便|不就|给个面子)")),
    ("道德绑架", re.compile(r"(不够意思|不帮|太绝情|怎么这样)")),
    ("降低报价", re.compile(r"(太贵|便宜点|打折|优惠|能不能少)")),
    ("无限咨询", re.compile(r"(再问|还有个|顺便问|再帮我看|怎么操作)")),
    ("免费试错", re.compile(r"(先试试|试用|先做|不满意再说|先帮)")),
    ("拖延成交", re.compile(r"(回头|再考虑|等等|过两天|先看看)")),
]

STOPLOSS_SELF = [
    ("免费咨询", re.compile(r"(可以先|我跟你说下|流程是|大概是这样|你先了解)")),
    ("免费劳动", re.compile(r"(我帮你(?!备注)|我给你做|我来弄|我发你方案|我整理一份)")),
    ("无限解释", re.compile(r"(所以说|其实是这样|我再解释|你听我说|我详细说一下)")),
    ("被动证明自己", re.compile(r"(我们是正规|我不是骗子|绝对不是骗子|我保证真的)")),
    ("被拖时间", re.compile(r"(你慢慢看|不急哈|随时问我|有问题再说)")),
]
_TEMPLATE_SKIP = re.compile(
    r"(自动回复|人工坐席|哈喽！感谢您的联系|小本生意|正在转接|点击蓝色字体)"
)

CONTENT_TYPES = [
    ("解决问题", re.compile(r"(怎么|如何|解决|处理|步骤|操作|开通|失败|报错)")),
    ("情绪表达", re.compile(r"(烦|累|开心|难过|生气|郁闷|无语|服了)")),
    ("信息分享", re.compile(r"(链接|地址|这个|发给你|看看这个|最新)")),
    ("吐槽", re.compile(r"(坑|垃圾|离谱|无语|服了|吐槽)")),
    ("寒暄", re.compile(r"(在吗|忙吗|你好|晚安|早安|哈哈|嗯|好的)")),
    ("敷衍", re.compile(r"^(嗯+|哦+|好的?|行|ok|知道了|收到)[\s。.!！]*$", re.I)),
]

FILLERS = ["其实", "感觉", "可以", "哈哈", "嗯", "那个", "就是", "然后", "不过", "可能"]
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F9FF"
    "\U00002600-\U000027BF"
    "\U0001FA00-\U0001FAFF"
    "]+"
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


def from_id_of(m: dict) -> str:
    fid = m.get("from_id")
    if fid is None:
        return ""
    s = str(fid)
    return s.replace("user", "") if s.startswith("user") else s


def parse_ts(m: dict) -> float | None:
    u = m.get("date_unixtime")
    if u is not None:
        try:
            return float(u)
        except (TypeError, ValueError):
            pass
    d = m.get("date")
    if not d:
        return None
    try:
        return datetime.fromisoformat(str(d).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def load_chat(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    msgs = []
    for m in data.get("messages") or []:
        if m.get("type") and m.get("type") != "message":
            continue
        txt = text_of(m)
        if not txt and not m.get("sticker_emoji"):
            continue
        msgs.append(
            {
                "id": m.get("id"),
                "from_id": from_id_of(m),
                "from": m.get("from"),
                "date": m.get("date"),
                "ts": parse_ts(m),
                "text": txt or str(m.get("sticker_emoji") or ""),
                "raw": m,
            }
        )
    peer_id = str(data.get("id") or path.stem.replace("chat_", ""))
    return {
        "peer_id": peer_id,
        "name": data.get("name"),
        "type": data.get("type"),
        "messages": msgs,
        "path": str(path),
    }


def split_sides(msgs: list[dict], self_id: str) -> tuple[list[dict], list[dict]]:
    me, peer = [], []
    for m in msgs:
        if str(m["from_id"]) == str(self_id):
            me.append(m)
        else:
            peer.append(m)
    return me, peer


# ---------- 模式判定 ----------

def score_mode_signals(msgs: list[dict], self_id: str, *, force_c: bool = False) -> dict:
    if force_c:
        return {
            "mode": "C",
            "scores": {"A": 0.0, "B": 0.0, "C": 1.0},
            "reasons": ["输入标记为自我语料 / 训练数据集 / 非双边对谈画像"],
            "borderline": False,
        }

    peer_texts = []
    self_texts = []
    for m in msgs:
        t = m["text"]
        if str(m["from_id"]) == str(self_id):
            self_texts.append(t)
        else:
            peer_texts.append(t)

    all_peer = "\n".join(peer_texts)
    all_self = "\n".join(self_texts)
    all_txt = all_peer + "\n" + all_self

    a = 0.0
    b = 0.0
    reasons_a: list[str] = []
    reasons_b: list[str] = []

    ap = len(A_PRICE.findall(all_peer))
    as_ = len(A_PRESSURE.findall(all_peer))
    a += ap * 1.2 + as_ * 1.5
    if ap:
        reasons_a.append(f"对方出现询价/方案/免费类话术 {ap} 次")
    if as_:
        reasons_a.append(f"对方出现议价/施压/拖延话术 {as_} 次")

    # 我方商务模板也推高 A（客服场景）
    if re.search(r"(自动回复|收款|开通|会员|报价|小本生意)", all_self):
        a += 2.0
        reasons_a.append("我方话术含商务/客服特征")

    bs = len(B_SOCIAL.findall(all_txt))
    be = len(B_EMO.findall(all_txt))
    b += bs * 1.0 + be * 1.3
    if bs:
        reasons_b.append(f"社交寒暄类话术 {bs} 次")
    if be:
        reasons_b.append(f"情绪交流类话术 {be} 次")

    # 双边且几乎无商务 → 抬高 B
    if peer_texts and self_texts and a < 2 and b >= 1:
        b += 1.5

    # 单边占比极高且消息量大 → 倾向 C（导出偏自我）
    n = len(msgs)
    n_self = len(self_texts)
    c = 0.0
    reasons_c: list[str] = []
    if n >= 30 and n_self / max(n, 1) >= 0.92:
        c = 3.0
        reasons_c.append("几乎全是同一人发言（≥92%），更像自我语料")
    if not peer_texts and self_texts:
        c = 5.0
        reasons_c.append("无对方发言，仅有单侧文本")

    scores = {"A": round(a, 2), "B": round(b, 2), "C": round(c, 2)}
    # 选最高；C 需明显才抢
    mode = max(scores, key=lambda k: scores[k])
    if scores["C"] < 2.5 and mode == "C":
        mode = "A" if scores["A"] >= scores["B"] else "B"
    if scores["A"] == 0 and scores["B"] == 0 and scores["C"] < 2.5:
        mode = "B"
        reasons_b.append("无明显商务特征，默认社交关系分析")

    top2 = sorted(scores.values(), reverse=True)
    borderline = len(top2) >= 2 and top2[0] > 0 and (top2[0] - top2[1]) < 1.5 and mode != "C"

    reasons = {
        "A": reasons_a or ["商务特征弱"],
        "B": reasons_b or ["社交特征弱"],
        "C": reasons_c or ["非自我语料结构"],
    }
    return {
        "mode": mode,
        "scores": scores,
        "reasons": reasons[mode],
        "all_reasons": reasons,
        "borderline": borderline,
    }


# ---------- 模式 A ----------

def analyze_mode_a(chat: dict, self_id: str) -> dict:
    msgs = chat["messages"]
    me, peer = split_sides(msgs, self_id)
    traps: list[dict] = []
    for m in peer:
        t = m["text"]
        for tag, rx in TRAP_TAGS:
            if rx.search(t):
                traps.append(
                    {
                        "quote": t[:120],
                        "purpose": _infer_purpose(tag, t),
                        "tag": tag,
                        "date": m.get("date"),
                        "confidence": "中" if len(t) < 8 else "高",
                        "fact_or_inference": "事实=出现关键词；推断=动机标签",
                    }
                )
                break

    # 白嫖指数
    trap_n = len(traps)
    free_n = sum(1 for x in traps if x["tag"] in ("索取价值", "免费试错", "无限咨询"))
    delay_n = sum(1 for x in traps if x["tag"] in ("拖延成交", "降低报价", "情绪施压", "道德绑架"))
    if free_n >= 3 or (free_n >= 2 and delay_n >= 2):
        level = "高危"
    elif free_n >= 1 or delay_n >= 1 or trap_n >= 2:
        level = "中等"
    else:
        level = "暂无"

    reasons = []
    if free_n:
        reasons.append(f"检测到免费/索取/无限咨询信号 {free_n} 条")
    if delay_n:
        reasons.append(f"检测到压价/拖延/施压信号 {delay_n} 条")
    if not reasons:
        reasons.append("对方未出现明显白嫖套路关键词（仍建议看整体成交意愿）")

    # 止损：我方哪些回复踩线（跳过客服模板群发）
    stoploss: list[dict] = []
    for m in me:
        t = m["text"]
        if _TEMPLATE_SKIP.search(t):
            continue
        for label, rx in STOPLOSS_SELF:
            if rx.search(t) and len(t) > 6:
                stoploss.append(
                    {
                        "label": label,
                        "quote": t[:140],
                        "date": m.get("date"),
                    }
                )
                break

    # 主动权丢失点：首次连续对方索取 + 我方长解释
    lost_at = None
    for i, m in enumerate(msgs):
        if str(m["from_id"]) == str(self_id):
            continue
        if not A_PRICE.search(m["text"]) and not A_PRESSURE.search(m["text"]):
            continue
        # 找之后我方第一条长回复
        for j in range(i + 1, min(i + 6, len(msgs))):
            nm = msgs[j]
            if str(nm["from_id"]) != str(self_id):
                continue
            if len(nm["text"]) >= 40 or any(rx.search(nm["text"]) for _, rx in STOPLOSS_SELF):
                lost_at = {
                    "trigger_quote": m["text"][:120],
                    "self_quote": nm["text"][:140],
                    "date": nm.get("date"),
                    "note": "从此处起，对方提问/施压后我方进入长解释或免费交付姿态",
                }
                break
        if lost_at:
            break

    arsenal = {
        "温柔防守": {
            "lines": [
                "可以，先说你要办哪一项。",
                "价格按页上的来，我按流程开。",
                "要落地的话我直接给你下单链接。",
            ],
            "scene": "对方试探、闲聊式询价，关系还想留着",
        },
        "价值锚定": {
            "lines": [
                "免费只能答一句范围，细节走单。",
                "方案是付费服务，确认预算再说细。",
                "我时间按单算，不定制口头方案。",
            ],
            "scene": "对方无限追问细节、要完整方案但不下单",
        },
        "反向逼单": {
            "lines": [
                "你要现在开还是先放着？",
                "预算到位我马上办，不到位先停这儿。",
                "今天能定我优先排，不定也没事。",
            ],
            "scene": "拖延成交、反复「再看看」、占用客服时段",
        },
    }

    return {
        "mode": "A",
        "白嫖指数": {"level": level, "reasons": reasons},
        "套路拆解": traps[:20],
        "止损红线": {
            "踩线回复": stoploss[:15],
            "主动权丢失点": lost_at,
            "categories_hit": sorted({s["label"] for s in stoploss}),
        },
        "反制转化武器库": arsenal,
    }


def _infer_purpose(tag: str, text: str) -> str:
    mapping = {
        "索取价值": "想不付钱或少付钱拿到信息/服务。",
        "情绪施压": "用关系或情绪推动你让步。",
        "道德绑架": "把拒绝描述成「不够意思」。",
        "降低报价": "把谈判焦点压到价格而非成交。",
        "无限咨询": "用连续提问消耗你的时间。",
        "免费试错": "把风险甩给你，自己零成本试。",
        "拖延成交": "占住你的注意力却不推进付款。",
    }
    return mapping.get(tag, "试探或消耗资源。") + f"（依据：含相关表述）"


# ---------- 模式 B ----------

def analyze_mode_b(chat: dict, self_id: str) -> dict:
    msgs = chat["messages"]
    me, peer = split_sides(msgs, self_id)
    n_me, n_peer = len(me), len(peer)
    total = max(n_me + n_peer, 1)
    init_me = _count_initiators(msgs, self_id)

    gaps_me_to_peer: list[float] = []
    gaps_peer_to_me: list[float] = []
    for i in range(1, len(msgs)):
        a, b = msgs[i - 1], msgs[i]
        if a["ts"] is None or b["ts"] is None:
            continue
        dt = b["ts"] - a["ts"]
        if dt < 0 or dt > 86400 * 3:
            continue
        if str(a["from_id"]) == str(self_id) and str(b["from_id"]) != str(self_id):
            gaps_peer_to_me.append(dt)  # peer replied to me
        if str(a["from_id"]) != str(self_id) and str(b["from_id"]) == str(self_id):
            gaps_me_to_peer.append(dt)

    def avg(xs: list[float]) -> str:
        if not xs:
            return "样本不足"
        m = sum(xs) / len(xs)
        if m < 60:
            return f"约 {int(m)} 秒"
        if m < 3600:
            return f"约 {int(m/60)} 分钟"
        return f"约 {m/3600:.1f} 小时"

    # 终结者：最后一条是谁；谁更常发「嗯/好/没事」收束
    ender = "我" if msgs and str(msgs[-1]["from_id"]) == str(self_id) else "对方"
    topic_ctrl = "我" if init_me["me_pct"] >= 60 else ("对方" if init_me["me_pct"] <= 40 else "互有拉扯")

    imbalance = abs(n_me - n_peer) / total
    if n_me / total >= 0.65:
        portrait = "这是一个双方都有联系意愿，但投入明显失衡的关系——我方发起与维持更多。"
    elif n_peer / total >= 0.65:
        portrait = "对方更主动维持联系，我方偏回应型。"
    elif imbalance < 0.15:
        portrait = "双方互动量接近，关系表面平衡，需看情感解码是否同频。"
    else:
        portrait = "联系意愿在，但节奏与话题控制权并不对等。"

    # 情感解码：取有代表性的轮次
    decoded = []
    pairs = _pair_turns(msgs, self_id, limit=12)
    for p in pairs:
        decoded.append(
            {
                "speaker": p["speaker"],
                "quote": p["text"][:100],
                "真正意思": _decode_social(p["text"], p["speaker"]),
                "confidence": "中",
                "fact_or_inference": "事实=原文；推断=意图解读",
            }
        )

    truth = _relation_truth(n_me, n_peer, init_me["me_pct"], gaps_me_to_peer, gaps_peer_to_me)

    return {
        "mode": "B",
        "关系画像": portrait,
        "对话流向图": {
            "发起": {"我": f"{init_me['me_pct']}%", "对方": f"{100 - init_me['me_pct']}%"},
            "消息占比": {"我": round(100 * n_me / total, 1), "对方": round(100 * n_peer / total, 1)},
            "回应速度": {"我回对方": avg(gaps_me_to_peer), "对方回我": avg(gaps_peer_to_me)},
            "终结者": ender,
            "话题控制权": topic_ctrl,
        },
        "情感解码": decoded,
        "关系真相": truth,
        "行动建议": [
            "先停一轮主动发起，看对方会不会找你。",
            "下一句只回事实，不补情绪解释。",
            "若连续三次你收尾，关系投入已经偏你。",
        ],
    }


def _count_initiators(msgs: list[dict], self_id: str) -> dict:
    """会话缝隙 > 2h 视为新发起。"""
    me_i = peer_i = 0
    prev_ts = None
    for m in msgs:
        ts = m["ts"]
        is_new = prev_ts is None or (ts is not None and prev_ts is not None and ts - prev_ts > 7200)
        if is_new:
            if str(m["from_id"]) == str(self_id):
                me_i += 1
            else:
                peer_i += 1
        if ts is not None:
            prev_ts = ts
    tot = max(me_i + peer_i, 1)
    return {"me": me_i, "peer": peer_i, "me_pct": int(round(100 * me_i / tot))}


def _pair_turns(msgs: list[dict], self_id: str, limit: int = 12) -> list[dict]:
    out = []
    for m in msgs:
        t = m["text"].strip()
        if len(t) < 2:
            continue
        speaker = "我" if str(m["from_id"]) == str(self_id) else "对方"
        out.append({"speaker": speaker, "text": t})
        if len(out) >= limit:
            break
    return out


def _decode_social(text: str, speaker: str) -> str:
    t = text.strip()
    if re.search(r"(忙吗|在吗|最近)", t):
        return "想建立或确认联系。"
    if re.fullmatch(r"(还行|还好|嗯+|哦+|哈哈*|没事|随便)[!！.。]*", t):
        return "不愿展开，或在挡话题。"
    if re.search(r"(想你|关心|怎么了)", t):
        return "释放亲近或试探回应。"
    if len(t) <= 4:
        return "低投入回应，维持存在感但不推进。"
    if "?" in t or "？" in t:
        return "用提问拉动对方输出。"
    if speaker == "我" and len(t) > 40:
        return "我方在补信息/解释，可能过度负责。"
    return "维持互动；具体意图需结合前后文。"


def _relation_truth(
    n_me: int,
    n_peer: int,
    me_init_pct: int,
    gaps_me: list[float],
    gaps_peer: list[float],
) -> str:
    if n_me > n_peer * 1.5 and me_init_pct >= 60:
        return "你们的问题不是没有话题，而是双方投入已经不对等。"
    if n_peer > n_me * 1.5:
        return "对方更用力维系；你若持续冷回应，关系会单向消耗对方。"
    avg_me = sum(gaps_me) / len(gaps_me) if gaps_me else None
    avg_peer = sum(gaps_peer) / len(gaps_peer) if gaps_peer else None
    if avg_me and avg_peer and avg_me > avg_peer * 3:
        return "你回得慢、对方回得快：热情不对称，别用忙碌当长期借口。"
    return "表面聊得动，但要看谁在收尾、谁在提问——控制权决定关系走向。"


# ---------- 模式 C ----------

def analyze_mode_c(texts: list[str], *, meta: dict | None = None) -> dict:
    texts = [t for t in texts if t and t.strip()]
    n = max(len(texts), 1)
    type_counts: Counter[str] = Counter()
    for t in texts:
        hit = False
        for name, rx in CONTENT_TYPES:
            if name == "敷衍":
                if rx.match(t.strip()):
                    type_counts[name] += 1
                    hit = True
                    break
            elif rx.search(t):
                type_counts[name] += 1
                hit = True
                break
        if not hit:
            type_counts["信息分享"] += 1  # 默认桶

    dist = {k: round(100 * type_counts.get(k, 0) / n, 1) for k, _ in CONTENT_TYPES}

    # 高频词 / 短语
    word_c: Counter[str] = Counter()
    phrase_c: Counter[str] = Counter()
    filler_c: Counter[str] = Counter()
    for t in texts:
        for f in FILLERS:
            c = t.count(f)
            if c:
                filler_c[f] += c
        # 粗分词：连续中文 2-grams + 英文词
        for w in re.findall(r"[\u4e00-\u9fff]{2,6}|[A-Za-z]{3,}", t):
            if w in ("自动回复", "正在转接", "人工客服"):
                continue
            word_c[w] += 1
        for ph in re.findall(r"[\u4e00-\u9fff]{4,12}", t):
            if len(ph) >= 4:
                phrase_c[ph] += 1

    lengths = [len(re.sub(r"\s+", "", t)) for t in texts]
    avg_len = sum(lengths) / len(lengths) if lengths else 0
    emoji_n = sum(len(EMOJI_RE.findall(t)) for t in texts)
    q_n = sum(t.count("？") + t.count("?") for t in texts)
    excl = sum(t.count("！") + t.count("!") for t in texts)
    ellipsis = sum(t.count("…") + t.count("...") for t in texts)

    style = []
    if avg_len <= 18:
        style.append("短句")
    else:
        style.append("长句偏多" if avg_len > 40 else "中等句长")
    if q_n / n > 0.25:
        style.append("提问驱动")
    if any(re.search(r"(因为|所以|比如|例如|分析)", t) for t in texts[:200]):
        style.append("偏理性/喜欢分析或举例")
    if any(re.search(r"(你先|马上|必须|别|不要)", t) for t in texts[:200]):
        style.append("命令式片段存在")
    if any(re.search(r"(理解|没事|辛苦|抱抱|心疼)", t) for t in texts[:200]):
        style.append("共情型片段存在")
    style.append(f"Emoji约 {emoji_n} 处（全文）")
    style.append(f"叹号 {excl} / 省略 {ellipsis}")

    # 情绪底色
    pos = sum(1 for t in texts if re.search(r"(哈哈|开心|好的|可以|谢谢)", t))
    neg = sum(1 for t in texts if re.search(r"(烦|累|无语|生气|不行)", t))
    if pos > neg * 2:
        mood = "整体偏稳住、推进事务，负向宣泄不多。"
    elif neg > pos:
        mood = "负向表达更醒目，压力或边界被触及时语气变硬。"
    else:
        mood = "情绪起伏中性，事务推进与应付并存。"

    # 角色
    roles = []
    if type_counts["解决问题"] >= type_counts.get("寒暄", 0):
        roles.append("解决问题的人")
    if type_counts["情绪表达"] > n * 0.08:
        roles.append("倾听者/情绪容器（对他人或自述）")
    if any("发给你" in t or "你按这个" in t for t in texts[:300]):
        roles.append("资源提供者")
    if any(re.search(r"(我们|安排|你先做|下一步)", t) for t in texts[:300]):
        roles.append("组织者/教练倾向")
    if not roles:
        roles.append("事务回应者")

    risks = []
    evidence = []
    long_help = sum(1 for t in texts if len(t) > 60 and re.search(r"(你|帮|可以)", t))
    if long_help > n * 0.08:
        risks.append("过度负责")
        evidence.append({"risk": "过度负责", "note": "长文指导/代劳句偏多", "count": long_help})
    soft = sum(1 for t in texts if re.search(r"(不好意思|没事|随便你|都可以)", t))
    if soft > 5:
        risks.append("讨好倾向")
        evidence.append({"risk": "讨好倾向", "quote_hint": "不好意思/都可以 类", "count": soft})
    if sum(1 for t in texts if re.search(r"(算了|不说了|随意)", t)) > 3:
        risks.append("回避冲突")
    if sum(1 for t in texts if re.search(r"(你必须|赶紧|别再)", t)) > 3:
        risks.append("控制欲")
    if sum(1 for t in texts if re.search(r"(你慢慢|随时问|不急)", t)) > 5:
        risks.append("边界感不足")
        evidence.append({"risk": "边界感不足", "note": "开放式随时服务话术"})

    return {
        "mode": "C",
        "meta": meta or {},
        "内容类型分布": dist,
        "高频词": {
            "词": word_c.most_common(25),
            "短语": phrase_c.most_common(15),
            "口头禅与语气词": filler_c.most_common(15),
        },
        "句式风格": style,
        "情绪底色": mood,
        "角色定位": {
            "长期扮演": roles,
            "风险倾向": risks or ["未检出显著风险标签（规则版）"],
            "证据": evidence[:10],
        },
        "样本句数": len(texts),
    }


# ---------- 报告渲染 ----------

def render_markdown(decision: dict, payload: dict, chat: dict | None) -> str:
    lines = [
        f"# 聊天分析报告 · 模式{decision['mode']}",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        "## 模式判定",
        "",
        f"- **判定**：模式 {decision['mode']}",
        f"- **分数**：A={decision['scores']['A']} / B={decision['scores']['B']} / C={decision['scores']['C']}",
        f"- **边界模糊**：{'是' if decision.get('borderline') else '否'}",
        "- **依据**：",
    ]
    for r in decision.get("reasons") or []:
        lines.append(f"  - {r}")
    if chat:
        lines += ["", f"- peer_id：`{chat.get('peer_id')}`", f"- 名称：{chat.get('name')}", f"- 消息数：{len(chat.get('messages') or [])}"]

    lines += ["", "---", ""]

    if decision["mode"] == "A":
        idx = payload["白嫖指数"]
        lines += ["## 一、白嫖指数", "", f"**{idx['level']}**", "", "原因：", ""]
        for r in idx["reasons"]:
            lines.append(f"- {r}")
        lines += ["", "## 二、套路拆解", ""]
        for i, t in enumerate(payload["套路拆解"], 1):
            lines += [
                f"### {i}. {t['tag']}",
                "",
                f"引用：",
                "",
                f"> \"{t['quote']}\"",
                "",
                f"分析：{t['purpose']}",
                "",
                f"属于：{t['tag']}",
                "",
                f"置信度：{t['confidence']}（{t['fact_or_inference']}）",
                "",
            ]
        if not payload["套路拆解"]:
            lines.append("未检出典型套路句（规则关键词版）。")
        sl = payload["止损红线"]
        lines += ["", "## 三、我的止损红线", ""]
        if sl["categories_hit"]:
            lines.append("哪些回复让我进入了：" + "、".join(sl["categories_hit"]))
        else:
            lines.append("未检出明显踩线回复（或我方话术偏模板短句）。")
        lines.append("")
        for s in sl["踩线回复"]:
            lines += [f"- **{s['label']}**：\"{s['quote']}\"", ""]
        lost = sl["主动权丢失点"]
        lines += ["并指出：从哪一句开始，主动权已经丢失。", ""]
        if lost:
            lines += [
                f"- 对方触发：\"{lost['trigger_quote']}\"",
                f"- 我方接住：\"{lost['self_quote']}\"",
                f"- {lost['note']}",
            ]
        else:
            lines.append("- 样本中未定位到清晰的「长解释接盘」拐点。")
        lines += ["", "## 四、反制转化武器库", ""]
        for name, block in payload["反制转化武器库"].items():
            lines += [f"### {name}", "", "适用场景：" + block["scene"], ""]
            for ln in block["lines"]:
                lines.append(f"- {ln}")
            lines.append("")

    elif decision["mode"] == "B":
        lines += ["## 一、关系画像", "", f"一句话总结：", "", f"> {payload['关系画像']}", ""]
        flow = payload["对话流向图"]
        lines += [
            "## 二、对话流向图",
            "",
            f"- 发起：我 {flow['发起']['我']} / 对方 {flow['发起']['对方']}",
            f"- 消息占比：我 {flow['消息占比']['我']}% / 对方 {flow['消息占比']['对方']}%",
            f"- 回应速度：我回对方 {flow['回应速度']['我回对方']}；对方回我 {flow['回应速度']['对方回我']}",
            f"- 终结者：{flow['终结者']}",
            f"- 话题控制权：{flow['话题控制权']}",
            "",
            "## 三、情感解码（逐段引用）",
            "",
        ]
        for i, d in enumerate(payload["情感解码"], 1):
            lines += [
                f"**{d['speaker']}：**",
                "",
                f"> \"{d['quote']}\"",
                "",
                f"真正意思：{d['真正意思']}",
                "",
                f"置信度：{d['confidence']}（{d['fact_or_inference']}）",
                "",
            ]
        lines += ["## 四、关系真相", "", f"> {payload['关系真相']}", "", "## 行动建议", ""]
        for a in payload.get("行动建议") or []:
            lines.append(f"- {a}")

    else:  # C
        lines += ["## 一、内容类型分布", "", "| 类型 | 占比 |", "|------|------|"]
        for k, v in payload["内容类型分布"].items():
            lines.append(f"| {k} | {v}% |")
        hw = payload["高频词"]
        lines += ["", "## 二、高频词", "", "### 高频词", ""]
        for w, c in hw["词"][:20]:
            lines.append(f"- {w} ×{c}")
        lines += ["", "### 高频短语", ""]
        for w, c in hw["短语"][:12]:
            lines.append(f"- {w} ×{c}")
        lines += ["", "### 口头禅 / 语气词", ""]
        for w, c in hw["口头禅与语气词"]:
            lines.append(f"- \"{w}\" ×{c}")
        lines += ["", "## 三、句式风格", ""]
        for s in payload["句式风格"]:
            lines.append(f"- {s}")
        lines += ["", "## 四、情绪底色", "", payload["情绪底色"], "", "## 五、角色定位", ""]
        lines.append("长期扮演：")
        for r in payload["角色定位"]["长期扮演"]:
            lines.append(f"- {r}")
        lines += ["", "进一步分析是否存在：", ""]
        for r in payload["角色定位"]["风险倾向"]:
            lines.append(f"- {r}")
        if payload["角色定位"]["证据"]:
            lines += ["", "证据：", ""]
            for e in payload["角色定位"]["证据"]:
                lines.append(f"- {json.dumps(e, ensure_ascii=False)}")
        lines += ["", f"样本句数：{payload['样本句数']}"]

    lines += [
        "",
        "---",
        "",
        "## 分析原则备忘",
        "",
        "1. 先分类，后分析",
        "2. 证据驱动（上文引用原文）",
        "3. 区分事实与推断，并标注置信度",
        "4. 行动导向（建议/止损/武器库）",
        "",
    ]
    return "\n".join(lines) + "\n"


def collect_self_corpus(chat_dir: Path, self_id: str, limit_chats: int) -> list[str]:
    texts: list[str] = []
    paths = sorted(chat_dir.glob("chat_*.json"))[:limit_chats]
    for p in paths:
        try:
            chat = load_chat(p)
        except Exception:
            continue
        for m in chat["messages"]:
            if str(m["from_id"]) == str(self_id):
                texts.append(m["text"])
    return texts


def run_one(
    chat: dict | None,
    *,
    mode: str | None,
    self_id: str,
    self_texts: list[str] | None = None,
) -> tuple[dict, dict, str]:
    if self_texts is not None:
        decision = score_mode_signals([], self_id, force_c=True)
        if mode and mode != "C":
            decision["mode"] = mode
            decision["reasons"] = [f"强制指定模式 {mode}（自我语料输入）"]
        payload = analyze_mode_c(self_texts, meta={"source": "self_corpus", "n": len(self_texts)})
        md = render_markdown(decision, payload, None)
        return decision, payload, md

    assert chat is not None
    decision = score_mode_signals(chat["messages"], self_id)
    if mode:
        decision["mode"] = mode.upper()
        decision["reasons"] = [f"强制指定模式 {mode.upper()}"] + list(decision.get("reasons") or [])
        decision["borderline"] = False

    m = decision["mode"]
    if m == "A":
        payload = analyze_mode_a(chat, self_id)
    elif m == "B":
        payload = analyze_mode_b(chat, self_id)
    else:
        me, _ = split_sides(chat["messages"], self_id)
        payload = analyze_mode_c([x["text"] for x in me], meta={"peer_id": chat["peer_id"], "side": "self_only_in_dialog"})
    md = render_markdown(decision, payload, chat)
    return decision, payload, md


def main() -> None:
    ap = argparse.ArgumentParser(description="模式 A/B/C 聊天分析")
    ap.add_argument("--chat", default="", help="单个 chat_*.json")
    ap.add_argument("--chat-dir", default=str(DEFAULT_CHAT_DIR))
    ap.add_argument("--mode", choices=["A", "B", "C", "a", "b", "c", ""], default="")
    ap.add_argument("--self-id", default=SELF_USER_ID)
    ap.add_argument("--self-corpus", action="store_true", help="聚合本人发言做模式 C")
    ap.add_argument("--limit-chats", type=int, default=300)
    ap.add_argument("--out-dir", default=str(SKILL / "reports" / "mode_analysis"))
    ap.add_argument("--demo", action="store_true", help="跑 A/B/C 各一例演示")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mode = args.mode.upper() if args.mode else None
    results = []

    if args.self_corpus or (mode == "C" and not args.chat and not args.demo):
        texts = collect_self_corpus(Path(args.chat_dir), args.self_id, args.limit_chats)
        decision, payload, md = run_one(None, mode="C", self_id=args.self_id, self_texts=texts)
        stem = "self_corpus_mode_C"
        (out_dir / f"{stem}.md").write_text(md, encoding="utf-8")
        (out_dir / f"{stem}.json").write_text(
            json.dumps({"decision": decision, "payload": payload}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        results.append({"file": stem, "mode": "C", "n_texts": len(texts)})
        print(json.dumps({"ok": True, "results": results, "out_dir": str(out_dir)}, ensure_ascii=False, indent=2))
        return

    if args.demo:
        # A: business-heavy
        a_path = Path("/Users/home/Downloads/tg_private_4y_monthly/00_raw_origin/chat_8070485799.json")
        # B: try find social-ish short chat
        b_path = Path("/Users/home/Downloads/tg_private_4y_monthly/00_raw_origin/chat_5977904977.json")
        for label, path, force in [("A", a_path, "A"), ("B", b_path, "B")]:
            if not path.exists():
                continue
            chat = load_chat(path)
            decision, payload, md = run_one(chat, mode=force, self_id=args.self_id)
            stem = f"demo_mode_{label}_{chat['peer_id']}"
            (out_dir / f"{stem}.md").write_text(md, encoding="utf-8")
            (out_dir / f"{stem}.json").write_text(
                json.dumps({"decision": decision, "payload": payload}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            results.append({"file": stem, "mode": label, "peer_id": chat["peer_id"]})
        texts = collect_self_corpus(Path(args.chat_dir), args.self_id, min(80, args.limit_chats))
        decision, payload, md = run_one(None, mode="C", self_id=args.self_id, self_texts=texts)
        stem = "demo_mode_C_self_corpus"
        (out_dir / f"{stem}.md").write_text(md, encoding="utf-8")
        (out_dir / f"{stem}.json").write_text(
            json.dumps({"decision": decision, "payload": payload}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        results.append({"file": stem, "mode": "C", "n_texts": len(texts)})
        print(json.dumps({"ok": True, "results": results, "out_dir": str(out_dir)}, ensure_ascii=False, indent=2))
        return

    if not args.chat:
        ap.error("请提供 --chat，或使用 --self-corpus / --demo")

    chat = load_chat(Path(args.chat))
    decision, payload, md = run_one(chat, mode=mode, self_id=args.self_id)
    stem = f"mode_{decision['mode']}_{chat['peer_id']}"
    (out_dir / f"{stem}.md").write_text(md, encoding="utf-8")
    (out_dir / f"{stem}.json").write_text(
        json.dumps({"decision": decision, "payload": payload}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "mode": decision["mode"], "scores": decision["scores"], "out": str(out_dir / f"{stem}.md")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
