# Telegram 领取监控 · 关键词自动点击（tg_monitor）

一个挂在屏幕上的小工具：**实时盯着 Telegram 窗口，一旦画面里出现「领取」两个字，
自动把鼠标移过去点一下**。这样你不在电脑前，也不会错过限时领取的重要资料。

它走的是「**截屏 → OCR 识别文字 → 命中关键词 → 自动点击鼠标**」的路线，
所以 **网页版 Telegram、桌面版 Telegram 都能用**，不依赖账号 API、不用登录授权。

> ⚠️ 必须在**你自己的电脑**上运行（要能看到屏幕、控制鼠标）。云端容器没有屏幕，跑不了图形监控。

---

## 一、最省事：Windows 双击启动

1. 把仓库下载/解压到电脑（或 `git pull`）。
2. **双击 `monitor.bat`**。
   它会自动找 Python → 自动装依赖（首次会下载中文识别模型，需联网、耐心等几分钟）→ 打开监控窗口。
3. 在窗口里：
   - 先点 **「📐 框选监控区域」**，拖一个框把 **Telegram 聊天窗口**圈进去（识别更快更准、也更安全）；
   - 关键词默认就是 **领取**，需要的话可改成 `领取 红包 抢` 等（空格分隔）；
   - 点 **「▶ 开始监控」**。

> 没装 Python 的话，先到 https://www.python.org/downloads/ 安装，安装时勾选 **Add Python to PATH**。

## 二、Mac / Linux / 手动方式

```bash
pip install -r tg_monitor/requirements.txt   # mss numpy pyautogui easyocr
python -m tg_monitor                          # 打开图形监控窗口
```

- macOS 首次运行需在「系统设置 → 隐私与安全性」里给运行 Python 的程序授予
  **「屏幕录制」**（截屏用）和 **「辅助功能」**（控制鼠标用）权限，否则截不到屏 / 点不了。
- Linux 若提示缺 tkinter：`sudo apt install python3-tk`。

---

## 三、命令行用法（无界面 / 自动化）

```bash
python -m tg_monitor                     # 图形窗口（推荐）
python -m tg_monitor --no-gui            # 纯终端监控，Ctrl+C 停止
python -m tg_monitor -k 领取 红包        # 自定义关键词
python -m tg_monitor --dry-run           # 只提示不点击（先观察识别准不准）
python -m tg_monitor --region 100 200 800 600   # 指定监控区域 left top 宽 高
python -m tg_monitor --interval 1.0 --cooldown 8
python -m tg_monitor --save-config my.json      # 把设置存成文件
python -m tg_monitor --config my.json           # 下次直接读
```

---

## 四、各项设置说明

| 设置 | 作用 | 建议 |
|------|------|------|
| 关键词 keywords | 命中任意一个就触发，默认「领取」 | 可加 `红包 抢 立即领取`；英文不分大小写 |
| 监控区域 region | 只识别这块屏幕，不填=全屏 | **强烈建议框住 Telegram 窗口**，快又准 |
| 扫描间隔 interval | 每隔几秒识别一次 | 0.8~2 秒；越小越灵敏但越吃 CPU |
| 点击冷却 cooldown | 点一次后至少隔多久才再点 | 默认 8 秒，防同一个按钮被连点 |
| 去重半径 dedupe_radius | 冷却内离上次点太近的命中跳过 | 默认 45 像素 |
| 只提示不点击 dry-run | 只在日志报告、不真点 | **第一次先开它**，确认识别没问题再关 |
| 响铃提醒 sound_alert | 命中时响一声 | 开着，离开时也能听见 |

---

## 五、安全与紧急中止

- **紧急停**：把鼠标**快速甩到屏幕左上角**，pyautogui 故障保护会立刻中止点击（FAILSAFE）。
- 点完默认会把鼠标**移回原位**（`restore_mouse`），少打扰你手头的事。
- 自动点击是模拟你本人的鼠标操作，请**只对你自己有权领取的内容使用**；
  滥用去抢非自己应得的福利可能违反对应平台规则，风险自负。
- 建议先用 `--dry-run` 看几分钟日志，确认它认得准、点的位置对，再开启真正点击。

---

## 六、它是怎么工作的（模块）

| 文件 | 职责 |
|------|------|
| `tg_monitor/config.py` | 配置（关键词/区域/间隔/冷却…），可存读 JSON |
| `tg_monitor/matcher.py` | **纯逻辑**：关键词匹配 + 点击去重/冷却（有单元测试） |
| `tg_monitor/ocr.py` | 截屏 + OCR（easyocr 优先，缺失回退 tesseract） |
| `tg_monitor/clicker.py` | 鼠标移动/点击（带故障保护、演练模式） |
| `tg_monitor/monitor.py` | 监控主循环，串起上面，事件回调，UI 无关 |
| `tg_monitor/gui.py` | Tkinter 监控窗口（状态/日志/选区/启停） |

离线跑核心逻辑测试（不用装那些重依赖）：

```bash
python tests/test_tg_monitor.py
```

---

## 七、常见问题

- **识别不到「领取」？** 多半是区域没框对，或文字太小。把 Telegram 字体调大些、
  框准一点；首次用 easyocr 要等模型下载完。
- **点错位置？** 一般是区域 left/top 偏移没对上 —— 重新「框选监控区域」即可
  （区域坐标会自动加到点击位置上）。
- **太吃 CPU？** 把扫描间隔调大（如 2 秒），并务必只框 Telegram 窗口而不是全屏。
- **想用 Tesseract 而不是 easyocr？** 安装 Tesseract 程序 + `chi_sim` 语言包，
  `pip install pytesseract`，再 `--engine tesseract`。
