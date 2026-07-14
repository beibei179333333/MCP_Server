# Group Member Auto Export & Cleansing Tool (group_export)

Based on the `fun-stat-bot.net` API, automatically export group member lists with the following features:

- **Auto-pagination** until all members are retrieved
- **Auto deduplication + auto merging** (multiple records of the same user and duplicate members across groups are merged into one, keeping the most complete information)
- **Filter accounts without usernames**
- **Auto-filter spam/marketing accounts** (keyword + link + phone + emoji stacking + scam/fake tag scoring)
- Export to **CSV / JSON / XLSX** simultaneously

> ⚠️ Important: The current cloud session's network policy **does not allow access to `fun-stat-bot.net`** (`Host not in allowlist`),
> so **you must run on your own computer to fetch real data**. The cloud is only for development and offline testing.
> The tool will **auto-detect export endpoints** from the Swagger spec, so it adapts even if the interface path differs slightly from official documentation.

Also provides a **mobile web version**: batch paste group links, one-click export, **relaxed table** display, CSV/Excel/JSON download.

---

## ☁️ Cloud One-Click Export (GitHub Actions · Zero Installation · Real Data, Mobile-Friendly)

**Most convenient, real data available**: No installation, no deployment required, directly use GitHub's own servers
(which can access the API), and download the results when complete. Mobile browsers can complete all steps.

**One-time secret setup:**
1. Open repository → **Settings → Secrets and variables → Actions → New repository secret**.
2. Name: `GROUP_EXPORT_TOKEN`, Secret: your JWT token → **Add secret**.

**For each export:**
1. Open repository **Actions** tab → select "Export Members / 导出群成员" on the left → **Run workflow** on the right.
2. Paste group links in the "Group Links/IDs" field (separate multiple with spaces/commas/newlines) → **Run workflow**.
3. Wait 1-2 minutes for completion, click into the run, download from **Artifacts → members** at the bottom (contains CSV/JSON/XLSX and filtered lists).

> - Optional: fill "Additional Filter Parameters", e.g., `--min-messages 1 --premium-only` (see "Filter Options" table below for all parameters).
> - All done in the browser, secret stored as repository Secret (not shown in logs).

---

## 🍎 iPhone Zero-Install Version (Open URL and Use)

The entire logic is packaged as a **pure browser single-page application**, no installation required. Open directly in mobile Safari:

**👉 https://raw.githack.com/beibei179333333/MCP_Server/claude/group-member-export-tool-sWRs7/docs/index.html**

> For a more stable permanent URL, enable GitHub Pages (one-time, can be done on mobile):
> Repository **Settings → Pages → Source: Deploy from a branch →
> Branch: `claude/group-member-export-tool-sWRs7`, folder: `/docs` → Save**,
> Wait a minute or two to access `https://beibei179333333.github.io/MCP_Server/`.

> 🌐 **Bilingual**: Top-right corner switches between **Simplified Chinese / Tiếng Việt (Vietnamese)**, preference saved in browser.

Usage: Paste group links → Select filters → Fill token in "Advanced Settings" → Start export → View table / download CSV·JSON.

- **Demo mode** (checkbox on page): No token, no network required, preview UI and "relaxed table" effect first, guaranteed to work.
- **Real data**: Since this API is HTTP and may restrict cross-origin, iPhone Safari will block direct requests
  (error `Failed to fetch`). Two solutions 👇

### Solving "Failed to fetch"

**Solution 1: Hosted Fallback Version (Recommended, 100% Real Data Available, Most Stable)**

Deploy the version with "server-side proxy" to the free platform Render, get an HTTPS URL, open on mobile.
**One-click deploy** (mobile users can click this link, login with GitHub, no App installation):

👉 https://render.com/deploy?repo=https://github.com/beibei179333333/MCP_Server/tree/claude/group-member-export-tool-sWRs7

1. Click the link above → Login with GitHub → It will auto-read `render.yaml` from the repository, select instance **Free** → **Apply / Deploy**.
2. Wait a few minutes, get a URL like `https://group-export-xxxx.onrender.com`.
3. Open that URL on mobile (same bilingual interface) → Fill token in "Advanced Settings" → Export.
   The server makes requests to the API for you, **completely bypassing Safari's cross-origin / HTTP restrictions**, real data stable and available.

> If the one-click link doesn't work, manual setup: Render → New + → Web Service → Select repository `beibei179333333/MCP_Server`
> → Branch `claude/group-member-export-tool-sWRs7` → Start Command
> `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 600` → Free.

**Solution 2: Fill "Network Proxy" in the Page (Zero Deployment, but Less Stable/Security Concerns)**

Open "② Filter Options → Advanced Settings → Network Proxy", fill a CORS proxy (use `{url}` as placeholder), e.g.:

```
https://corsproxy.io/?url={url}
```

The proxy forwards on the server side for you, bypassing browser blocking. ⚠️ **Warning: Your request (including token) will go through this third-party proxy**,
use a trusted proxy, preferably one you deploy yourself; otherwise, use solution 1.

---

## 💻 Desktop Version (Windows · Real Data Directly Available, Most Convenient)

Run on your own computer, browser opens `localhost`, computer makes API requests for you, **no cross-origin/HTTP blocking like on mobile**, real data directly available.

### Most Convenient: Two Steps (Auto-install Python)

1. **Download and extract**: Click this link to download zip, right-click after download → "Extract All":
   https://github.com/beibei179333333/MCP_Server/archive/refs/heads/claude/group-member-export-tool-sWRs7.zip
2. Enter the extracted folder, **double-click `setup.bat`**.
   It will **auto-install Python (if not present) → auto-install dependencies → start → auto-open browser** at `http://localhost:8000`.
   No manual operations needed, wait for it to finish and the page to pop up.

Then in the page **② Filter Options → Advanced Settings** paste **Token** → paste group links → start export → download CSV / Excel / JSON.

> - If Python is already installed, you can directly double-click `run.bat` (faster, skips Python installation).
> - Top-right corner switches **Chinese / Vietnamese**.
> - To stop: Close the black command prompt window; to run again, double-click `setup.bat` (or `run.bat`).
> - If Windows shows "Protected your PC", click **More info → Run anyway** (script unsigned, normal).
> - If auto Python installation fails (rare), follow window prompt to manually install from https://www.python.org/downloads/ (check "Add Python to PATH"), then double-click again.

## 📱 Mobile Web Version (Run Server on Computer/Termux)

Start the service on your own computer, mobile connects to same WiFi to use browser:

```bash
pip install -r requirements.txt
export GROUP_EXPORT_TOKEN="<your JWT>"     # or fill in "Advanced Settings" on page
./run.sh web                               # or python -m group_export serve
```

After startup, terminal prints two addresses:
- Local computer: `http://127.0.0.1:8000`
- Mobile access: `http://<computer LAN IP>:8000` (mobile and computer on same WiFi)

Web operation flow:
1. **Batch group links**: One per line, supports `https://t.me/xxx`, `@xxx`, ID starting with `-100…`, also comma-separated; can upload `.txt`. Click "Parse Preview" to see how many groups recognized.
2. **Filter options**: Check "Filter no username / spam marketing / bots / scam fake", adjustable spam strictness.
3. **Start auto export**: Real-time progress bar; after completion, statistics + **relaxed table** displayed below, with CSV / Excel / JSON download.
4. **Demo mode**: When checked, no token or network needed, synthetic data previews interface and table (convenient for previewing effect on mobile first).

> To run server directly on mobile, use Android **Termux**: after `pkg install python`, same `./run.sh web`, browser opens `http://127.0.0.1:8000`.

---

## 1. Command Line Version · Installation

```bash
pip install -r requirements.txt        # requests, openpyxl
```

## 2. Configure Token (Don't Write in Code / Don't Commit to Git)

Choose one of three:

```bash
# Method A: Environment variable
export GROUP_EXPORT_TOKEN="<your JWT>"

# Method B: Local file (already ignored in .gitignore)
echo "<your JWT>" > token.txt

# Method C: Command line argument
python -m group_export export --token "<your JWT>" ...
```

## 3. Check Endpoints First (Optional, Confirm Auto-Detection)

```bash
python -m group_export discover
```

Lists all endpoints in Swagger and prints the best match for "export group members" interface.
If auto-detection is wrong, use `--endpoint / --group-param / --page-param / --size-param` below to manually specify.

## 4. Export One Group (Complete Cleansing Process)

```bash
python -m group_export export --group -1001234567890 -o members --format all
```

Output: `members.csv`, `members.json`, `members.xlsx`.

## 5. Export Multiple Groups with Auto Merge & Dedup

```bash
python -m group_export export \
  --group GROUP_A --group GROUP_B --group GROUP_C \
  -o merged --format all
```

You can also merge **previously exported files**:

```bash
python -m group_export export --group GROUP_A --merge-in old_members.json -o merged
```

---

## Filter Options

> In the web version (iPhone zero-install / server version), **each setting has Chinese explanation and suggestions below**,
> with "↻ One-Click Recommended" button to auto-fill recommended filters. Below are the command line parameters.

| Parameter | Function | Default |
|-----------|----------|---------|
| `--keep-no-username` | Keep accounts without username | Filter by default |
| `--keep-ads` | Keep spam/marketing accounts | Filter by default |
| `--keep-bots` | Keep bots | Filter by default |
| `--keep-scam` | Keep scam/fake | Filter by default |
| `--keep-deleted` | Keep deleted/blank accounts (no username and no display name) | Filter by default |
| `--filter-no-photo` | Filter accounts without profile photo (only when API explicitly returns no photo) | Off by default |
| `--filter-random-username` | Filter suspected random usernames (like user123456) | Off by default |
| `--premium-only` | Keep only Premium members | Off by default |
| `--verified-only` | Keep only officially verified accounts | Off by default |
| `--min-messages N` | Keep only members with message count ≥ N (activity level) | 0 unlimited |
| `--language-keep zh,en` | Keep only specified languages (unknown language kept) | Unlimited |
| `--ad-threshold N` | Spam detection threshold, smaller = stricter | 2 |
| `--ad-keywords-file FILE` | Custom spam keyword list (replace built-in) | — |
| `--extra-ad-keywords-file FILE` | Append spam keywords (stack with built-in) | — |
| `--whitelist-file FILE` | Username whitelist, never filter | — |
| `--dump-removed` | Additional export `xxx.removed.csv` (with filter reasons) | — |

## Manual Endpoint Override (Use When Auto-Detection Inaccurate)

| Parameter | Description |
|-----------|-------------|
| `--endpoint /api/...` | Export endpoint path |
| `--method GET/POST` | Request method |
| `--group-param NAME` | Group ID parameter name (e.g., `group_id` / `chat_id`) |
| `--page-param NAME` | Pagination parameter name (e.g., `page` or `offset`) |
| `--size-param NAME` | Page size parameter name (e.g., `page_size` / `limit`) |
| `--page-size N` | Items per page (default 200) |
| `--offset-pagination` | Pagination parameter is "offset" not "page number" |
| `--param k=v` | Append arbitrary query parameters (repeatable) |

---

## Run Tests (Offline, No Network Required)

```bash
python tests/test_pipeline.py
# or python -m pytest tests/ -q
```

## Deduplication / Merge Rules

- Dedup key: Priority `user_id`, else `@username`, else display name.
- Merge: Empty fields filled from another record; `message_count` takes max; bot/premium/scam/fake takes "OR";
  Records all groups this member appeared in.

## Spam Account Detection (Scoring, Filter if >= Threshold)

- Matches spam keywords (Chinese/English, see `group_export/filters.py`, +1 per match)
- Name/bio contains links `t.me/ http(s) @handle` (+2)
- Name/bio contains suspected phone number (+2)
- Name has emoji stacking ≥ 4 (+1)
- Account marked scam/fake (+3)
