# 第四～六阶段交付索引

生成时间：见各产物 `_INDEX` / gate 报告。

## 第四阶段 · 联系人画像 `person/`

每联系人一份 JSON（7988）：

```json
{
  "peer_id": "...",
  "relationship": "...",
  "trust": "...",
  "business": "...",
  "emotion": "...",
  "strategy": "...",
  "risk": "..."
}
```

同步目录：

- `/Users/home/Downloads/tg_private_4y_monthly/person/`
- `/Users/home/Downloads/压缩包/skills/telegram-personality-evolution/person/`
- `/Users/home/Downloads/压缩包/monthly_agent_tasks_2022-2026-07/person/`

索引：`person/_INDEX.json`

Agent：**直接读取，无需重新分析。**

---

## 第五阶段 · Qwen Deep 阶梯

```
220 → 1000 → 2500 → 6935
```

| 产物 | 路径 |
|------|------|
| 抽样清单 | `outputs/deep_pilot/ladder/ladder_sample_{N}.json` |
| 门禁报告 | `outputs/deep_pilot/ladder/gate_{N}.md` |
| 状态 | `outputs/deep_pilot/ladder/ladder_state.json` |
| 深版策略 | `06_full_coverage/strategies_qwen_deep_v1/by_peer/` |

门禁看：重复率、幻觉、一致性、稳定性。  
`can_promote_next=true` 才允许升下一阶。

当前：220 已 `promote_next_tier`；1000 扩量进行中（见 `expand_1000.log`）。

---

## 第六阶段 · 知识库 `knowledge/`

全 Markdown，Agent 直引：

```
knowledge/
  personality/
  relationship/
  business/
  emotion/
  language/
  strategy/
  lora/
```

同步三处（skill / pipeline / monthly_agent_tasks）。

Markdown / JSON / Tag / Weight 可继续调；知识库与 person 为稳定引用层。

---

## 常用命令

```bash
cd "/Users/home/Downloads/压缩包/skills/telegram-personality-evolution"
python3 build_person_portraits.py
python3 build_knowledge_base.py
python3 run_qwen_deep_ladder.py --eval-tier 1000
python3 run_qwen_deep_ladder.py --expand-tier 2500 --workers 4   # 仅当 1000 门禁通过
```
