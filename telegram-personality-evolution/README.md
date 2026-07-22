# Telegram 人格演化分析系统 
# Telegram Personality Evolution Analysis System

<div align="center">

**按月份深度分析 Telegram 私聊数据，追踪人格演化轨迹，生成 LoRA 训练数据集**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[简体中文](README.md) | [English](README_EN.md) | [Tiếng Việt](README_VI.md)

</div>

---

## 📖 项目简介

Telegram 人格演化分析系统是一个综合性数据分析工具链，用于：

- 📊 **月度分析**：按月份独立分析 Telegram 私聊数据（2022-01 至 2026-07）
- 👤 **联系人画像**：构建全覆盖联系人宇宙（~7988 人）
- 🧠 **人格评分**：多维度人格、关系、策略评分系统
- 🎓 **训练数据**：生成高质量 Alpaca 格式 LoRA 训练集
- 📈 **演化追踪**：四年人格成长轨迹分析
- 🔍 **深度分析**：≤100 条消息优先 + 高价值联系人专项分析
- 🤖 **AI 集成**：Qwen Deep 模型集成，阶梯式扩量（220→1000→2500→6935）

---

## 🎯 核心特性

### 1. 数据处理管道

```
原始数据 → 清洗 → 上下文分析 → 特征提取 → 标签生成 → 训练集
```

- ✅ **智能清洗**：过滤无效消息（empty_media, service, invalid）
- ✅ **上下文理解**：30-60秒窗口消息压缩
- ✅ **隔离处理**：按单客户/单对话切分，禁止混客户
- ✅ **真人化表达**：短句优先（15-30字），自然口语化

### 2. 人格分析维度

| 维度 | 指标 | 说明 |
|------|------|------|
| 人格 | 情绪/语气/专属表达/一致性 | `score_personality.py` |
| 关系 | relationship_stage + my_attitude | `score_relationship.py` |
| 策略 | 12类策略 + confidence | `score_strategy.py` |
| LoRA | 营养分层/时序权重/Alpaca校验 | `score_lora.py` |

### 3. 联系人全覆盖

- **不过滤汇旺/靓号** - 保留所有真实联系人
- **价值分层** - 根据消息数和价值星级分类
- **深分析优先** - `valid_message_count <= 100` 或 `stars >= 3`
- **全员策略** - 所有联系人都生成12类策略（含低样本）

### 4. Qwen Deep 阶梯扩量

```
规则版(只读保留) → Qwen Deep 220 → 1000 → 2500 → 6935
```

- ✅ **门禁机制**：重复率/幻觉/一致性/稳定性检测
- ✅ **证据链**：fact_basis + inference + insufficient_evidence
- ✅ **低样本保护**：≤5条强制低置信 + "暂不判断"

---

## 📂 项目结构

```
telegram-personality-evolution/
├── scripts/                    # 脚本文件
│   ├── core/                   # 核心脚本
│   │   ├── month_runner.py    # 月度串行执行器
│   │   ├── build_contact_universe.py  # 联系人宇宙构建
│   │   └── expand_deep_coverage_le100.py  # 深度覆盖扩量
│   ├── analysis/               # 分析脚本
│   │   ├── analyze_chat_modes.py       # 聊天模式分析
│   │   ├── analyze_contacts_50_100.py  # 50-100条消息分析
│   │   ├── analyze_lt300_dialogs.py    # <300条对话分析
│   │   └── audit_*.py                  # 审计脚本
│   ├── training/               # 训练数据生成
│   │   ├── refine_conversation_1_1.py  # 对话精简 v1.1
│   │   ├── refine_conversation_1_2.py  # 对话压缩 v1.2
│   │   ├── extract_standard_qa_2_1.py  # 标准QA提取
│   │   ├── extract_golden_qa_4_1.py    # 黄金QA提取
│   │   ├── prepare_training_data.py    # 训练数据准备
│   │   └── prepare_siliconflow_finetune.py  # SiliconFlow微调准备
│   ├── evaluation/             # 评估脚本
│   │   ├── score_personality.py        # 人格评分
│   │   ├── score_relationship.py       # 关系评分
│   │   ├── score_strategy.py           # 策略评分
│   │   ├── score_lora.py               # LoRA质量评分
│   │   └── eval_rule_vs_qwen_deep.py  # 规则vs深度评估
│   └── utils/                  # 工具脚本
│       ├── build_knowledge_base.py     # 知识库构建
│       ├── build_person_portraits.py   # 人物画像生成
│       ├── generate_*.py               # 报告生成器
│       ├── check_isolation.py          # 隔离检查
│       └── chat_siliconflow.py         # API聊天
├── docs/                       # 文档
│   ├── SKILL.md               # 技能说明
│   ├── FILTER_DELETE_POLICY.md  # 过滤政策
│   ├── PHASES_4_5_6_INDEX.md   # 阶段索引
│   ├── workflow_template.json   # 工作流模板
│   └── expected_output.json     # 预期输出
├── outputs/                    # 输出目录
│   ├── YYYY-MM/               # 月度输出
│   │   ├── report_YYYY-MM.md
│   │   ├── metrics_YYYY-MM.json
│   │   ├── train_YYYY-MM_alpaca.json
│   │   └── val_YYYY-MM_alpaca.json
│   └── deep_pilot/            # 深度试点
│       └── ladder/            # 阶梯扩量
├── reports/                    # 报告
│   ├── monthly/               # 月度详细总结
│   └── final/                 # 最终演化报告
├── person/                     # 联系人画像（7988份JSON）
├── knowledge/                  # 知识库（全Markdown）
│   ├── personality/
│   ├── relationship/
│   ├── business/
│   ├── emotion/
│   ├── language/
│   ├── strategy/
│   └── lora/
├── state/                      # 运行状态
├── requirements.txt            # Python依赖
├── README.md                   # 本文件
├── README_EN.md               # 英文文档
└── README_VI.md               # 越南语文档
```

---

## 🚀 快速开始

### 环境要求

- Python 3.8+
- 8GB+ RAM（推荐 16GB+）
- 存储空间：20GB+（用于数据和输出）

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd telegram-personality-evolution

# 安装依赖
pip install -r requirements.txt
```

### 基础使用

#### 1. 构建联系人宇宙

```bash
cd scripts
python3 build_contact_universe.py
```

输出：
- `outputs/contact_universe/contact_universe.json` - 全联系人数据
- `outputs/contact_universe/deep_priority_le100.jsonl` - 深分析队列（~7402人）
- `outputs/contact_universe/build_status.json` - 构建状态

#### 2. 月度串行分析

```bash
python3 month_runner.py --from 2022-01 --to 2026-07
```

执行流程：
1. 清洗与上下文分析
2. 人格/关系/策略评分
3. LoRA训练集生成
4. 月度详细总结（22章强制维度）
5. 演化日志追加

#### 3. 生成月度详细总结

```bash
python3 generate_monthly_detailed_summary.py --month 2022-01
```

或批量：
```bash
python3 generate_monthly_detailed_summary.py --from 2022-01 --to 2026-07
```

#### 4. 构建人物画像与知识库

```bash
python3 build_person_portraits.py   # 生成 person/{id}.json ×7988
python3 build_knowledge_base.py     # 生成 knowledge/**/*.md
```

#### 5. Qwen Deep 阶梯扩量

```bash
# 构建抽样样本
python3 run_qwen_deep_ladder.py --build-samples

# 评估220层
python3 run_qwen_deep_ladder.py --eval-tier 220

# 扩量到1000层（需220层门禁通过）
python3 run_qwen_deep_ladder.py --expand-tier 1000 --workers 4

# 继续扩量：2500 → 6935（禁止跳阶）
```

---

## 📋 脚本说明

### 核心执行脚本

| 脚本 | 功能 | 用法 |
|------|------|------|
| `month_runner.py` | 串行月度执行器 | `--from YYYY-MM --to YYYY-MM` |
| `build_contact_universe.py` | 构建联系人全集 | 自动调用管道脚本 |
| `expand_deep_coverage_le100.py` | 扩展深度分析覆盖 | 自动执行 |

### 训练数据模块

| 模块 | 脚本 | 说明 |
|------|------|------|
| 1.1 | `refine_conversation_1_1.py` | 单会话句子合并精简 |
| 1.2 | `refine_conversation_1_2.py` | 30-60s窗口连续消息压缩 |
| 2.1 | `extract_standard_qa_2_1.py` | 标准问答提取 → `knowledge/qa/` |
| 2.2 | `extract_success_context_2_2.py` | 成功上下文提取 |
| 3.1 | `build_multiturn_logic_3_1.py` | 多轮逻辑构建 |
| 4.1 | `extract_golden_qa_4_1.py` | 黄金问答提取 |

### 评分系统

| 脚本 | 评分维度 | 输出字段 |
|------|----------|----------|
| `score_personality.py` | 情绪/语气/专属表达/一致性 | emotion_richness, tone_clarity, fragmentation, coldness |
| `score_relationship.py` | 关系阶段与态度 | relationship_stage, my_attitude |
| `score_strategy.py` | 12类沟通策略 | 12种策略 + confidence |
| `score_lora.py` | LoRA训练质量 | 营养分层, 时序权重 |

### 深度分析

| 脚本 | 功能 | 说明 |
|------|------|------|
| `run_qwen_deep_strategy_pilot.py` | Qwen Deep 策略试点 | 单次执行 |
| `run_qwen_deep_pilot_parallel.py` | 并行深度分析 | 多线程 |
| `run_qwen_deep_ladder.py` | 阶梯扩量主控 | 220→1000→2500→6935 |
| `eval_rule_vs_qwen_deep.py` | 规则vs深度对比 | 门禁评估 |

### 审计与分析

| 脚本 | 用途 |
|------|------|
| `audit_transaction_leakage.py` | 审计会话泄漏 |
| `audit_high_value_opportunities.py` | 高价值机会审计 |
| `analyze_chat_modes.py` | 聊天模式分析 |
| `analyze_contacts_50_100.py` | 50-100条消息专项分析 |
| `analyze_lt300_dialogs.py` | <300条对话分析 |
| `check_isolation.py` | 隔离性检查 |

### 模型与微调

| 脚本 | 功能 |
|------|------|
| `prepare_training_data.py` | 准备通用训练数据 |
| `prepare_siliconflow_finetune.py` | SiliconFlow微调数据准备 |
| `upload_siliconflow_finetune.py` | 上传微调数据集 |
| `merge_lora.py` | 合并LoRA权重 |
| `convert_to_gguf.py` | 转换为GGUF格式 |
| `chat_siliconflow.py` | API聊天测试 |

### 报告生成

| 脚本 | 输出 |
|------|------|
| `generate_full_reports_v2.py` | 完整报告v2 |
| `generate_monthly_detailed_summary.py` | 月度详细总结（22章） |
| `generate_processing_docs.py` | 处理文档 |

### 知识库构建

| 脚本 | 功能 |
|------|------|
| `build_knowledge_base.py` | 全知识库构建 |
| `build_person_portraits.py` | 联系人画像生成 |
| `build_kg_rag_eval_pipeline.py` | KG-RAG评估管道 |

---

## 🔧 配置说明

### 默认路径（根据实际环境修改）

| 角色 | 默认路径 | 说明 |
|------|----------|------|
| 技能根 | 当前目录 | 脚本运行位置 |
| 数据工程产物 | `/Users/home/Downloads/tg_private_4y_monthly` | 主数据管道 |
| 月度任务书 | `/Users/home/Downloads/压缩包/monthly_agent_tasks_2022-2026-07` | 月度配置 |
| 原始导出 | `/Users/home/Downloads/Telegram Lite/聊天记录最新716/result.json` | Telegram导出 |

### 每月必读文件

- `monthly_prompts/YYYY-MM.md` - 月度提示
- `references/pipeline_rules.md` - 管道规则
- `references/monthly_detailed_report_spec.md` - 详细总结规范
- 上月 `outputs/YYYY-MM/metrics_*.json` - 上月指标

---

## 📊 输出格式

### 月度输出（每月）

```
outputs/YYYY-MM/
  ├── report_YYYY-MM.md              # 月度报告
  ├── metrics_YYYY-MM.json           # 指标数据
  ├── train_YYYY-MM_alpaca.json      # 训练集
  ├── val_YYYY-MM_alpaca.json        # 验证集
  └── contact_strategies_YYYY-MM.jsonl  # 联系人策略（可选）

reports/monthly/
  ├── YYYY-MM_personality_summary_detailed.md      # ★ 强制详细总结
  └── YYYY-MM_personality_summary_detailed.meta.json
```

### 最终输出（全部月份完成后）

```
reports/final/
  └── report_2022-01_2026-07_personality_evolution.md  # 四年演化报告

outputs/
  └── long_term_personality_evolution.jsonl  # 演化日志
```

### 联系人画像

```
person/
  ├── {peer_id}.json  # 每人一份，共7988份
  └── _INDEX.json     # 索引
```

每份画像包含：
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

### 知识库

```
knowledge/
  ├── personality/    # 人格知识
  ├── relationship/   # 关系知识
  ├── business/       # 业务知识
  ├── emotion/        # 情感知识
  ├── language/       # 语言风格
  ├── strategy/       # 策略知识
  └── lora/          # LoRA相关
```

全部为 Markdown 格式，Agent 可直接引用。

---

## 🛡️ 核心规则（硬规则，写死）

0. **角色与原则**：资深客户沟通专家 + 数据分析师
1. **分块隔离**：禁止混客户/混场景；按单客户或单次沟通切分
2. **真人化表达**：短句优先（15-30字）、留白转化、自然口语
3. **不过滤联系人，只过滤无效消息**（取消汇旺/靓号联系人级过滤）
4. **全覆盖**：目标联系人全集（~7988人）
5. **深分析**：`valid_message_count <= 100` 或 `stars >= 3`
6. **全员策略**：所有人都生成12类策略（样本少也生成）
7. **禁止使用未来月份信息**
8. **保持原始文本**：入库证据不润色，新写示范句才人话化

---

## 📖 深度分析覆盖

### 当前策略

```
valid_message_count <= 100
  OR value.stars >= 3   # 高价值及以上
→ deep_analysis = true
```

- **主队列**：`06_full_coverage/deep_priority_le100.jsonl`（约 7402 人）
- **兼容队列**：`deep_priority_le50.jsonl`（≤50 子集）

### 消息过滤永久删除政策

以下类别永久删除，禁止恢复：

1. **empty_media** — 无有效文字的纯媒体
2. **service** — 系统服务消息
3. **invalid** — 空文本 / 坏时间 / 无发送者

---

## 🎯 开发阶段

### 第四阶段：联系人画像

- 每联系人一份 JSON（7988份）
- 路径：`person/{peer_id}.json`
- 索引：`person/_INDEX.json`
- **Agent 直接读取，无需重新分析**

### 第五阶段：Qwen Deep 阶梯

```
220 → 1000 → 2500 → 6935
```

- **抽样清单**：`outputs/deep_pilot/ladder/ladder_sample_{N}.json`
- **门禁报告**：`outputs/deep_pilot/ladder/gate_{N}.md`
- **深版策略**：`06_full_coverage/strategies_qwen_deep_v1/by_peer/`

门禁指标：
- 重复率
- 幻觉检测
- 一致性
- 稳定性

`can_promote_next=true` 才允许升下一阶。

### 第六阶段：知识库

- 全 Markdown，Agent 直引
- 同步三处（skill / pipeline / monthly_agent_tasks）
- 稳定引用层

---

## 🧪 测试与验证

### 运行烟雾测试

```bash
# 查看烟雾测试日志
cat docs/run_smoke.log
```

### 验证隔离性

```bash
python3 check_isolation.py
```

### 评估规则vs深度

```bash
python3 eval_rule_vs_qwen_deep.py
```

---

## 📚 参考文档

位于项目根目录和 `docs/` 目录：

- `SKILL.md` - 完整技能说明
- `FILTER_DELETE_POLICY.md` - 过滤策略
- `PHASES_4_5_6_INDEX.md` - 开发阶段索引
- `workflow_template.json` - 工作流模板
- `expected_output.json` - 预期输出格式

---

## ⚠️ 注意事项

1. **数据隐私**：本系统处理个人私聊数据，请确保合规使用
2. **API 配额**：使用 Qwen/SiliconFlow API 需注意配额限制
3. **存储空间**：完整运行需要 20GB+ 存储空间
4. **内存要求**：建议 16GB+ RAM，处理大数据集时可能需要更多
5. **断点续传**：`state/month_runner_state.json` 保存运行状态
6. **串行执行**：月度分析必须串行，禁止并行处理不同月份

---

## 🤝 贡献指南

本项目为数据分析工具链，欢迎提交：

- Bug 报告
- 功能改进建议
- 文档完善
- 性能优化

---

## 📄 许可证

MIT License

---

## 📞 联系方式

如有问题或建议，请提交 Issue。

---

## 🎯 项目状态

**✅ 完整可用 / FULLY FUNCTIONAL**

- ✅ 35 个 Python 脚本
- ✅ 完整文档
- ✅ 月度分析管道
- ✅ 人格评分系统
- ✅ LoRA 训练集生成
- ✅ Qwen Deep 集成
- ✅ 知识库构建

---

**更新时间**: 2026-07-22  
**版本**: v1.0
