# Công cụ Xuất & Làm sạch Thành viên Nhóm Tự động (group_export)

Dựa trên API `fun-stat-bot.net`, tự động xuất danh sách thành viên nhóm với các tính năng sau:

- **Phân trang tự động** cho đến khi lấy hết tất cả thành viên
- **Tự động loại bỏ trùng lặp + tự động hợp nhất** (nhiều bản ghi của cùng một người dùng và thành viên trùng lặp trong nhiều nhóm được hợp nhất thành một, giữ thông tin đầy đủ nhất)
- **Lọc tài khoản không có tên người dùng**
- **Tự động lọc tài khoản spam/marketing** (từ khóa + liên kết + điện thoại + xếp emoji + đánh điểm thẻ scam/fake)
- Xuất sang **CSV / JSON / XLSX** đồng thời

> ⚠️ Quan trọng: Chính sách mạng của phiên đám mây hiện tại **không cho phép truy cập `fun-stat-bot.net`** (`Host not in allowlist`),
> vì vậy **bạn phải chạy trên máy tính của mình để lấy dữ liệu thực**. Đám mây chỉ dùng để phát triển và thử nghiệm ngoại tuyến.
> Công cụ sẽ **tự động phát hiện endpoint xuất** từ đặc tả Swagger, vì vậy nó thích ứng ngay cả khi đường dẫn giao diện khác một chút so với tài liệu chính thức.

Cũng cung cấp **phiên bản web di động**: dán hàng loạt liên kết nhóm, xuất một cú nhấp chuột, hiển thị **bảng thoải mái**, tải xuống CSV/Excel/JSON.

---

## ☁️ Xuất Một Cú Nhấp Chuột trên Đám mây (GitHub Actions · Không Cài đặt · Dữ liệu Thực, Thân thiện Di động)

**Thuận tiện nhất, dữ liệu thực có sẵn**: Không cần cài đặt, không triển khai, trực tiếp sử dụng máy chủ của GitHub
(có thể truy cập API), và tải xuống kết quả khi hoàn thành. Trình duyệt di động có thể hoàn thành tất cả các bước.

**Thiết lập bí mật một lần:**
1. Mở kho → **Settings → Secrets and variables → Actions → New repository secret**.
2. Name: `GROUP_EXPORT_TOKEN`, Secret: mã JWT của bạn → **Add secret**.

**Cho mỗi lần xuất:**
1. Mở tab **Actions** của kho → chọn "Export Members / 导出群成员" bên trái → **Run workflow** bên phải.
2. Dán liên kết nhóm vào trường "Group Links/IDs" (phân cách nhiều liên kết bằng dấu cách/dấu phẩy/dòng mới) → **Run workflow**.
3. Đợi 1-2 phút để hoàn thành, nhấp vào lần chạy đó, tải xuống từ **Artifacts → members** ở dưới cùng (chứa CSV/JSON/XLSX và danh sách đã lọc).

> - Tùy chọn: điền "Additional Filter Parameters", ví dụ: `--min-messages 1 --premium-only` (xem bảng "Filter Options" bên dưới cho tất cả tham số).
> - Tất cả được thực hiện trong trình duyệt, bí mật được lưu trữ dưới dạng Secret của kho (không hiển thị trong nhật ký).

---

## 🍎 Phiên bản Không Cài đặt cho iPhone (Mở URL và Sử dụng)

Toàn bộ logic được đóng gói thành **ứng dụng một trang trình duyệt thuần túy**, không cần cài đặt. Mở trực tiếp trong Safari di động:

**👉 https://raw.githack.com/beibei179333333/MCP_Server/claude/group-member-export-tool-sWRs7/docs/index.html**

> Để có URL vĩnh viễn ổn định hơn, bật GitHub Pages (một lần, có thể thực hiện trên di động):
> Kho **Settings → Pages → Source: Deploy from a branch →
> Branch: `claude/group-member-export-tool-sWRs7`, folder: `/docs` → Save**,
> Đợi một hoặc hai phút để truy cập `https://beibei179333333.github.io/MCP_Server/`.

> 🌐 **Song ngữ**: Góc trên bên phải chuyển đổi giữa **Tiếng Trung Giản thể / Tiếng Việt**, tùy chọn được lưu trong trình duyệt.

Cách sử dụng: Dán liên kết nhóm → Chọn bộ lọc → Điền token vào "Advanced Settings" → Bắt đầu xuất → Xem bảng / tải xuống CSV·JSON.

- **Chế độ demo** (hộp kiểm trên trang): Không cần token, không cần mạng, xem trước giao diện và hiệu ứng "bảng thoải mái" trước, đảm bảo hoạt động.
- **Dữ liệu thực**: Vì API này là HTTP và có thể hạn chế nguồn gốc chéo, iPhone Safari sẽ chặn yêu cầu trực tiếp
  (lỗi `Failed to fetch`). Hai giải pháp 👇

### Giải quyết "Failed to fetch"

**Giải pháp 1: Phiên bản Dự phòng được Lưu trữ (Khuyến nghị, 100% Dữ liệu Thực Có sẵn, Ổn định Nhất)**

Triển khai phiên bản với "proxy phía máy chủ" lên nền tảng miễn phí Render, nhận URL HTTPS, mở trên di động.
**Triển khai một cú nhấp chuột** (người dùng di động có thể nhấp vào liên kết này, đăng nhập bằng GitHub, không cần cài đặt Ứng dụng):

👉 https://render.com/deploy?repo=https://github.com/beibei179333333/MCP_Server/tree/claude/group-member-export-tool-sWRs7

1. Nhấp vào liên kết trên → Đăng nhập bằng GitHub → Nó sẽ tự động đọc `render.yaml` từ kho, chọn instance **Free** → **Apply / Deploy**.
2. Đợi vài phút, nhận URL như `https://group-export-xxxx.onrender.com`.
3. Mở URL đó trên di động (cùng giao diện song ngữ) → Điền token vào "Advanced Settings" → Xuất.
   Máy chủ thực hiện yêu cầu đến API cho bạn, **hoàn toàn vượt qua hạn chế nguồn gốc chéo / HTTP của Safari**, dữ liệu thực ổn định và có sẵn.

> Nếu liên kết một cú nhấp chuột không hoạt động, thiết lập thủ công: Render → New + → Web Service → Chọn kho `beibei179333333/MCP_Server`
> → Branch `claude/group-member-export-tool-sWRs7` → Start Command
> `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 600` → Free.

**Giải pháp 2: Điền "Network Proxy" trong Trang (Không Triển khai, nhưng Kém Ổn định/Vấn đề Bảo mật)**

Mở "② Filter Options → Advanced Settings → Network Proxy", điền proxy CORS (sử dụng `{url}` làm trình giữ chỗ), ví dụ:

```
https://corsproxy.io/?url={url}
```

Proxy chuyển tiếp phía máy chủ cho bạn, vượt qua chặn trình duyệt. ⚠️ **Cảnh báo: Yêu cầu của bạn (bao gồm token) sẽ đi qua proxy bên thứ ba này**,
sử dụng proxy đáng tin cậy, tốt nhất là bạn tự triển khai; nếu không, hãy sử dụng giải pháp 1.

---

## 💻 Phiên bản Máy tính để bàn (Windows · Dữ liệu Thực Trực tiếp Có sẵn, Thuận tiện Nhất)

Chạy trên máy tính của riêng bạn, trình duyệt mở `localhost`, máy tính thực hiện yêu cầu API cho bạn, **không có chặn nguồn gốc chéo/HTTP như trên di động**, dữ liệu thực trực tiếp có sẵn.

### Thuận tiện Nhất: Hai Bước (Tự động cài đặt Python)

1. **Tải xuống và giải nén**: Nhấp vào liên kết này để tải xuống zip, nhấp chuột phải sau khi tải xuống → "Extract All":
   https://github.com/beibei179333333/MCP_Server/archive/refs/heads/claude/group-member-export-tool-sWRs7.zip
2. Vào thư mục đã giải nén, **nhấp đúp `setup.bat`**.
   Nó sẽ **tự động cài đặt Python (nếu không có) → tự động cài đặt phụ thuộc → khởi động → tự động mở trình duyệt** tại `http://localhost:8000`.
   Không cần thao tác thủ công, đợi nó hoàn thành và trang sẽ bật lên.

Sau đó trong trang **② Filter Options → Advanced Settings** dán **Token** → dán liên kết nhóm → bắt đầu xuất → tải xuống CSV / Excel / JSON.

> - Nếu Python đã được cài đặt, bạn có thể trực tiếp nhấp đúp `run.bat` (nhanh hơn, bỏ qua cài đặt Python).
> - Góc trên bên phải chuyển đổi **Tiếng Trung / Tiếng Việt**.
> - Để dừng: Đóng cửa sổ dấu nhắc lệnh màu đen; để chạy lại, nhấp đúp `setup.bat` (hoặc `run.bat`).
> - Nếu Windows hiển thị "Protected your PC", nhấp **More info → Run anyway** (script chưa ký, hiện tượng bình thường).
> - Nếu cài đặt Python tự động thất bại (hiếm), làm theo nhắc nhở cửa sổ để cài đặt thủ công từ https://www.python.org/downloads/ (chọn "Add Python to PATH"), sau đó nhấp đúp lại.

## 📱 Phiên bản Web Di động (Chạy Máy chủ trên Máy tính/Termux)

Khởi động dịch vụ trên máy tính của riêng bạn, di động kết nối cùng WiFi để sử dụng trình duyệt:

```bash
pip install -r requirements.txt
export GROUP_EXPORT_TOKEN="<JWT của bạn>"     # hoặc điền vào "Advanced Settings" trên trang
./run.sh web                                  # hoặc python -m group_export serve
```

Sau khi khởi động, terminal in hai địa chỉ:
- Máy tính cục bộ: `http://127.0.0.1:8000`
- Truy cập di động: `http://<IP LAN máy tính>:8000` (di động và máy tính trên cùng WiFi)

Quy trình hoạt động web:
1. **Liên kết nhóm hàng loạt**: Một dòng một, hỗ trợ `https://t.me/xxx`, `@xxx`, ID bắt đầu bằng `-100…`, cũng phân tách bằng dấu phẩy; có thể tải lên `.txt`. Nhấp "Parse Preview" để xem bao nhiêu nhóm được nhận dạng.
2. **Tùy chọn bộ lọc**: Chọn "Filter no username / spam marketing / bots / scam fake", độ nghiêm ngặt spam có thể điều chỉnh.
3. **Bắt đầu xuất tự động**: Thanh tiến trình thời gian thực; sau khi hoàn thành, thống kê + **bảng thoải mái** được hiển thị bên dưới, với tải xuống CSV / Excel / JSON.
4. **Chế độ demo**: Khi được chọn, không cần token hoặc mạng, dữ liệu tổng hợp xem trước giao diện và bảng (thuận tiện để xem trước hiệu ứng trên di động trước).

> Để chạy máy chủ trực tiếp trên di động, sử dụng Android **Termux**: sau `pkg install python`, cùng `./run.sh web`, trình duyệt mở `http://127.0.0.1:8000`.

---

## 1. Phiên bản Dòng lệnh · Cài đặt

```bash
pip install -r requirements.txt        # requests, openpyxl
```

## 2. Cấu hình Token (Đừng Viết trong Code / Đừng Commit vào Git)

Chọn một trong ba:

```bash
# Phương pháp A: Biến môi trường
export GROUP_EXPORT_TOKEN="<JWT của bạn>"

# Phương pháp B: Tệp cục bộ (đã bỏ qua trong .gitignore)
echo "<JWT của bạn>" > token.txt

# Phương pháp C: Đối số dòng lệnh
python -m group_export export --token "<JWT của bạn>" ...
```

## 3. Kiểm tra Endpoints Trước (Tùy chọn, Xác nhận Tự động Phát hiện)

```bash
python -m group_export discover
```

Liệt kê tất cả các endpoint trong Swagger và in ra kết quả khớp tốt nhất cho giao diện "export group members".
Nếu tự động phát hiện sai, sử dụng `--endpoint / --group-param / --page-param / --size-param` bên dưới để chỉ định thủ công.

## 4. Xuất Một Nhóm (Quy trình Làm sạch Hoàn chỉnh)

```bash
python -m group_export export --group -1001234567890 -o members --format all
```

Đầu ra: `members.csv`, `members.json`, `members.xlsx`.

## 5. Xuất Nhiều Nhóm với Tự động Hợp nhất & Loại bỏ Trùng lặp

```bash
python -m group_export export \
  --group GROUP_A --group GROUP_B --group GROUP_C \
  -o merged --format all
```

Bạn cũng có thể hợp nhất **các tệp đã xuất trước đó**:

```bash
python -m group_export export --group GROUP_A --merge-in old_members.json -o merged
```

---

## Tùy chọn Bộ lọc

> Trong phiên bản web (iPhone không cài đặt / phiên bản máy chủ), **mỗi cài đặt có giải thích và đề xuất tiếng Trung bên dưới**,
> với nút "↻ One-Click Recommended" để tự động điền bộ lọc được khuyến nghị. Dưới đây là các tham số dòng lệnh.

| Tham số | Chức năng | Mặc định |
|---------|-----------|----------|
| `--keep-no-username` | Giữ tài khoản không có tên người dùng | Lọc theo mặc định |
| `--keep-ads` | Giữ tài khoản spam/marketing | Lọc theo mặc định |
| `--keep-bots` | Giữ bot | Lọc theo mặc định |
| `--keep-scam` | Giữ scam/fake | Lọc theo mặc định |
| `--keep-deleted` | Giữ tài khoản đã xóa/trống (không có tên người dùng và không có tên hiển thị) | Lọc theo mặc định |
| `--filter-no-photo` | Lọc tài khoản không có ảnh hồ sơ (chỉ khi API trả về rõ ràng không có ảnh) | Tắt theo mặc định |
| `--filter-random-username` | Lọc tên người dùng nghi ngờ ngẫu nhiên (như user123456) | Tắt theo mặc định |
| `--premium-only` | Chỉ giữ thành viên Premium | Tắt theo mặc định |
| `--verified-only` | Chỉ giữ tài khoản được xác minh chính thức | Tắt theo mặc định |
| `--min-messages N` | Chỉ giữ thành viên có số tin nhắn ≥ N (mức độ hoạt động) | 0 không giới hạn |
| `--language-keep zh,en` | Chỉ giữ các ngôn ngữ được chỉ định (ngôn ngữ không xác định được giữ) | Không giới hạn |
| `--ad-threshold N` | Ngưỡng phát hiện spam, nhỏ hơn = nghiêm ngặt hơn | 2 |
| `--ad-keywords-file FILE` | Danh sách từ khóa spam tùy chỉnh (thay thế tích hợp) | — |
| `--extra-ad-keywords-file FILE` | Thêm từ khóa spam (xếp chồng với tích hợp) | — |
| `--whitelist-file FILE` | Danh sách trắng tên người dùng, không bao giờ lọc | — |
| `--dump-removed` | Xuất bổ sung `xxx.removed.csv` (với lý do lọc) | — |

## Ghi đè Endpoint Thủ công (Sử dụng Khi Tự động Phát hiện Không Chính xác)

| Tham số | Mô tả |
|---------|-------|
| `--endpoint /api/...` | Đường dẫn endpoint xuất |
| `--method GET/POST` | Phương thức yêu cầu |
| `--group-param NAME` | Tên tham số ID nhóm (ví dụ: `group_id` / `chat_id`) |
| `--page-param NAME` | Tên tham số phân trang (ví dụ: `page` hoặc `offset`) |
| `--size-param NAME` | Tên tham số kích thước trang (ví dụ: `page_size` / `limit`) |
| `--page-size N` | Mục mỗi trang (mặc định 200) |
| `--offset-pagination` | Tham số phân trang là "offset" không phải "số trang" |
| `--param k=v` | Thêm tham số truy vấn tùy ý (có thể lặp lại) |

---

## Chạy Kiểm tra (Ngoại tuyến, Không Cần Mạng)

```bash
python tests/test_pipeline.py
# hoặc python -m pytest tests/ -q
```

## Quy tắc Loại bỏ Trùng lặp / Hợp nhất

- Khóa loại bỏ trùng lặp: Ưu tiên `user_id`, nếu không thì `@username`, nếu không thì tên hiển thị.
- Hợp nhất: Trường trống được điền từ bản ghi khác; `message_count` lấy tối đa; bot/premium/scam/fake lấy "OR";
  Ghi lại tất cả các nhóm mà thành viên này xuất hiện.

## Phát hiện Tài khoản Spam (Chấm điểm, Lọc nếu >= Ngưỡng)

- Khớp từ khóa spam (Tiếng Trung/Tiếng Anh, xem `group_export/filters.py`, +1 mỗi lần khớp)
- Tên/tiểu sử chứa liên kết `t.me/ http(s) @handle` (+2)
- Tên/tiểu sử chứa số điện thoại nghi ngờ (+2)
- Tên có xếp emoji ≥ 4 (+1)
- Tài khoản được đánh dấu scam/fake (+3)
