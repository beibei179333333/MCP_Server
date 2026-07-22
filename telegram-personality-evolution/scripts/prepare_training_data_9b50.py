#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成优化后的高质量训练数据集（Alpaca JSONL）。

示例：
  python3 prepare_training_data.py \\
    --source outputs/ \\
    --output train_data_final/ \\
    --min-nutrition medium \\
    --max-low-nutrition-ratio 0.25 \\
    --expand-deep-analysis \\
    --add-knowledge \\
    --balance-business-emotion \\
    --total-samples 65000
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL = Path(__file__).resolve().parent
SEED = 42

TEMPLATE_MARKERS = (
    "华强北科技人工坐席",
    "正在转接人工客服",
    "点击蓝色字体",
    "闪兑TRX",
    "能量闪租",
    "小本生意 诚信经营 赊账白嫖",
)

NUTRITION_RANK = {
    "high": 3,
    "medium": 2,
    "low": 1,
    "unknown": 0,
}


def nutrition_bucket(row: dict) -> str:
    lv = str(row.get("nutrition_level") or "")
    cat = str(row.get("category") or "")
    if "高营养" in lv or "Top20" in lv:
        return "high"
    if "中营养" in lv or "60%" in lv:
        return "medium"
    if "低营养" in lv or cat == "low_nutrition" or "20%" in lv:
        return "low"
    # fallback by category
    if cat in ("emotion", "business"):
        return "medium"
    return "low"


def category_bucket(row: dict) -> str:
    cat = str(row.get("category") or "")
    if cat == "business":
        return "business"
    if cat == "emotion":
        return "emotion"
    # low_nutrition may still be emotional/business-ish; keep as low
    tags = " ".join(str(x) for x in (row.get("business_style_tags") or []))
    if any(k in tags for k in ("报价", "售后", "业务", "营销")):
        return "business"
    return "emotion" if cat != "low_nutrition" else "low"


def is_template_ad(text: str) -> bool:
    t = text or ""
    hits = sum(1 for m in TEMPLATE_MARKERS if m in t)
    return hits >= 2 or ("人工坐席" in t and "TRX" in t and len(t) > 400)


def load_monthly_alpaca(source: Path) -> list[dict]:
    rows: list[dict] = []
    for kind in ("train", "val"):
        for fp in sorted(source.glob(f"*/{kind}_*_alpaca.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, list):
                continue
            for row in data:
                if not isinstance(row, dict):
                    continue
                out = str(row.get("output") or "").strip()
                if not out:
                    continue
                rec = dict(row)
                rec["_source_file"] = str(fp.relative_to(source)) if fp.is_relative_to(source) else str(fp)
                rec["_nutrition"] = nutrition_bucket(rec)
                rec["_cat"] = category_bucket(rec)
                rec["_template"] = is_template_ad(out)
                if rec["_template"]:
                    rec["_nutrition"] = "low"
                    rec["_cat"] = "low"
                rows.append(rec)
    return rows


def year_from_row(row: dict) -> int | None:
    ym = str(row.get("year_month") or "")
    m = re.match(r"(20\d{2})", ym)
    if m:
        return int(m.group(1))
    did = str(row.get("dialog_id") or "")
    m2 = re.match(r"(20\d{2})", did)
    return int(m2.group(1)) if m2 else None


def apply_weight_boosts(
    row: dict,
    *,
    business_weight_mult: float,
    recent_years: set[int],
    recent_weight_mult: float,
) -> dict:
    """提高业务权重，并抬升 2025-2026 近期样本权重。"""
    rec = dict(row)
    w = float(rec.get("sample_weight") or 1.0)
    y = year_from_row(rec)
    if rec.get("_cat") == "business" and not rec.get("_template"):
        w *= business_weight_mult
    if y is not None and y in recent_years:
        w *= recent_weight_mult
    rec["sample_weight"] = round(min(w, 4.0), 4)
    rec["_year"] = y
    return rec


def sample_score(
    row: dict,
    *,
    expand_deep: bool,
    business_weight_mult: float = 1.0,
    recent_years: set[int] | None = None,
    recent_weight_mult: float = 1.0,
) -> float:
    """越高越优先入选。"""
    nut = row["_nutrition"]
    base = {"high": 3.0, "medium": 2.0, "low": 0.6, "unknown": 0.3}[nut]
    w = float(row.get("sample_weight") or 1.0)
    score = base * (0.7 + 0.3 * min(w, 2.0))
    if row["_template"]:
        score *= 0.15
    out = str(row.get("output") or "")
    inp = str(row.get("input") or "")
    # 过短空确认降权
    if len(re.sub(r"\s+", "", out)) <= 2:
        score *= 0.35
    # 深分析代理：短上下文 + 非模板 + 中高营养（≈少消息高价值对话）
    if expand_deep and nut in ("high", "medium") and not row["_template"]:
        turns = inp.count("\n") + 1
        if turns <= 8 and len(out) <= 800:
            score *= 1.25
        if turns <= 4:
            score *= 1.1
    # 业务样本提权（选样 + 后续 sample_weight）
    if row["_cat"] == "business" and nut != "low":
        score *= max(1.08, business_weight_mult)
    # 近期年份提权
    y = row.get("_year")
    if y is None:
        y = year_from_row(row)
    if recent_years and y in recent_years:
        score *= max(1.0, recent_weight_mult)
    return score


def dedupe_key(row: dict) -> str:
    raw = f"{row.get('input','')}\n||\n{row.get('output','')}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _knowledge_md_files(knowledge_root: Path) -> list[Path]:
    """收集 knowledge/ 下全部 Markdown（含子目录），排除隐藏文件。"""
    files = sorted(
        p
        for p in knowledge_root.rglob("*.md")
        if p.is_file() and not any(part.startswith(".") for part in p.parts)
    )
    return files


def _cat_from_knowledge_path(rel: str) -> str:
    low = rel.lower()
    if "business" in low or "strategy" in low:
        return "business"
    if "emotion" in low or "relationship" in low:
        return "emotion"
    if "language" in low or "personality" in low:
        return "emotion"
    return "emotion"


def _chunk_markdown(text: str, *, max_chars: int = 900) -> list[str]:
    """按段落切块，保留长期记忆可用的知识片段。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        # 去掉纯表格分隔行噪声，保留有信息量的内容
        lines = [
            ln
            for ln in p.splitlines()
            if ln.strip()
            and not re.fullmatch(r"\|?[\s\-:|]+\|?", ln.strip())
        ]
        p2 = "\n".join(lines).strip()
        if not p2 or len(p2) < 20:
            continue
        if len(buf) + len(p2) + 2 <= max_chars:
            buf = f"{buf}\n\n{p2}".strip() if buf else p2
        else:
            if buf:
                chunks.append(buf[:max_chars])
            buf = p2[:max_chars]
    if buf:
        chunks.append(buf[:max_chars])
    return chunks


def build_knowledge_samples(knowledge_root: Path) -> list[dict]:
    """从 knowledge/ 全量 Markdown 生成额外上下文样本（非伪造私聊原文）。"""
    files = _knowledge_md_files(knowledge_root)
    scenarios = [
        ("对方抱怨办理太慢，语气有点急", "emotion", "先确认听到，再给可执行下一步，短句收束，不灌鸡汤。"),
        ("对方询价能量/TRX，只问价格", "business", "被动商务：确认需求类型后给条件或入口，少空谈，需要时拆多行短句。"),
        ("对方发来验证码让你帮收", "business", "明确拒绝越权与验证码请求，优先风险提示，可给替代正规路径。"),
        ("对方只回「在吗」", "emotion", "短确认即可，不展开长篇；保持有温度的短，而不是空的短。"),
        ("老客户售后问进度", "business", "先对齐状态，再给时间点或下一步，避免模板广告腔。"),
        ("对方情绪低落倾诉", "emotion", "确认→可执行出口→必要时短句收束；共情有配额，不做全天候治愈系。"),
    ]

    style_bits: list[str] = []
    context_chunks: list[tuple[str, str, str]] = []  # rel, cat, chunk
    for fp in files:
        rel = str(fp.relative_to(knowledge_root))
        cat = _cat_from_knowledge_path(rel)
        text = fp.read_text(encoding="utf-8", errors="ignore")
        for chunk in _chunk_markdown(text):
            context_chunks.append((rel, cat, chunk))
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("|") or s.startswith(">"):
                continue
            if len(s) < 12:
                continue
            style_bits.append(s[:180])
            if len(style_bits) >= 120:
                break

    rows: list[dict] = []

    # 1) 场景锚定
    for i, (user_in, cat, principle) in enumerate(scenarios):
        anchor = style_bits[i % len(style_bits)] if style_bits else principle
        rows.append(
            {
                "instruction": "根据上下文回复对方消息，保持自然、真实且符合既有表达风格。",
                "input": user_in,
                "output": f"{principle}\n（风格锚定）{anchor}",
                "dialog_id": f"knowledge_{i:04d}",
                "year_month": "knowledge",
                "category": cat,
                "emotion_tags": ["知识锚定"] if cat == "emotion" else [],
                "tone_tags": ["知识锚定"],
                "business_style_tags": ["知识锚定"] if cat == "business" else [],
                "nutrition_level": "高营养Top20%",
                "temporal_weight": 1.0,
                "nutrition_multiplier": 1.3,
                "sample_weight": 1.35,
                "_nutrition": "high",
                "_cat": cat,
                "_template": False,
                "_source_file": "knowledge/",
                "_knowledge": True,
            }
        )

    # 2) 短句原则转写
    for j, bit in enumerate(style_bits[:100]):
        rows.append(
            {
                "instruction": "用自己的一贯风格，把下面的原则转成可执行的简短回复要点（不要写成广告模板）。",
                "input": bit,
                "output": f"记住并体现在回复里：{bit}\n尽量短、碎、实、有边界。",
                "dialog_id": f"knowledge_style_{j:04d}",
                "year_month": "knowledge",
                "category": "emotion",
                "emotion_tags": [],
                "tone_tags": ["知识锚定"],
                "business_style_tags": [],
                "nutrition_level": "高营养Top20%",
                "temporal_weight": 1.0,
                "nutrition_multiplier": 1.25,
                "sample_weight": 1.25,
                "_nutrition": "high",
                "_cat": "emotion",
                "_template": False,
                "_source_file": "knowledge/",
                "_knowledge": True,
            }
        )

    # 3) knowledge/ 全文块 → 长期记忆额外上下文（核心）
    for k, (rel, cat, chunk) in enumerate(context_chunks):
        rows.append(
            {
                "instruction": (
                    "以下内容来自内部 knowledge/ 知识库，请作为长期人格/关系/商务记忆的额外上下文内化；"
                    "回答时用第一人称要点复述可执行约束，不要编造未出现的事实。"
                ),
                "input": f"[knowledge/{rel}]\n{chunk}",
                "output": (
                    f"已内化 knowledge/{rel} 的约束。\n"
                    f"执行要点：{chunk[:420].strip()}\n"
                    "回复时保持短、碎、实、有边界，不套模板广告腔。"
                ),
                "dialog_id": f"knowledge_ctx_{k:04d}",
                "year_month": "knowledge",
                "category": cat,
                "emotion_tags": ["知识库上下文"] if cat == "emotion" else [],
                "tone_tags": ["知识库上下文", "长期记忆"],
                "business_style_tags": ["知识库上下文"] if cat == "business" else [],
                "nutrition_level": "高营养Top20%",
                "temporal_weight": 1.0,
                "nutrition_multiplier": 1.4,
                "sample_weight": 1.5,
                "_nutrition": "high",
                "_cat": cat,
                "_template": False,
                "_source_file": f"knowledge/{rel}",
                "_knowledge": True,
            }
        )
    return rows


def export_knowledge_context_jsonl(knowledge_root: Path, out_dir: Path) -> dict:
    """单独导出 knowledge 上下文数据集，供 Stage3 作为额外 dataset 挂载。"""
    rows = build_knowledge_samples(knowledge_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    train_path = out_dir / "context.jsonl"
    with train_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(
                json.dumps(
                    {
                        "instruction": r["instruction"],
                        "input": r["input"],
                        "output": r["output"],
                        "sample_weight": r.get("sample_weight", 1.0),
                        "from_knowledge": True,
                        "source_file": r.get("_source_file"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    meta = {
        "n": len(rows),
        "path": str(train_path),
        "knowledge_files": [str(p.relative_to(knowledge_root)) for p in _knowledge_md_files(knowledge_root)],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return meta


def select_balanced(
    pool: list[dict],
    *,
    total: int,
    min_nutrition: str,
    max_low_ratio: float,
    balance_be: bool,
    expand_deep: bool,
    business_weight_mult: float = 1.6,
    recent_years: set[int] | None = None,
    recent_weight_mult: float = 1.45,
    recent_min_ratio: float = 0.42,
) -> list[dict]:
    recent_years = recent_years or {2025, 2026}
    score_kw = dict(
        expand_deep=expand_deep,
        business_weight_mult=business_weight_mult,
        recent_years=recent_years,
        recent_weight_mult=recent_weight_mult,
    )

    min_rank = NUTRITION_RANK[min_nutrition]
    eligible = [r for r in pool if NUTRITION_RANK[r["_nutrition"]] >= min_rank or r["_nutrition"] == "low"]
    primary = [r for r in eligible if NUTRITION_RANK[r["_nutrition"]] >= min_rank]
    low_pool = [r for r in eligible if r["_nutrition"] == "low" and not r.get("_knowledge")]

    max_low = int(total * max_low_ratio)
    target_primary = total - max_low
    recent_quota = int(total * recent_min_ratio)

    def sk(r):
        return (-sample_score(r, **score_kw), r.get("dialog_id") or "")

    primary_sorted = sorted(primary, key=sk)
    low_sorted = sorted(low_pool, key=sk)
    recent_primary = sorted(
        [r for r in primary if year_from_row(r) in recent_years],
        key=sk,
    )
    older_primary = sorted(
        [r for r in primary if year_from_row(r) not in recent_years],
        key=sk,
    )

    selected: list[dict] = []
    seen = set()

    def take(rows: list[dict], n: int, pred=None) -> int:
        got = 0
        for r in rows:
            if got >= n:
                break
            if pred and not pred(r):
                continue
            k = dedupe_key(r)
            if k in seen:
                continue
            seen.add(k)
            selected.append(r)
            got += 1
        return got

    # 1) 先锁近期配额（2025-2026）
    take(recent_primary, recent_quota)

    # 2) 业务/情绪平衡填充剩余 primary
    remain_primary = target_primary - len(selected)
    if balance_be and remain_primary > 0:
        half = max(0, remain_primary // 2)
        biz = [r for r in primary_sorted if r["_cat"] == "business"]
        emo = [r for r in primary_sorted if r["_cat"] == "emotion"]
        # 业务侧再偏一点（约 55% of remain）
        biz_n = int(remain_primary * 0.55)
        emo_n = remain_primary - biz_n
        take(biz, biz_n)
        take(emo, emo_n)
        take(biz + emo + older_primary + primary_sorted, target_primary - len(selected))
    else:
        take(older_primary + primary_sorted, target_primary - len(selected))

    if len(selected) < target_primary:
        take(primary_sorted, target_primary - len(selected))

    # 3) low nutrition
    low_non_ad = [r for r in low_sorted if not r["_template"]]
    low_ad = [r for r in low_sorted if r["_template"]]
    # 近期 low 优先
    low_recent = [r for r in low_non_ad if year_from_row(r) in recent_years]
    take(low_recent, max_low // 2)
    take(low_non_ad, max_low - sum(1 for r in selected if r["_nutrition"] == "low"))
    if sum(1 for r in selected if r["_nutrition"] == "low") < max_low:
        remain = max_low - sum(1 for r in selected if r["_nutrition"] == "low")
        take(low_ad, min(remain, max(0, int(max_low * 0.15))))

    if len(selected) < total:
        take(recent_primary + primary_sorted + low_non_ad, total - len(selected))

    selected = sorted(selected, key=lambda r: -sample_score(r, **score_kw))[:total]
    return selected


def split_train_val(rows: list[dict], val_ratio: float = 0.05) -> tuple[list[dict], list[dict]]:
    """按 dialog_id 前缀分组防泄漏（knowledge_* 可进 train）。"""
    rng = random.Random(SEED)
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        did = str(r.get("dialog_id") or "")
        if did.startswith("knowledge_"):
            g = "knowledge"
        else:
            # year_month or dialog prefix
            g = str(r.get("year_month") or did.split("_")[0] or "unk")
        groups[g].append(r)

    keys = list(groups.keys())
    rng.shuffle(keys)
    # approximate val by groups
    val_target = max(1, int(len(rows) * val_ratio))
    val, train = [], []
    for k in keys:
        bucket = groups[k]
        if k == "knowledge":
            train.extend(bucket)
            continue
        if len(val) < val_target and rng.random() < val_ratio * 1.2:
            val.extend(bucket)
        else:
            train.extend(bucket)
    # adjust sizes
    if len(val) > val_target * 1.5:
        rng.shuffle(val)
        move = val[val_target:]
        val = val[:val_target]
        train.extend(move)
    if len(val) < max(1, val_target // 2):
        rng.shuffle(train)
        need = val_target - len(val)
        val.extend(train[:need])
        train = train[need:]
    return train, val


def to_alpaca(row: dict) -> dict:
    out = {
        "instruction": row.get("instruction")
        or "根据上下文回复对方消息，保持自然、真实且符合既有表达风格。",
        "input": row.get("input") or "",
        "output": row.get("output") or "",
    }
    # keep useful metadata for auditing (Axolotl alpaca type ignores extras usually)
    for k in (
        "dialog_id",
        "year_month",
        "category",
        "nutrition_level",
        "sample_weight",
        "emotion_tags",
        "tone_tags",
        "business_style_tags",
    ):
        if k in row and row[k] is not None:
            out[k] = row[k]
    out["quality_tier"] = row.get("_nutrition")
    out["balanced_category"] = row.get("_cat")
    if row.get("_knowledge"):
        out["from_knowledge"] = True
    if row.get("_template"):
        out["template_ad"] = True
    return out


def summarize(rows: list[dict]) -> dict:
    return {
        "n": len(rows),
        "nutrition": dict(Counter(r.get("_nutrition") or r.get("quality_tier") for r in rows)),
        "category": dict(Counter(r.get("_cat") or r.get("balanced_category") for r in rows)),
        "template_ads": sum(1 for r in rows if r.get("_template") or r.get("template_ad")),
        "knowledge": sum(1 for r in rows if r.get("_knowledge") or r.get("from_knowledge")),
        "year_month": dict(Counter(str(r.get("year_month")) for r in rows).most_common(12)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=SKILL / "outputs")
    ap.add_argument("--output", type=Path, default=SKILL / "train_data_final")
    ap.add_argument("--min-nutrition", choices=("high", "medium", "low"), default="medium")
    ap.add_argument("--max-low-nutrition-ratio", type=float, default=0.25)
    ap.add_argument("--expand-deep-analysis", action="store_true")
    ap.add_argument("--add-knowledge", action="store_true")
    ap.add_argument("--balance-business-emotion", action="store_true")
    ap.add_argument("--total-samples", type=int, default=65000)
    ap.add_argument("--val-ratio", type=float, default=0.05)
    ap.add_argument("--business-weight-mult", type=float, default=1.75, help="业务样本 sample_weight 乘数")
    ap.add_argument("--recent-years", default="2025,2026", help="近期年份，逗号分隔")
    ap.add_argument("--recent-weight-mult", type=float, default=1.5, help="近期样本权重乘数")
    ap.add_argument("--recent-min-ratio", type=float, default=0.45, help="选样中近期年份最低占比")
    args = ap.parse_args()

    random.seed(SEED)
    source = args.source if args.source.is_absolute() else SKILL / args.source
    output = args.output if args.output.is_absolute() else SKILL / args.output
    output.mkdir(parents=True, exist_ok=True)
    recent_years = {int(x.strip()) for x in args.recent_years.split(",") if x.strip()}

    print(f"loading from {source} …")
    pool = load_monthly_alpaca(source)
    print(f"raw pool={len(pool)}")

    if args.add_knowledge:
        krows = build_knowledge_samples(SKILL / "knowledge")
        pool.extend(krows)
        print(f"added knowledge samples={len(krows)}")
        kmeta = export_knowledge_context_jsonl(SKILL / "knowledge", SKILL / "train_data_knowledge")
        print(f"exported knowledge context dataset n={kmeta['n']} → {kmeta['path']}")

    # 预打年份并应用业务/近期权重（写入最终 sample_weight）
    pool = [
        apply_weight_boosts(
            r,
            business_weight_mult=args.business_weight_mult,
            recent_years=recent_years,
            recent_weight_mult=args.recent_weight_mult,
        )
        for r in pool
    ]

    selected = select_balanced(
        pool,
        total=args.total_samples,
        min_nutrition=args.min_nutrition,
        max_low_ratio=args.max_low_nutrition_ratio,
        balance_be=args.balance_business_emotion,
        expand_deep=args.expand_deep_analysis,
        business_weight_mult=args.business_weight_mult,
        recent_years=recent_years,
        recent_weight_mult=args.recent_weight_mult,
        recent_min_ratio=args.recent_min_ratio,
    )
    selected = sorted(
        selected,
        key=lambda r: -sample_score(
            r,
            expand_deep=args.expand_deep_analysis,
            business_weight_mult=args.business_weight_mult,
            recent_years=recent_years,
            recent_weight_mult=args.recent_weight_mult,
        ),
    )

    train, val = split_train_val(selected, val_ratio=args.val_ratio)

    def year_dist(rows):
        c = Counter()
        for r in rows:
            y = year_from_row(r)
            c[str(y) if y else "unk"] += 1
        return dict(c)

    train_path = output / "train.jsonl"
    val_path = output / "val.jsonl"
    with train_path.open("w", encoding="utf-8") as f:
        for r in train:
            f.write(json.dumps(to_alpaca(r), ensure_ascii=False) + "\n")
    with val_path.open("w", encoding="utf-8") as f:
        for r in val:
            f.write(json.dumps(to_alpaca(r), ensure_ascii=False) + "\n")

    # also write quality report
    st_train = summarize(train)
    recent_n = sum(1 for r in train if year_from_row(r) in recent_years)
    biz_w = [float(r.get("sample_weight") or 1) for r in train if (r.get("_cat") or r.get("balanced_category")) == "business"]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quality": "high",
        "params": {
            "source": str(source),
            "output": str(output),
            "min_nutrition": args.min_nutrition,
            "max_low_nutrition_ratio": args.max_low_nutrition_ratio,
            "expand_deep_analysis": args.expand_deep_analysis,
            "add_knowledge": args.add_knowledge,
            "balance_business_emotion": args.balance_business_emotion,
            "total_samples_requested": args.total_samples,
            "val_ratio": args.val_ratio,
            "business_weight_mult": args.business_weight_mult,
            "recent_years": sorted(recent_years),
            "recent_weight_mult": args.recent_weight_mult,
            "recent_min_ratio": args.recent_min_ratio,
            "seed": SEED,
        },
        "pool_size": len(pool),
        "selected_total": len(selected),
        "train": st_train,
        "val": summarize(val),
        "year_dist_train": year_dist(train),
        "recent_ratio_train": round(recent_n / max(1, len(train)), 4),
        "business_weight_mean": round(sum(biz_w) / max(1, len(biz_w)), 4) if biz_w else None,
        "constraints": {
            "low_ratio_train": round(st_train["nutrition"].get("low", 0) / max(1, len(train)), 4),
            "business_emotion_train": {
                "business": st_train["category"].get("business", 0),
                "emotion": st_train["category"].get("emotion", 0),
                "low": st_train["category"].get("low", 0),
            },
        },
        "notes": [
            "模板广告腔强制降为 low，并限制进入比例",
            "min-nutrition=medium 时主仓为高+中营养",
            "expand-deep-analysis：短上下文+中高营养提权（代理 ≤100 深分析对话）",
            "add-knowledge：注入 knowledge/ 风格锚定样本",
            f"业务样本权重 ×{args.business_weight_mult}",
            f"近期年份 {sorted(recent_years)} 权重 ×{args.recent_weight_mult}，选样占比目标 ≥{args.recent_min_ratio}",
            "按 year_month/dialog 分组切 val，降低泄漏",
        ],
    }
    (output / "quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "train": str(train_path),
                "val": str(val_path),
                "train_n": len(train),
                "val_n": len(val),
                "format": "alpaca-jsonl",
                "axolotl_config": "config/qwen3.6_27b_personality_stage1.yaml",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    md = [
        "# 高质量训练数据集报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- train：**{len(train)}** → `{train_path.name}`",
        f"- val：**{len(val)}** → `{val_path.name}`",
        f"- 请求总量：{args.total_samples}；实际选中：{len(selected)}",
        f"- 最低营养：`{args.min_nutrition}`；低营养上限比例：{args.max_low_nutrition_ratio}",
        f"- 深分析提权：{args.expand_deep_analysis}；知识库注入：{args.add_knowledge}；业务/情绪平衡：{args.balance_business_emotion}",
        "",
        "## Train 营养分布",
        "",
        f"```json\n{json.dumps(report['train']['nutrition'], ensure_ascii=False, indent=2)}\n```",
        "",
        "## Train 类别分布",
        "",
        f"```json\n{json.dumps(report['train']['category'], ensure_ascii=False, indent=2)}\n```",
        "",
        f"- 低营养占比：{report['constraints']['low_ratio_train']}",
        f"- 模板广告条数：{report['train']['template_ads']}",
        f"- 知识锚定条数：{report['train']['knowledge']}",
        f"- 业务样本均权：{report['business_weight_mean']}（×{args.business_weight_mult}）",
        f"- 近期年份占比：{report['recent_ratio_train']}（目标 ≥{args.recent_min_ratio}；权重 ×{args.recent_weight_mult}）",
        "",
        "## Train 年份分布",
        "",
        f"```json\n{json.dumps(report['year_dist_train'], ensure_ascii=False, indent=2)}\n```",
        "",
        "## 使用",
        "",
        "```bash",
        "axolotl train config/qwen3.6_27b_personality_stage1.yaml",
        "```",
        "",
    ]
    (output / "QUALITY.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps(
        {
            "train_n": len(train),
            "val_n": len(val),
            "low_ratio_train": report["constraints"]["low_ratio_train"],
            "nutrition_train": report["train"]["nutrition"],
            "category_train": report["train"]["category"],
            "year_dist_train": report["year_dist_train"],
            "recent_ratio_train": report["recent_ratio_train"],
            "business_weight_mean": report["business_weight_mean"],
            "output": str(output),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
