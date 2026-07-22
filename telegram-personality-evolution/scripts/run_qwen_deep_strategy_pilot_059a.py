#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qwen 深版策略试点：100–300 人分层抽样，不覆盖规则版。

硬约束：
- 规则版 strategies/ 只读保留
- 新版写入 strategies_qwen_deep_v1/
- 极少消息强制低置信 + 证据句 +「暂不判断」
- 字段区分 fact_basis / inference / strategy
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SKILL_ROOT = Path(__file__).resolve().parent
PIPELINE = Path("/Users/home/Downloads/tg_private_4y_monthly")
CFG = json.loads((PIPELINE / "config_full_coverage.json").read_text(encoding="utf-8"))
RAW = Path(CFG["RAW_ORIGIN"])
RULE_DIR = PIPELINE / "06_full_coverage" / "strategies" / "by_peer"
OUT_ROOT = PIPELINE / "06_full_coverage" / "strategies_qwen_deep_v1"
BY_PEER = OUT_ROOT / "by_peer"
PILOT_DIR = SKILL_ROOT / "outputs" / "deep_pilot"
SELF = str(CFG["SELF_USER_ID"])
STRATEGY_TYPES = list(CFG["strategy_types"])
STRATEGY_VERSION = "qwen_deep_v1"
FEW_MSG_MAX = 5  # <=5：强制 insufficient + 暂不判断闸门

FORBIDDEN = (
    "archived_huiwang_lianghao",
    "split_chats_filtered",
    "汇旺名单",
    "靓号名单",
    "号码商名单",
)

_USER_RE = re.compile(r"(?:user)?(\d+)$", re.I)
_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\ufeff\u00a0]")


def assert_source_ok(path: Path) -> None:
    s = str(path)
    for frag in FORBIDDEN:
        if frag in s:
            raise RuntimeError(f"禁止过滤/名单路径: {path}")


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for path in (Path("/Users/home/技能/.env"), SKILL_ROOT / ".env", PIPELINE / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "SILICONFLOW_API_KEY"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def extract_text(text: Any) -> str:
    if text is None:
        return ""
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        parts = []
        for item in text:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text", "")))
        return "".join(parts)
    return str(text)


def normalize_msg_text(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = _INVISIBLE.sub("", t).strip()
    return re.sub(r"\n{3,}", "\n\n", t)


def sender_id(msg: dict) -> str | None:
    for k in ("from_id", "actor_id", "sender_id"):
        v = msg.get(k)
        if v is None:
            continue
        m = _USER_RE.search(str(v).replace(" ", ""))
        if m:
            return m.group(1)
        d = re.sub(r"\D", "", str(v))
        if d:
            return d
    return None


def has_media(msg: dict) -> bool:
    return bool(msg.get("media_type") or msg.get("photo") or msg.get("file") or msg.get("sticker_emoji"))


def is_valid_message(msg: dict) -> tuple[bool, str]:
    if str(msg.get("type") or "message").lower() == "service":
        return False, "service"
    if not msg.get("date"):
        return False, "bad_date"
    if not sender_id(msg):
        return False, "no_sender"
    text = normalize_msg_text(extract_text(msg.get("text")))
    if not text:
        return False, "empty_media" if has_media(msg) else "empty"
    if not re.sub(r"\s+", "", text):
        return False, "invisible"
    return True, text


def confidence_cap(n: int) -> float:
    if n <= 0:
        return 0.05
    if n <= 2:
        return round(0.15 + 0.03 * n, 4)
    if n <= 5:
        return round(0.25 + 0.03 * (n - 3), 4)
    if n <= 20:
        return round(0.40 + 0.01 * (n - 6), 4)
    if n <= 50:
        return round(0.60 + 0.005 * (n - 21), 4)
    return 0.75


def load_valid_msgs(peer_id: str) -> list[dict]:
    path = RAW / f"chat_{peer_id}.json"
    assert_source_ok(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    msgs = data.get("messages") if isinstance(data, dict) else data
    out = []
    for m in msgs or []:
        if not isinstance(m, dict):
            continue
        ok, text = is_valid_message(m)
        if not ok:
            continue
        sid = sender_id(m)
        out.append(
            {
                "id": m.get("id"),
                "date": m.get("date"),
                "from_self": str(sid) == SELF,
                "text": text[:800],
            }
        )
    return out


def call_qwen(system: str, user: str, api_key: str, base_url: str, model: str, retries: int = 4) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 6000,
        "enable_thinking": False,
    }
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
            wait = min(40, 2 * attempt)
            if isinstance(e, urllib.error.HTTPError) and e.code in (429, 503):
                wait = min(70, 6 * attempt)
            time.sleep(wait)
    raise last_err  # type: ignore[misc]


def _repair_json_blob(blob: str) -> str:
    """修复模型常见 JSON 瑕疵：尾逗号、中文引号、未转义换行。"""
    blob = blob.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    blob = re.sub(r",\s*([}\]])", r"\1", blob)
    # 字符串内裸换行 → \n（粗修复）
    out = []
    in_str = False
    esc = False
    for ch in blob:
        if in_str:
            if esc:
                out.append(ch)
                esc = False
                continue
            if ch == "\\":
                out.append(ch)
                esc = True
                continue
            if ch == '"':
                in_str = False
                out.append(ch)
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                continue
            out.append(ch)
        else:
            if ch == '"':
                in_str = True
            out.append(ch)
    return "".join(out)


def extract_json_obj(text: str) -> dict:
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    candidates = [text]
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        candidates.append(m.group(0))
    last_err: Exception | None = None
    for cand in candidates:
        for blob in (cand, _repair_json_blob(cand)):
            try:
                obj = json.loads(blob)
                if isinstance(obj, list) and obj:
                    return obj[0] if isinstance(obj[0], dict) else {"raw": obj}
                if isinstance(obj, dict):
                    return obj
            except Exception as e:
                last_err = e
                continue
    raise ValueError(f"no json: {last_err}")


SYSTEM_PROMPT = f"""你是 Telegram 私聊策略分析器。只根据给定对话做判断，禁止编造未出现的事实。

必须输出一个 JSON 对象，字段：
{{
  "relationship_stage": "陌生|初识|建立信任|熟悉|合作|长期|淡化|失联|恢复联系|结束",
  "my_attitude": "主动|被动|平衡|冷处理|拒绝|高投入|低投入",
  "fact_basis": ["只写对话里可核对的事实短句"],
  "inference": ["可推断但非事实的句子，须标注不确定"],
  "evidence_message_ids": [消息id整数],
  "insufficient_evidence": true/false,
  "confidence": 0.0到1.0,
  "strategies": {{
    "利益捆绑": {{
      "summary": "...",
      "actions": ["..."],
      "risk": "...",
      "verdict": "可执行|观察|暂不判断",
      "fact_basis": ["..."],
      "inference": ["..."],
      "evidence_message_ids": []
    }}
    // 其余 11 类同样结构：{ " / ".join(STRATEGY_TYPES) }
  }}
}}

规则：
1. fact_basis 必须能在对话原文中找到依据；找不到就不要写。
2. 不得把推断写进 fact_basis。
3. 有效消息很少（≤{FEW_MSG_MAX}）时：insufficient_evidence=true，confidence≤0.35，
   每类策略 verdict 必须为「暂不判断」，summary/actions 说明证据不足，禁止编造对方身份/业务/关系。
4. 证据不足时不要输出具体成交话术或虚构资源网络。
5. evidence_message_ids 只能使用用户提供的 id。
6. 全程简体中文。只输出 JSON。
"""


def forced_few_msg_record(
    peer: dict,
    msgs: list[dict],
    model: str,
) -> dict:
    """极少消息：不依赖模型编造，强制低置信 + 暂不判断。"""
    n = len(msgs)
    evidence_ids = [m["id"] for m in msgs if m.get("id") is not None]
    evidence_sentences = [f"[{m['id']}] {'我' if m['from_self'] else '对方'}: {m['text'][:200]}" for m in msgs[:12]]
    fact_basis = [s for s in evidence_sentences] if msgs else ["无有效消息，无法建立事实"]
    conf = min(confidence_cap(n), 0.25)
    strategies = {}
    for t in STRATEGY_TYPES:
        strategies[t] = {
            "type": t,
            "summary": "暂不判断：有效消息过少，不足以支撑该类策略。",
            "actions": ["等待更多真实对话后再评估", "仅保留礼貌通道，不主动深推"],
            "risk": "过度推断会污染策略库",
            "verdict": "暂不判断",
            "confidence": conf,
            "fact_basis": fact_basis[:3],
            "inference": [],
            "evidence_message_ids": evidence_ids,
            "info_note": "消息极少强制闸门：低置信度 + 暂不判断",
        }
    return base_record(
        peer=peer,
        msgs=msgs,
        model=model,
        confidence=conf,
        insufficient=True,
        evidence_ids=evidence_ids,
        fact_basis=fact_basis,
        inference=[],
        relationship_stage="陌生" if n <= 1 else "初识",
        my_attitude="被动",
        strategies=strategies,
        source_mode="forced_few_msg_gate",
        raw_model=None,
    )


def base_record(
    *,
    peer: dict,
    msgs: list[dict],
    model: str,
    confidence: float,
    insufficient: bool,
    evidence_ids: list,
    fact_basis: list,
    inference: list,
    relationship_stage: str,
    my_attitude: str,
    strategies: dict,
    source_mode: str,
    raw_model: dict | None,
) -> dict:
    return {
        "peer_id": str(peer["peer_id"]),
        "name": peer.get("name"),
        "valid_message_count": len(msgs),
        "value": peer.get("value"),
        "deep_analysis": True,
        "strategy_version": STRATEGY_VERSION,
        "model": model,
        "rule_strategy_ref": f"06_full_coverage/strategies/by_peer/{peer['peer_id']}.json",
        "confidence": confidence,
        "evidence_message_ids": evidence_ids,
        "fact_basis": fact_basis,
        "inference": inference,
        "insufficient_evidence": insufficient,
        "review_status": "pending",
        "relationship_stage": relationship_stage,
        "my_attitude": my_attitude,
        "strategies": strategies,
        "source_mode": source_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "run_qwen_deep_strategy_pilot.py",
        "raw_model_excerpt": None if raw_model is None else {k: raw_model.get(k) for k in ("relationship_stage", "my_attitude", "confidence", "insufficient_evidence")},
    }


def clamp_model_output(peer: dict, msgs: list[dict], model: str, obj: dict) -> dict:
    n = len(msgs)
    valid_ids = {m["id"] for m in msgs if m.get("id") is not None}
    corpus = "\n".join(m["text"] for m in msgs)
    evidence_ids = [i for i in (obj.get("evidence_message_ids") or []) if i in valid_ids]
    if not evidence_ids:
        evidence_ids = list(valid_ids)[:20]

    def _supported(claim: str) -> bool:
        c = normalize_msg_text(claim)
        corp = normalize_msg_text(corpus).lower().replace(" ", "")
        cn = c.lower().replace(" ", "")
        if len(cn) < 2:
            return False
        if cn in corp:
            return True
        toks = re.findall(r"[A-Za-z]{3,}|\d{2,}|[\u4e00-\u9fff]{2}", claim)
        toks = [t.lower() for t in toks if t not in ("对方", "询问", "回复", "表示", "进行")]
        if not toks:
            return False
        return sum(1 for t in toks if t.lower().replace(" ", "") in corp) / len(toks) >= 0.5

    raw_facts = [str(x)[:300] for x in (obj.get("fact_basis") or []) if str(x).strip()][:12]
    fact_basis, demoted = [], []
    for f in raw_facts:
        (fact_basis if _supported(f) else demoted).append(f)
    inference = [str(x)[:300] for x in (obj.get("inference") or []) if str(x).strip()][:12]
    inference = (inference + [f"[未核对降级] {x}" for x in demoted])[:20]
    if not fact_basis:
        fact_basis = [m["text"][:120] for m in msgs[:5]] if msgs else ["无有效消息"]

    insufficient = bool(obj.get("insufficient_evidence")) or n <= FEW_MSG_MAX or (len(demoted) > len(fact_basis) and n <= 20)
    conf = float(obj.get("confidence") or confidence_cap(n))
    conf = min(conf, confidence_cap(n))
    if insufficient:
        conf = min(conf, 0.35)

    strategies_in = obj.get("strategies") or {}
    strategies = {}
    for t in STRATEGY_TYPES:
        s = strategies_in.get(t) or {}
        if not isinstance(s, dict):
            s = {"summary": str(s)}
        verdict = str(s.get("verdict") or "").strip()
        if insufficient:
            verdict = "暂不判断"
            summary = "暂不判断：证据不足，避免过度推断。"
            actions = ["等待更多对话", "不做强绑定推进"]
            risk = "低样本幻觉风险"
        else:
            summary = str(s.get("summary") or "暂不判断")[:400]
            actions = [str(a)[:200] for a in (s.get("actions") or []) if str(a).strip()][:5]
            if not actions:
                actions = ["观察后再行动"]
            risk = str(s.get("risk") or "")[:200]
            if verdict not in ("可执行", "观察", "暂不判断"):
                verdict = "观察"
        eids = [i for i in (s.get("evidence_message_ids") or evidence_ids) if i in valid_ids] or evidence_ids[:8]
        sf, sd = [], []
        for x in (s.get("fact_basis") or fact_basis):
            xs = str(x)[:300]
            if not xs.strip():
                continue
            (sf if _supported(xs) else sd).append(xs)
        strategies[t] = {
            "type": t,
            "summary": summary if not insufficient else "暂不判断：证据不足，避免过度推断。",
            "actions": actions,
            "risk": risk,
            "verdict": verdict,
            "confidence": conf,
            "fact_basis": (sf or fact_basis)[:5],
            "inference": (
                [str(x)[:300] for x in (s.get("inference") or []) if str(x).strip()]
                + [f"[未核对降级] {x}" for x in sd]
                + ([] if insufficient else [])
            )[:5],
            "evidence_message_ids": eids,
            "info_note": "消息极少强制闸门" if insufficient else "fact_gate=inline_sanitize",
        }

    stage = str(obj.get("relationship_stage") or "陌生")
    attitude = str(obj.get("my_attitude") or "被动")
    if insufficient and n <= 2:
        stage = "陌生" if n <= 1 else "初识"
        attitude = "被动"

    rec = base_record(
        peer=peer,
        msgs=msgs,
        model=model,
        confidence=conf,
        insufficient=insufficient,
        evidence_ids=evidence_ids,
        fact_basis=fact_basis or (["无有效消息"] if n == 0 else [m["text"][:120] for m in msgs[:5]]),
        inference=inference,  # 保留降级项，便于审计
        relationship_stage=stage,
        my_attitude=attitude,
        strategies=strategies,
        source_mode="qwen_api_clamped",
        raw_model=obj,
    )
    rec["fact_gate"] = "inline_sanitize_v1"
    return rec


def build_user_prompt(peer: dict, msgs: list[dict]) -> str:
    lines = [
        f"peer_id={peer['peer_id']}",
        f"name={peer.get('name')}",
        f"valid_message_count={len(msgs)}",
        f"value={json.dumps(peer.get('value'), ensure_ascii=False)}",
        "对话（按时间，含 id）:",
    ]
    for m in msgs[-40:]:
        who = "我" if m["from_self"] else "对方"
        lines.append(f"- id={m['id']} date={m.get('date')} {who}: {m['text'][:500]}")
    if len(msgs) <= FEW_MSG_MAX:
        lines.append(
            f"\n注意：有效消息仅 {len(msgs)} 条（≤{FEW_MSG_MAX}）。"
            "必须 insufficient_evidence=true，各类策略 verdict=暂不判断，禁止编造。"
        )
    return "\n".join(lines)


def parse_failed_fallback(peer: dict, msgs: list[dict], model: str, err: str) -> dict:
    """模型输出无法解析时：降级为低置信记录，保证试点样本齐全。"""
    evidence_ids = [m["id"] for m in msgs if m.get("id") is not None]
    fact_basis = [
        f"[{m['id']}] {'我' if m['from_self'] else '对方'}: {m['text'][:160]}" for m in msgs[:10]
    ]
    conf = min(confidence_cap(len(msgs)), 0.2)
    strategies = {}
    for t in STRATEGY_TYPES:
        strategies[t] = {
            "type": t,
            "summary": "暂不判断：模型输出解析失败，已降级，待重跑。",
            "actions": ["人工复核原文", "稍后用同一版本重生成"],
            "risk": f"parse_error: {err[:120]}",
            "verdict": "暂不判断",
            "confidence": conf,
            "fact_basis": fact_basis[:3],
            "inference": [],
            "evidence_message_ids": evidence_ids[:12],
            "info_note": "json_parse_fallback",
        }
    return base_record(
        peer=peer,
        msgs=msgs,
        model=model,
        confidence=conf,
        insufficient=True,
        evidence_ids=evidence_ids,
        fact_basis=fact_basis or ["解析失败且无可用事实摘录"],
        inference=[],
        relationship_stage="初识",
        my_attitude="被动",
        strategies=strategies,
        source_mode="json_parse_fallback",
        raw_model=None,
    )


def generate_one(peer: dict, api_key: str, base_url: str, model: str, force_api_few: bool) -> dict:
    msgs = load_valid_msgs(str(peer["peer_id"]))
    n = len(msgs)

    # 0 条：绝不调模型
    if n == 0:
        return forced_few_msg_record(peer, msgs, model)

    # 极少消息：默认强制闸门；可选 --force-api-few 用于测幻觉
    if n <= FEW_MSG_MAX and not force_api_few:
        return forced_few_msg_record(peer, msgs, model)

    user = build_user_prompt(peer, msgs)
    last_err: Exception | None = None
    raw_last = ""
    for attempt in range(1, 4):
        prompt = user if attempt == 1 else (
            user
            + "\n\n重要：只输出合法 JSON。"
            "所有字符串用双引号；字符串内换行写成 \\n；不要尾逗号；不要 markdown。"
            "strategies 只保留 summary/actions/risk/verdict/evidence_message_ids 五个字段。"
        )
        try:
            raw_last = call_qwen(SYSTEM_PROMPT, prompt, api_key, base_url, model)
            obj = extract_json_obj(raw_last)
            return clamp_model_output(peer, msgs, model, obj)
        except Exception as e:
            last_err = e
            continue
    dump = PILOT_DIR / "raw_parse_failures" / f"{peer['peer_id']}.txt"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text(raw_last or str(last_err), encoding="utf-8")
    return parse_failed_fallback(peer, msgs, model, str(last_err))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=Path, default=PILOT_DIR / "pilot_sample_220.json")
    ap.add_argument("--limit", type=int, default=0, help="仅处理前 N 人（烟测）")
    ap.add_argument("--force-api-few", action="store_true", help="极少消息也调 API（评幻觉用）")
    ap.add_argument("--only-api-eligible", action="store_true", help="只跑 >FEW_MSG_MAX 的联系人")
    args = ap.parse_args()

    env = load_env()
    api_key = env.get("SILICONFLOW_API_KEY") or env.get("OPENAI_API_KEY")
    base_url = env.get("OPENAI_BASE_URL") or "https://api.siliconflow.cn/v1"
    model = env.get("OPENAI_MODEL") or "Qwen/Qwen3.5-397B-A17B"
    if not api_key:
        raise SystemExit("缺少 OPENAI_API_KEY / SILICONFLOW_API_KEY")

    peers = json.loads(args.sample.read_text(encoding="utf-8"))
    if args.only_api_eligible:
        peers = [p for p in peers if int(p.get("valid_message_count") or 0) > FEW_MSG_MAX]
    if args.limit > 0:
        peers = peers[: args.limit]

    BY_PEER.mkdir(parents=True, exist_ok=True)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    PILOT_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = OUT_ROOT / "pilot_strategies.jsonl"
    state_path = PILOT_DIR / "pilot_run_state.json"

    done = set()
    if state_path.exists():
        st = json.loads(state_path.read_text(encoding="utf-8"))
        done = set(st.get("done_peer_ids") or [])

    ok = fail = skip = 0
    with jsonl_path.open("a", encoding="utf-8") as jf:
        for i, peer in enumerate(peers, 1):
            pid = str(peer["peer_id"])
            out_path = BY_PEER / f"{pid}.json"
            if pid in done and out_path.exists():
                skip += 1
                continue
            try:
                rec = generate_one(peer, api_key, base_url, model, args.force_api_few)
                out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
                jf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                done.add(pid)
                ok += 1
                print(f"[{i}/{len(peers)}] OK {pid} msgs={rec['valid_message_count']} mode={rec['source_mode']} conf={rec['confidence']}")
            except Exception as e:
                fail += 1
                err = {"peer_id": pid, "error": str(e), "at": datetime.now(timezone.utc).isoformat()}
                (PILOT_DIR / "errors.jsonl").open("a", encoding="utf-8").write(json.dumps(err, ensure_ascii=False) + "\n")
                print(f"[{i}/{len(peers)}] FAIL {pid}: {e}")
            state_path.write_text(
                json.dumps(
                    {
                        "done_peer_ids": sorted(done),
                        "ok": ok,
                        "fail": fail,
                        "skip": skip,
                        "model": model,
                        "strategy_version": STRATEGY_VERSION,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    summary = {
        "strategy_version": STRATEGY_VERSION,
        "model": model,
        "sample_size_requested": len(peers),
        "ok": ok,
        "fail": fail,
        "skip": skip,
        "done_total": len(done),
        "out_dir": str(OUT_ROOT),
        "rule_dir_untouched": str(RULE_DIR),
        "few_msg_max": FEW_MSG_MAX,
        "note": "规则版未覆盖；全量 6935 需审核通过后再跑",
    }
    (OUT_ROOT / "pilot_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (PILOT_DIR / "pilot_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
