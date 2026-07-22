# Hệ thống Phân tích Tiến hóa Tính cách Telegram

<div align="center">

**Phân tích sâu dữ liệu trò chuyện riêng Telegram theo tháng, theo dõi quỹ đạo tiến hóa tính cách, tạo tập dữ liệu huấn luyện LoRA**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

[简体中文](README.md) | [English](README_EN.md) | [Tiếng Việt](README_VI.md)

</div>

---

## 📖 Tổng quan Dự án

Hệ thống Phân tích Tiến hóa Tính cách Telegram là bộ công cụ phân tích dữ liệu toàn diện được thiết kế cho:

- 📊 **Phân tích Hàng tháng**: Phân tích độc lập hàng tháng dữ liệu trò chuyện riêng Telegram (2022-01 đến 2026-07)
- 👤 **Hồ sơ Liên hệ**: Xây dựng vũ trụ liên hệ đầy đủ (~7988 người)
- 🧠 **Chấm điểm Tính cách**: Hệ thống chấm điểm tính cách, mối quan hệ và chiến lược đa chiều
- 🎓 **Dữ liệu Huấn luyện**: Tạo bộ huấn luyện LoRA định dạng Alpaca chất lượng cao
- 📈 **Theo dõi Tiến hóa**: Phân tích quỹ đạo tăng trưởng tính cách bốn năm
- 🔍 **Phân tích Sâu**: Ưu tiên cho ≤100 tin nhắn + phân tích chuyên biệt liên hệ giá trị cao
- 🤖 **Tích hợp AI**: Tích hợp mô hình Qwen Deep, mở rộng theo bậc thang (220→1000→2500→6935)

---

## 🎯 Tính năng Cốt lõi

### 1. Pipeline Xử lý Dữ liệu

```
Dữ liệu Thô → Làm sạch → Phân tích Ngữ cảnh → Trích xuất Đặc trưng → Gắn thẻ → Tập Huấn luyện
```

- ✅ **Làm sạch Thông minh**: Lọc tin nhắn không hợp lệ (empty_media, service, invalid)
- ✅ **Hiểu Ngữ cảnh**: Nén tin nhắn cửa sổ 30-60 giây
- ✅ **Xử lý Cô lập**: Tách theo khách hàng đơn lẻ/hội thoại đơn lẻ, không trộn khách hàng
- ✅ **Biểu hiện Nhân bản hóa**: Câu ngắn ưu tiên (15-30 ký tự), ngôn ngữ nói tự nhiên

### 2. Chiều Phân tích Tính cách

| Chiều | Chỉ số | Script |
|-------|--------|--------|
| Tính cách | Cảm xúc/Giọng điệu/Biểu hiện Độc đáo/Nhất quán | `score_personality.py` |
| Mối quan hệ | relationship_stage + my_attitude | `score_relationship.py` |
| Chiến lược | 12 loại chiến lược + độ tin cậy | `score_strategy.py` |
| LoRA | Phân tầng dinh dưỡng/Trọng số thời gian/Xác thực Alpaca | `score_lora.py` |

### 3. Bao phủ Liên hệ Đầy đủ

- **Không lọc số cao cấp** - Giữ lại tất cả liên hệ thực
- **Phân tầng giá trị** - Phân loại theo số lượng tin nhắn và sao giá trị
- **Ưu tiên phân tích sâu** - `valid_message_count <= 100` hoặc `stars >= 3`
- **Chiến lược đầy đủ** - Tạo 12 loại chiến lược cho tất cả liên hệ (bao gồm mẫu thấp)

### 4. Mở rộng Bậc thang Qwen Deep

```
Dựa trên quy tắc (chỉ đọc) → Qwen Deep 220 → 1000 → 2500 → 6935
```

- ✅ **Cơ chế cổng**: Phát hiện tỷ lệ lặp lại/Ảo giác/Nhất quán/Ổn định
- ✅ **Chuỗi bằng chứng**: fact_basis + inference + insufficient_evidence
- ✅ **Bảo vệ mẫu thấp**: ≤5 tin nhắn buộc độ tin cậy thấp + "tạm giữ"

---

## 📂 Cấu trúc Dự án

```
telegram-personality-evolution/
├── scripts/                    # Tệp script
│   ├── core/                   # Script cốt lõi
│   ├── analysis/               # Script phân tích
│   ├── training/               # Tạo dữ liệu huấn luyện
│   ├── evaluation/             # Script đánh giá
│   └── utils/                  # Script tiện ích
├── docs/                       # Tài liệu
├── outputs/                    # Thư mục đầu ra
│   ├── YYYY-MM/               # Đầu ra hàng tháng
│   └── deep_pilot/            # Thử nghiệm sâu
├── reports/                    # Báo cáo
│   ├── monthly/               # Tóm tắt hàng tháng
│   └── final/                 # Báo cáo tiến hóa cuối cùng
├── person/                     # Hồ sơ liên hệ (7988 tệp JSON)
├── knowledge/                  # Cơ sở kiến thức (tất cả Markdown)
├── state/                      # Trạng thái runtime
└── requirements.txt            # Phụ thuộc Python
```

---

## 🚀 Bắt đầu Nhanh

### Yêu cầu

- Python 3.8+
- RAM 8GB+ (khuyến nghị 16GB+)
- Lưu trữ: 20GB+ (cho dữ liệu và đầu ra)

### Cài đặt

```bash
# Sao chép dự án
git clone <repository-url>
cd telegram-personality-evolution

# Cài đặt phụ thuộc
pip install -r requirements.txt
```

### Sử dụng Cơ bản

#### 1. Xây dựng Vũ trụ Liên hệ

```bash
cd scripts
python3 build_contact_universe.py
```

Đầu ra:
- `outputs/contact_universe/contact_universe.json` - Tất cả dữ liệu liên hệ
- `outputs/contact_universe/deep_priority_le100.jsonl` - Hàng đợi phân tích sâu (~7402 người)
- `outputs/contact_universe/build_status.json` - Trạng thái xây dựng

#### 2. Phân tích Nối tiếp Hàng tháng

```bash
python3 month_runner.py --from 2022-01 --to 2026-07
```

Luồng thực thi:
1. Làm sạch và phân tích ngữ cảnh
2. Chấm điểm Tính cách/Mối quan hệ/Chiến lược
3. Tạo tập huấn luyện LoRA
4. Tóm tắt chi tiết hàng tháng (22 chương bắt buộc)
5. Thêm nhật ký tiến hóa

#### 3. Tạo Tóm tắt Chi tiết Hàng tháng

```bash
python3 generate_monthly_detailed_summary.py --month 2022-01
```

Hoặc hàng loạt:
```bash
python3 generate_monthly_detailed_summary.py --from 2022-01 --to 2026-07
```

#### 4. Xây dựng Chân dung Người và Cơ sở Kiến thức

```bash
python3 build_person_portraits.py   # Tạo person/{id}.json ×7988
python3 build_knowledge_base.py     # Tạo knowledge/**/*.md
```

#### 5. Mở rộng Bậc thang Qwen Deep

```bash
# Xây dựng mẫu lấy mẫu
python3 run_qwen_deep_ladder.py --build-samples

# Đánh giá bậc 220
python3 run_qwen_deep_ladder.py --eval-tier 220

# Mở rộng đến bậc 1000 (yêu cầu cổng bậc 220 vượt qua)
python3 run_qwen_deep_ladder.py --expand-tier 1000 --workers 4

# Tiếp tục mở rộng: 2500 → 6935 (không bỏ qua bậc)
```

---

## 📋 Mô tả Script

### Script Thực thi Cốt lõi

| Script | Chức năng | Sử dụng |
|--------|-----------|---------|
| `month_runner.py` | Trình thực thi nối tiếp hàng tháng | `--from YYYY-MM --to YYYY-MM` |
| `build_contact_universe.py` | Xây dựng tập liên hệ đầy đủ | Tự động gọi script pipeline |
| `expand_deep_coverage_le100.py` | Mở rộng bao phủ phân tích sâu | Tự động thực thi |

### Mô-đun Dữ liệu Huấn luyện

| Mô-đun | Script | Mô tả |
|--------|--------|-------|
| 1.1 | `refine_conversation_1_1.py` | Hợp nhất và đơn giản hóa câu phiên đơn lẻ |
| 1.2 | `refine_conversation_1_2.py` | Nén tin nhắn liên tục cửa sổ 30-60s |
| 2.1 | `extract_standard_qa_2_1.py` | Trích xuất Q&A tiêu chuẩn → `knowledge/qa/` |
| 2.2 | `extract_success_context_2_2.py` | Trích xuất ngữ cảnh thành công |
| 3.1 | `build_multiturn_logic_3_1.py` | Xây dựng logic nhiều lượt |
| 4.1 | `extract_golden_qa_4_1.py` | Trích xuất Q&A vàng |

### Hệ thống Chấm điểm

| Script | Chiều Chấm điểm | Trường Đầu ra |
|--------|-----------------|---------------|
| `score_personality.py` | Cảm xúc/Giọng điệu/Biểu hiện Độc đáo/Nhất quán | emotion_richness, tone_clarity, fragmentation, coldness |
| `score_relationship.py` | Giai đoạn mối quan hệ và thái độ | relationship_stage, my_attitude |
| `score_strategy.py` | 12 loại chiến lược giao tiếp | 12 chiến lược + độ tin cậy |
| `score_lora.py` | Chất lượng huấn luyện LoRA | Phân tầng dinh dưỡng, trọng số thời gian |

### Phân tích Sâu

| Script | Chức năng | Mô tả |
|--------|-----------|-------|
| `run_qwen_deep_strategy_pilot.py` | Thử nghiệm chiến lược Qwen Deep | Thực thi đơn lẻ |
| `run_qwen_deep_pilot_parallel.py` | Phân tích sâu song song | Đa luồng |
| `run_qwen_deep_ladder.py` | Điều khiển chính mở rộng bậc thang | 220→1000→2500→6935 |
| `eval_rule_vs_qwen_deep.py` | So sánh quy tắc vs sâu | Đánh giá cổng |

---

## 🔧 Cấu hình

### Đường dẫn Mặc định (Sửa đổi theo môi trường thực tế)

| Vai trò | Đường dẫn Mặc định | Mô tả |
|---------|-------------------|-------|
| Gốc kỹ năng | Thư mục hiện tại | Vị trí chạy script |
| Sản phẩm kỹ thuật dữ liệu | `/Users/home/Downloads/tg_private_4y_monthly` | Pipeline dữ liệu chính |
| Sổ nhiệm vụ hàng tháng | `/Users/home/Downloads/压缩包/monthly_agent_tasks_2022-2026-07` | Cấu hình hàng tháng |
| Xuất gốc | `/Users/home/Downloads/Telegram Lite/聊天记录最新716/result.json` | Xuất Telegram |

---

## 📊 Định dạng Đầu ra

### Đầu ra Hàng tháng (Mỗi Tháng)

```
outputs/YYYY-MM/
  ├── report_YYYY-MM.md              # Báo cáo hàng tháng
  ├── metrics_YYYY-MM.json           # Dữ liệu chỉ số
  ├── train_YYYY-MM_alpaca.json      # Tập huấn luyện
  ├── val_YYYY-MM_alpaca.json        # Tập xác thực
  └── contact_strategies_YYYY-MM.jsonl  # Chiến lược liên hệ (tùy chọn)

reports/monthly/
  ├── YYYY-MM_personality_summary_detailed.md      # ★ Tóm tắt chi tiết bắt buộc
  └── YYYY-MM_personality_summary_detailed.meta.json
```

### Đầu ra Cuối cùng (Sau Khi Hoàn thành Tất cả Tháng)

```
reports/final/
  └── report_2022-01_2026-07_personality_evolution.md  # Báo cáo tiến hóa bốn năm

outputs/
  └── long_term_personality_evolution.jsonl  # Nhật ký tiến hóa
```

### Hồ sơ Liên hệ

```
person/
  ├── {peer_id}.json  # Một mỗi người, tổng cộng 7988
  └── _INDEX.json     # Chỉ mục
```

Mỗi hồ sơ chứa:
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

### Cơ sở Kiến thức

```
knowledge/
  ├── personality/    # Kiến thức tính cách
  ├── relationship/   # Kiến thức mối quan hệ
  ├── business/       # Kiến thức kinh doanh
  ├── emotion/        # Kiến thức cảm xúc
  ├── language/       # Phong cách ngôn ngữ
  ├── strategy/       # Kiến thức chiến lược
  └── lora/          # Liên quan đến LoRA
```

Tất cả định dạng Markdown, có thể tham chiếu trực tiếp bởi Agent.

---

## 🛡️ Quy tắc Cốt lõi (Quy tắc Cứng, Mã hóa cứng)

0. **Vai trò và Nguyên tắc**: Chuyên gia giao tiếp khách hàng cao cấp + nhà phân tích dữ liệu
1. **Cô lập Khối**: Không trộn khách hàng/trộn cảnh; tách theo khách hàng đơn lẻ hoặc giao tiếp đơn lẻ
2. **Biểu hiện Nhân bản hóa**: Câu ngắn ưu tiên (15-30 ký tự), chuyển đổi khoảng trắng, ngôn ngữ nói tự nhiên
3. **Không lọc liên hệ, chỉ lọc tin nhắn không hợp lệ** (Hủy lọc cấp liên hệ số cao cấp)
4. **Bao phủ đầy đủ**: Tập liên hệ mục tiêu đầy đủ (~7988 người)
5. **Phân tích sâu**: `valid_message_count <= 100` hoặc `stars >= 3`
6. **Chiến lược đầy đủ**: Tất cả mọi người tạo 12 loại chiến lược (ngay cả với mẫu ít)
7. **Không sử dụng thông tin tháng tương lai**
8. **Bảo tồn văn bản gốc**: Không đánh bóng bằng chứng để lưu trữ, chỉ nhân bản hóa câu ví dụ

---

## 🧪 Kiểm tra và Xác thực

### Chạy Kiểm tra Khói

```bash
# Xem nhật ký kiểm tra khói
cat docs/run_smoke.log
```

### Xác minh Cô lập

```bash
python3 check_isolation.py
```

### Đánh giá Quy tắc vs Sâu

```bash
python3 eval_rule_vs_qwen_deep.py
```

---

## 📚 Tài liệu Tham khảo

Nằm trong gốc dự án và thư mục `docs/`:

- `SKILL.md` - Mô tả kỹ năng hoàn chỉnh
- `FILTER_DELETE_POLICY.md` - Chính sách lọc
- `PHASES_4_5_6_INDEX.md` - Chỉ mục giai đoạn phát triển
- `workflow_template.json` - Mẫu quy trình làm việc
- `expected_output.json` - Định dạng đầu ra mong đợi

---

## ⚠️ Lưu ý Quan trọng

1. **Quyền riêng tư Dữ liệu**: Hệ thống này xử lý dữ liệu trò chuyện riêng cá nhân, đảm bảo sử dụng tuân thủ
2. **Hạn ngạch API**: Sử dụng API Qwen/SiliconFlow yêu cầu chú ý đến giới hạn hạn ngạch
3. **Không gian Lưu trữ**: Chạy đầy đủ yêu cầu lưu trữ 20GB+
4. **Yêu cầu Bộ nhớ**: Khuyến nghị RAM 16GB+, có thể cần nhiều hơn cho tập dữ liệu lớn
5. **Tiếp tục Checkpoint**: `state/month_runner_state.json` lưu trạng thái chạy
6. **Thực thi Nối tiếp**: Phân tích hàng tháng phải nối tiếp, không xử lý song song các tháng khác nhau

---

## 🤝 Đóng góp

Dự án này là bộ công cụ phân tích dữ liệu, hoan nghênh gửi:

- Báo cáo lỗi
- Đề xuất cải tiến tính năng
- Cải thiện tài liệu
- Tối ưu hóa hiệu suất

---

## 📄 Giấy phép

Giấy phép MIT

---

## 📞 Liên hệ

Đối với câu hỏi hoặc đề xuất, vui lòng gửi Issue.

---

## 🎯 Trạng thái Dự án

**✅ HOÀN TOÀN CÓ CHỨC NĂNG**

- ✅ 35 script Python
- ✅ Tài liệu hoàn chỉnh
- ✅ Pipeline phân tích hàng tháng
- ✅ Hệ thống chấm điểm tính cách
- ✅ Tạo tập huấn luyện LoRA
- ✅ Tích hợp Qwen Deep
- ✅ Xây dựng cơ sở kiến thức

---

**Cập nhật Lần cuối**: 2026-07-22  
**Phiên bản**: v1.0
