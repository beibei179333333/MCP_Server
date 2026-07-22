---
name: telegram-personality-evolution
description: >-
  按月份串行分析 Telegram 私聊：清洗与上下文、人格/关系/策略评分、联系人全覆盖宇宙、
  LoRA 月度训练集与四年人格演化。适用于 2022-01→2026-07 逐月任务、不过滤汇旺/靓号、
  ≤100 条优先深分析（含高价值 stars≥3）、全员 12 类策略。触发词：人格演化、月度分析、tg_private_4y、LoRA 训练集。
---

# Telegram Personality Evolution

按月份独立分析 Telegram 私聊，逐月更新人格、关系、策略与 LoRA 训练数据。

## 何时使用

- 用户给出 `monthly_agent_tasks` / `tg_private_4y_monthly` / 本 skill 路径
- 需要从 `2022-01` 串行跑到结束月，禁止读未来月
- 需要全联系人策略 + 人格成长轴 + 月度 Alpaca

## 硬规则（写死）

0. **角色与原则**：资深客户沟通专家 + 数据分析师；完整原则见 `references/project_principles.md`
1. **分块隔离**：禁止混客户/混场景；按 **单客户 (`peer_id`)** 或 **单次沟通 (`dialog_id`)** 切分处理
1b. **真人化表达**：新写话术短句优先（约 15–30 字）、手机两三行可读；**留白转化**——抛关键信息后等回复
1c. **语气人设**：自然口语、绝无 AI/教科书腔；专业有说服力，经验 + 亲和
1d. **训练模块一 · 1.1**：单会话句子合并精简 → `refine_conversation_1_1.py`
1e. **训练模块一 · 1.2**：30–60s 窗口连续消息压缩 → `refine_conversation_1_2.py`
1f. **训练模块二 · 2.1**：标准问答提取 → `extract_standard_qa_2_1.py` → `knowledge/qa/`
2. **不过滤联系人，只过滤无效消息**（含取消汇旺/靓号联系人级过滤）
3. **全覆盖**：目标联系人全集（当前约 7988），禁止只用 Top40/100
4. **深分析**：`valid_message_count <= 100` **或** `value.stars >= 3`（高价值+）；消息越少优先级越高
5. **全员 12 类策略** + `confidence`（样本少也生成，不跳过）
6. **禁止使用未来月份信息**；微调只追加演化，不覆盖历史结论
7. **保持原始文本**（入库证据不润色）；新写示范句才做人话化短句

## 默认路径

| 角色 | 路径 |
|------|------|
| 技能根 | 本目录 |
| 数据工程产物 | `/Users/home/Downloads/tg_private_4y_monthly` |
| 月度任务书 | `/Users/home/Downloads/压缩包/monthly_agent_tasks_2022-2026-07` |
| 原始导出 | `/Users/home/Downloads/Telegram Lite/聊天记录最新716/result.json` |
| 源只读筛选目录 | `/Users/home/Documents/新筛选聊天`（若空则从 result.json 私聊回填） |

## 执行顺序

```text
1. build_contact_universe.py     # 全员宇宙 + 价值分层 + ≤100/高价值 深分析旗标
2. expand_deep_coverage_le100.py # （可由 build 自动调用）扩量队列 + 策略旗标同步
3. month_runner.py --from 2022-01 --to 2026-07   # 串行月度
   ├─ 清洗/上下文/标签（复用或调用主工程流水线）
   ├─ score_personality.py
   ├─ score_relationship.py
   ├─ score_strategy.py
   ├─ score_lora.py
   ├─ ★ generate_monthly_detailed_summary.py --month YYYY-MM   # 强制 22 章详细总结
   └─ 追加 long_term_personality_evolution.jsonl
4. build_knowledge_base.py       # 更新 knowledge/（含深分析扩量说明）
5. 全部月份完成后：
   generate_monthly_detailed_summary.py --final-only
   → reports/final/report_2022-01_2026-07_personality_evolution.md
```

断点：`state/month_runner_state.json`。未生成详细总结或验收失败 → **当月不得 completed**。

## 每月必读

- `monthly_prompts/YYYY-MM.md`
- `references/pipeline_rules.md`
- `references/monthly_detailed_report_spec.md`（详细总结强制维度）
- 上月 `outputs/YYYY-MM/metrics_*.json`（若非首月）

## 每月输出（见 expected_output.json）

```text
outputs/YYYY-MM/
  report_YYYY-MM.md
  metrics_YYYY-MM.json
  train_YYYY-MM_alpaca.json
  val_YYYY-MM_alpaca.json
  contact_strategies_YYYY-MM.jsonl   # 可选：当月活跃联系人策略切片

reports/monthly/
  YYYY-MM_personality_summary_detailed.md   # ★ 强制
  YYYY-MM_personality_summary_detailed.meta.json
```

## 快速命令

```bash
cd "/Users/home/Downloads/压缩包/skills/telegram-personality-evolution"
python3 build_contact_universe.py
python3 month_runner.py --from 2022-01 --to 2026-07
# 或单独重生成详细总结：
python3 generate_monthly_detailed_summary.py --from 2022-01 --to 2026-07
```

## 第四～六阶段产物（Agent 直读）

```bash
python3 build_person_portraits.py          # person/{peer_id}.json ×7988
python3 build_knowledge_base.py            # knowledge/**/*.md
python3 run_qwen_deep_ladder.py --build-samples
python3 run_qwen_deep_ladder.py --eval-tier 220
python3 run_qwen_deep_ladder.py --expand-tier 1000 --workers 4
# 满员且 gate 通过后再：2500 → 6935（禁止跳阶）
```

| 阶段 | 路径 | 说明 |
|------|------|------|
| 4 联系人画像 | `person/{id}.json` | relationship/trust/business/emotion/strategy/risk |
| 5 Qwen 阶梯 | `strategies_qwen_deep_v1/` + `outputs/deep_pilot/ladder/` | 220→1000→2500→6935 |
| 6 知识库 | `knowledge/{personality,relationship,business,emotion,language,strategy,lora}/` | 全 Markdown |

## Qwen 深版策略（阶梯扩量）

规则版 `06_full_coverage/strategies/` **只读保留**。深版写入独立目录。

```bash
python3 run_qwen_deep_strategy_pilot.py --sample outputs/deep_pilot/pilot_sample_220.json
python3 eval_rule_vs_qwen_deep.py
python3 run_qwen_deep_ladder.py --eval-tier 220   # 门禁：重复率/幻觉/一致性/稳定性
```

- 输出：`tg_private_4y_monthly/06_full_coverage/strategies_qwen_deep_v1/`
- ≤5 条有效消息：强制低置信 + 证据句 + `暂不判断`
- 新字段：`strategy_version` / `model` / `fact_basis` / `inference` / `insufficient_evidence` / `review_status`
- **禁止** 220 直接跳 6935；每阶 `can_promote_next=true` 才升阶

## 评分脚本

| 脚本 | 作用 |
|------|------|
| `score_personality.py` | 情绪/语气/专属表达/人格一致性 |
| `score_relationship.py` | relationship_stage + my_attitude |
| `score_strategy.py` | 12 类策略 + confidence |
| `score_lora.py` | 营养分层、时序权重、Alpaca 校验 |

## 参考

- `references/source_evidence_map.md`
- `references/pipeline_rules.md`
- `references/contact_universe_spec.md`
- `references/lora_rules.md`
- `templates/`
- `examples/`
