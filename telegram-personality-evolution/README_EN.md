# Telegram Personality Evolution Analysis System

<div align="center">

**Monthly deep analysis of Telegram private chat data, tracking personality evolution trajectories, generating LoRA training datasets**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[简体中文](README.md) | [English](README_EN.md) | [Tiếng Việt](README_VI.md)

</div>

---

## 📖 Project Overview

Telegram Personality Evolution Analysis System is a comprehensive data analysis toolkit designed for:

- 📊 **Monthly Analysis**: Independent monthly analysis of Telegram private chat data (2022-01 to 2026-07)
- 👤 **Contact Profiles**: Build full-coverage contact universe (~7988 people)
- 🧠 **Personality Scoring**: Multi-dimensional personality, relationship, and strategy scoring system
- 🎓 **Training Data**: Generate high-quality Alpaca format LoRA training sets
- 📈 **Evolution Tracking**: Four-year personality growth trajectory analysis
- 🔍 **Deep Analysis**: Priority for ≤100 messages + high-value contact specialized analysis
- 🤖 **AI Integration**: Qwen Deep model integration, ladder-style expansion (220→1000→2500→6935)

---

## 🎯 Core Features

### 1. Data Processing Pipeline

```
Raw Data → Cleaning → Context Analysis → Feature Extraction → Tagging → Training Set
```

- ✅ **Smart Cleaning**: Filter invalid messages (empty_media, service, invalid)
- ✅ **Context Understanding**: 30-60 second window message compression
- ✅ **Isolated Processing**: Split by single customer/single dialog, no customer mixing
- ✅ **Humanized Expression**: Short sentences first (15-30 chars), natural colloquial

### 2. Personality Analysis Dimensions

| Dimension | Metrics | Script |
|-----------|---------|--------|
| Personality | Emotion/Tone/Unique Expression/Consistency | `score_personality.py` |
| Relationship | relationship_stage + my_attitude | `score_relationship.py` |
| Strategy | 12 types of strategies + confidence | `score_strategy.py` |
| LoRA | Nutritional stratification/Temporal weights/Alpaca validation | `score_lora.py` |

### 3. Full Contact Coverage

- **No filtering of premium numbers** - Retain all real contacts
- **Value stratification** - Classify by message count and value stars
- **Deep analysis priority** - `valid_message_count <= 100` or `stars >= 3`
- **Full strategy** - Generate 12 types of strategies for all contacts (including low samples)

### 4. Qwen Deep Ladder Expansion

```
Rule-based (read-only) → Qwen Deep 220 → 1000 → 2500 → 6935
```

- ✅ **Gate mechanism**: Repetition rate/Hallucination/Consistency/Stability detection
- ✅ **Evidence chain**: fact_basis + inference + insufficient_evidence
- ✅ **Low sample protection**: ≤5 messages force low confidence + "temporarily withheld"

---

## 📂 Project Structure

```
telegram-personality-evolution/
├── scripts/                    # Script files
│   ├── core/                   # Core scripts
│   ├── analysis/               # Analysis scripts
│   ├── training/               # Training data generation
│   ├── evaluation/             # Evaluation scripts
│   └── utils/                  # Utility scripts
├── docs/                       # Documentation
├── outputs/                    # Output directory
│   ├── YYYY-MM/               # Monthly outputs
│   └── deep_pilot/            # Deep pilot
├── reports/                    # Reports
│   ├── monthly/               # Monthly summaries
│   └── final/                 # Final evolution report
├── person/                     # Contact profiles (7988 JSON files)
├── knowledge/                  # Knowledge base (all Markdown)
├── state/                      # Runtime state
└── requirements.txt            # Python dependencies
```

---

## 🚀 Quick Start

### Requirements

- Python 3.8+
- 8GB+ RAM (16GB+ recommended)
- Storage: 20GB+ (for data and outputs)

### Installation

```bash
# Clone the project
git clone <repository-url>
cd telegram-personality-evolution

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

#### 1. Build Contact Universe

```bash
cd scripts
python3 build_contact_universe.py
```

Outputs:
- `outputs/contact_universe/contact_universe.json` - All contact data
- `outputs/contact_universe/deep_priority_le100.jsonl` - Deep analysis queue (~7402 people)
- `outputs/contact_universe/build_status.json` - Build status

#### 2. Monthly Serial Analysis

```bash
python3 month_runner.py --from 2022-01 --to 2026-07
```

Execution flow:
1. Cleaning and context analysis
2. Personality/Relationship/Strategy scoring
3. LoRA training set generation
4. Monthly detailed summary (22 mandatory chapters)
5. Evolution log append

#### 3. Generate Monthly Detailed Summary

```bash
python3 generate_monthly_detailed_summary.py --month 2022-01
```

Or batch:
```bash
python3 generate_monthly_detailed_summary.py --from 2022-01 --to 2026-07
```

#### 4. Build Person Portraits and Knowledge Base

```bash
python3 build_person_portraits.py   # Generate person/{id}.json ×7988
python3 build_knowledge_base.py     # Generate knowledge/**/*.md
```

#### 5. Qwen Deep Ladder Expansion

```bash
# Build sample samples
python3 run_qwen_deep_ladder.py --build-samples

# Evaluate 220 tier
python3 run_qwen_deep_ladder.py --eval-tier 220

# Expand to 1000 tier (requires 220 gate pass)
python3 run_qwen_deep_ladder.py --expand-tier 1000 --workers 4

# Continue expansion: 2500 → 6935 (no skipping tiers)
```

---

## 📋 Script Descriptions

### Core Execution Scripts

| Script | Function | Usage |
|--------|----------|-------|
| `month_runner.py` | Serial monthly executor | `--from YYYY-MM --to YYYY-MM` |
| `build_contact_universe.py` | Build full contact set | Automatically calls pipeline scripts |
| `expand_deep_coverage_le100.py` | Expand deep analysis coverage | Auto-execute |

### Training Data Modules

| Module | Script | Description |
|--------|--------|-------------|
| 1.1 | `refine_conversation_1_1.py` | Single session sentence merge and simplification |
| 1.2 | `refine_conversation_1_2.py` | 30-60s window continuous message compression |
| 2.1 | `extract_standard_qa_2_1.py` | Standard Q&A extraction → `knowledge/qa/` |
| 2.2 | `extract_success_context_2_2.py` | Success context extraction |
| 3.1 | `build_multiturn_logic_3_1.py` | Multi-turn logic construction |
| 4.1 | `extract_golden_qa_4_1.py` | Golden Q&A extraction |

### Scoring System

| Script | Scoring Dimension | Output Fields |
|--------|-------------------|---------------|
| `score_personality.py` | Emotion/Tone/Unique Expression/Consistency | emotion_richness, tone_clarity, fragmentation, coldness |
| `score_relationship.py` | Relationship stage and attitude | relationship_stage, my_attitude |
| `score_strategy.py` | 12 types of communication strategies | 12 strategies + confidence |
| `score_lora.py` | LoRA training quality | Nutritional stratification, temporal weights |

### Deep Analysis

| Script | Function | Description |
|--------|----------|-------------|
| `run_qwen_deep_strategy_pilot.py` | Qwen Deep strategy pilot | Single execution |
| `run_qwen_deep_pilot_parallel.py` | Parallel deep analysis | Multi-threaded |
| `run_qwen_deep_ladder.py` | Ladder expansion master control | 220→1000→2500→6935 |
| `eval_rule_vs_qwen_deep.py` | Rule vs deep comparison | Gate evaluation |

### Audit and Analysis

| Script | Purpose |
|--------|---------|
| `audit_transaction_leakage.py` | Audit session leakage |
| `audit_high_value_opportunities.py` | High-value opportunity audit |
| `analyze_chat_modes.py` | Chat mode analysis |
| `analyze_contacts_50_100.py` | 50-100 message specialized analysis |
| `analyze_lt300_dialogs.py` | <300 dialog analysis |
| `check_isolation.py` | Isolation check |

### Model and Fine-tuning

| Script | Function |
|--------|----------|
| `prepare_training_data.py` | Prepare general training data |
| `prepare_siliconflow_finetune.py` | SiliconFlow fine-tuning data preparation |
| `upload_siliconflow_finetune.py` | Upload fine-tuning dataset |
| `merge_lora.py` | Merge LoRA weights |
| `convert_to_gguf.py` | Convert to GGUF format |
| `chat_siliconflow.py` | API chat test |

### Report Generation

| Script | Output |
|--------|--------|
| `generate_full_reports_v2.py` | Full report v2 |
| `generate_monthly_detailed_summary.py` | Monthly detailed summary (22 chapters) |
| `generate_processing_docs.py` | Processing documentation |

### Knowledge Base Construction

| Script | Function |
|--------|----------|
| `build_knowledge_base.py` | Full knowledge base construction |
| `build_person_portraits.py` | Contact profile generation |
| `build_kg_rag_eval_pipeline.py` | KG-RAG evaluation pipeline |

---

## 🔧 Configuration

### Default Paths (Modify according to actual environment)

| Role | Default Path | Description |
|------|--------------|-------------|
| Skill root | Current directory | Script run location |
| Data engineering artifacts | `/Users/home/Downloads/tg_private_4y_monthly` | Main data pipeline |
| Monthly task book | `/Users/home/Downloads/压缩包/monthly_agent_tasks_2022-2026-07` | Monthly config |
| Original export | `/Users/home/Downloads/Telegram Lite/聊天记录最新716/result.json` | Telegram export |

### Monthly Required Files

- `monthly_prompts/YYYY-MM.md` - Monthly prompts
- `references/pipeline_rules.md` - Pipeline rules
- `references/monthly_detailed_report_spec.md` - Detailed summary specification
- Previous month `outputs/YYYY-MM/metrics_*.json` - Previous month metrics

---

## 📊 Output Format

### Monthly Output (Each Month)

```
outputs/YYYY-MM/
  ├── report_YYYY-MM.md              # Monthly report
  ├── metrics_YYYY-MM.json           # Metrics data
  ├── train_YYYY-MM_alpaca.json      # Training set
  ├── val_YYYY-MM_alpaca.json        # Validation set
  └── contact_strategies_YYYY-MM.jsonl  # Contact strategies (optional)

reports/monthly/
  ├── YYYY-MM_personality_summary_detailed.md      # ★ Mandatory detailed summary
  └── YYYY-MM_personality_summary_detailed.meta.json
```

### Final Output (After All Months Complete)

```
reports/final/
  └── report_2022-01_2026-07_personality_evolution.md  # Four-year evolution report

outputs/
  └── long_term_personality_evolution.jsonl  # Evolution log
```

### Contact Profiles

```
person/
  ├── {peer_id}.json  # One per person, 7988 total
  └── _INDEX.json     # Index
```

Each profile contains:
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

### Knowledge Base

```
knowledge/
  ├── personality/    # Personality knowledge
  ├── relationship/   # Relationship knowledge
  ├── business/       # Business knowledge
  ├── emotion/        # Emotion knowledge
  ├── language/       # Language style
  ├── strategy/       # Strategy knowledge
  └── lora/          # LoRA related
```

All in Markdown format, directly referenceable by Agent.

---

## 🛡️ Core Rules (Hard Rules, Hardcoded)

0. **Role and Principles**: Senior customer communication expert + data analyst
1. **Block Isolation**: No customer mixing/scene mixing; split by single customer or single communication
2. **Humanized Expression**: Short sentences first (15-30 chars), white space conversion, natural colloquial
3. **No contact filtering, only filter invalid messages** (Cancel premium number contact-level filtering)
4. **Full coverage**: Target contact full set (~7988 people)
5. **Deep analysis**: `valid_message_count <= 100` or `stars >= 3`
6. **Full strategy**: All people generate 12 types of strategies (even with few samples)
7. **No use of future month information**
8. **Preserve original text**: Don't polish evidence for storage, only humanize example sentences

---

## 📖 Deep Analysis Coverage

### Current Strategy

```
valid_message_count <= 100
  OR value.stars >= 3   # High value and above
→ deep_analysis = true
```

- **Main queue**: `06_full_coverage/deep_priority_le100.jsonl` (about 7402 people)
- **Compatible queue**: `deep_priority_le50.jsonl` (≤50 subset)

### Message Filter Permanent Deletion Policy

The following categories are permanently deleted, no recovery:

1. **empty_media** — Pure media with no valid text
2. **service** — System service messages
3. **invalid** — Empty text / bad time / no sender

---

## 🎯 Development Phases

### Phase 4: Contact Profiles

- One JSON per contact (7988 files)
- Path: `person/{peer_id}.json`
- Index: `person/_INDEX.json`
- **Agent reads directly, no need to re-analyze**

### Phase 5: Qwen Deep Ladder

```
220 → 1000 → 2500 → 6935
```

- **Sample list**: `outputs/deep_pilot/ladder/ladder_sample_{N}.json`
- **Gate report**: `outputs/deep_pilot/ladder/gate_{N}.md`
- **Deep strategy**: `06_full_coverage/strategies_qwen_deep_v1/by_peer/`

Gate metrics:
- Repetition rate
- Hallucination detection
- Consistency
- Stability

`can_promote_next=true` allows promotion to next tier.

### Phase 6: Knowledge Base

- All Markdown, directly referenced by Agent
- Synced to three locations (skill / pipeline / monthly_agent_tasks)
- Stable reference layer

---

## 🧪 Testing and Validation

### Run Smoke Test

```bash
# View smoke test log
cat docs/run_smoke.log
```

### Verify Isolation

```bash
python3 check_isolation.py
```

### Evaluate Rule vs Deep

```bash
python3 eval_rule_vs_qwen_deep.py
```

---

## 📚 Reference Documentation

Located in project root and `docs/` directory:

- `SKILL.md` - Complete skill description
- `FILTER_DELETE_POLICY.md` - Filter policy
- `PHASES_4_5_6_INDEX.md` - Development phase index
- `workflow_template.json` - Workflow template
- `expected_output.json` - Expected output format

---

## ⚠️ Important Notes

1. **Data Privacy**: This system processes personal private chat data, ensure compliant use
2. **API Quota**: Using Qwen/SiliconFlow API requires attention to quota limits
3. **Storage Space**: Full run requires 20GB+ storage
4. **Memory Requirements**: Recommend 16GB+ RAM, may need more for large datasets
5. **Checkpoint Resume**: `state/month_runner_state.json` saves run state
6. **Serial Execution**: Monthly analysis must be serial, no parallel processing of different months

---

## 🤝 Contributing

This project is a data analysis toolkit, welcome to submit:

- Bug reports
- Feature improvement suggestions
- Documentation enhancements
- Performance optimizations

---

## 📄 License

MIT License

---

## 📞 Contact

For questions or suggestions, please submit an Issue.

---

## 🎯 Project Status

**✅ FULLY FUNCTIONAL**

- ✅ 35 Python scripts
- ✅ Complete documentation
- ✅ Monthly analysis pipeline
- ✅ Personality scoring system
- ✅ LoRA training set generation
- ✅ Qwen Deep integration
- ✅ Knowledge base construction

---

**Last Updated**: 2026-07-22  
**Version**: v1.0
