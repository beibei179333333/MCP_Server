#!/usr/bin/env bash
# 一条命令直接跑(无需 git / venv)。用法:
#   curl -fsSL <本文件raw地址> | TG_BOT_TOKEN='你的token' bash
# 可选环境变量:BOT_OWNER_ID、TEST_LIMIT(=2 则只跑2个测试)
set -euo pipefail

BRANCH="claude/telegram-emoji-clone-rename-AzlOD"
BASE="https://raw.githubusercontent.com/beibei179333333/MCP_Server/${BRANCH}"
DIR="$HOME/emoji_clone"

if [ -z "${TG_BOT_TOKEN:-}" ]; then
  echo "!! 缺少 TG_BOT_TOKEN。正确用法:" >&2
  echo "   curl -fsSL ${BASE}/oneclick.sh | TG_BOT_TOKEN='你的token' bash" >&2
  exit 1
fi

echo "==> 安装 python3 / pip / curl"
if command -v dnf >/dev/null 2>&1; then
  dnf install -y python3 python3-pip curl >/dev/null
elif command -v apt-get >/dev/null 2>&1; then
  apt-get update >/dev/null && apt-get install -y python3 python3-pip curl >/dev/null
fi

mkdir -p "$DIR" && cd "$DIR"

echo "==> 下载脚本和包列表"
curl -fsSL "${BASE}/clone_via_bot.py" -o clone_via_bot.py
curl -fsSL "${BASE}/packs.txt" -o packs.txt

echo "==> 安装 Python 依赖 (requests / python-dotenv)"
python3 -m pip install -q --upgrade pip >/dev/null 2>&1 || true
python3 -m pip install -q requests python-dotenv >/dev/null 2>&1 \
  || python3 -m pip install --user -q requests python-dotenv

echo "==> 写入 .env"
cat > .env <<EOF
TG_BOT_TOKEN=${TG_BOT_TOKEN}
BOT_OWNER_ID=${BOT_OWNER_ID:-}
NEW_TITLE=会员表情🔥 @emojipd
SHORT_PREFIX=emojipd
START_INDEX=1
REUSE_FILE_ID=1
PACK_DELAY=3
TEST_LIMIT=${TEST_LIMIT:-0}
EOF

echo "==> 开始克隆(务必已用你的账号给 @Biaoqing111bot 发过 /start)"
echo ""
python3 clone_via_bot.py

echo ""
echo "==> 完成。全部新链接见:  cat ${DIR}/state_bot.json"
