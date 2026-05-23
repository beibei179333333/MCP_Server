#!/usr/bin/env bash
# 一键在服务器上配置并运行 Bot API 克隆脚本。
#
# 交互模式:   bash setup.sh
# 非交互模式: TG_BOT_TOKEN='xxx' bash setup.sh        # 自动写 .env 并跑完整 97 个
#   可选:    BOT_OWNER_ID=123456  RUN=test|full|none
set -euo pipefail

cd "$(dirname "$0")"

# 环境变量里给了 token 就是非交互模式
NONINTERACTIVE=0
if [ -n "${TG_BOT_TOKEN:-}" ]; then
  NONINTERACTIVE=1
fi
RUN="${RUN:-}"

echo "==> 1/4 安装系统依赖 (python3 / pip / git)"
if command -v dnf >/dev/null 2>&1; then
  dnf install -y python3 python3-pip git
elif command -v apt-get >/dev/null 2>&1; then
  apt-get update && apt-get install -y python3 python3-venv python3-pip git
else
  echo "未识别的包管理器,请手动安装 python3 / pip / git" >&2
fi

echo "==> 2/4 创建虚拟环境并安装 Python 依赖"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "==> 3/4 配置 .env"
if [ -f .env ]; then
  echo "    已存在 .env,跳过(如需重配请先删除 .env)"
else
  if [ "$NONINTERACTIVE" -eq 1 ]; then
    TOKEN="$TG_BOT_TOKEN"
    OWNER="${BOT_OWNER_ID:-}"
  else
    read -r -p "    粘贴 @Biaoqing111bot 的 Bot Token: " TOKEN
    read -r -p "    你的 Telegram 数字 user_id(不知道就直接回车,自动识别): " OWNER
  fi
  cat > .env <<EOF
TG_BOT_TOKEN=${TOKEN}
BOT_OWNER_ID=${OWNER}
NEW_TITLE=会员表情🔥 @emojipd
SHORT_PREFIX=emojipd
START_INDEX=1
REUSE_FILE_ID=1
PACK_DELAY=3
TEST_LIMIT=0
EOF
  echo "    已写入 .env"
fi

echo ""
echo "==> 4/4 运行"
echo "    !! 务必先用你的 Telegram 账号给 @Biaoqing111bot 发过一条 /start !!"
echo "       (新表情包必须有归属用户,脚本靠这条消息自动识别你)"
echo ""

# 决定运行模式
if [ -z "$RUN" ]; then
  if [ "$NONINTERACTIVE" -eq 1 ]; then
    RUN="full"   # 非交互默认跑全部
  else
    read -r -p "现在先跑 2 个做测试吗?[Y/n] " ANS
    ANS=${ANS:-Y}
    [[ "$ANS" =~ ^[Yy]$ ]] && RUN="test" || RUN="none"
  fi
fi

case "$RUN" in
  test)
    echo "==> 测试运行(只跑 2 个)"
    TEST_LIMIT=2 python clone_via_bot.py
    echo ""
    echo "测试完成。确认这 2 个新包能在 Telegram 打开后,跑完整 97 个:"
    echo "    source .venv/bin/activate && rm -f state_bot.json && python clone_via_bot.py"
    ;;
  full)
    echo "==> 完整运行(97 个)"
    rm -f state_bot.json
    python clone_via_bot.py
    echo ""
    echo "全部完成。所有新链接见 state_bot.json:"
    echo "    cat state_bot.json"
    ;;
  *)
    echo "跳过运行。手动执行:"
    echo "    source .venv/bin/activate && python clone_via_bot.py"
    ;;
esac
