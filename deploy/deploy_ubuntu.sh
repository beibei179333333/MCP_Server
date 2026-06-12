#!/usr/bin/env bash
# 一键部署 2026 世界杯 Telegram 机器人到 Ubuntu（以 root 运行）。
# 幂等：可重复执行用于更新。装为 systemd 服务，开机自启 + 崩溃自动重启。
#
# 用法：
#   TELEGRAM_BOT_TOKEN=xxxx bash deploy/deploy_ubuntu.sh
# 可选环境变量：
#   PROVIDER=demo|football-data   FOOTBALL_DATA_API_KEY=...   TIMEZONE=Asia/Shanghai
#   REPO=... BRANCH=...           （私有仓库可用带 PAT 的 https URL）
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/worldcup-bot}"
REPO="${REPO:-https://github.com/beibei179333333/MCP_Server.git}"
BRANCH="${BRANCH:-claude/2026-world-cup-telegram-bot-15wfrb}"

echo "==> [1/6] 安装系统依赖 (python3 / venv / pip / git)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git

echo "==> [2/6] 拉取代码到 $APP_DIR (分支 $BRANCH)"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" remote set-url origin "$REPO"
  git -C "$APP_DIR" fetch origin "$BRANCH"
  git -C "$APP_DIR" checkout -B "$BRANCH" "origin/$BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
  git clone -b "$BRANCH" "$REPO" "$APP_DIR"
fi

echo "==> [3/6] 创建虚拟环境并安装依赖"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip -q
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/worldcup_bot/requirements.txt" -q

echo "==> [4/6] 写入配置 .env（已存在则不覆盖）"
if [ ! -f "$APP_DIR/.env" ]; then
  cat > "$APP_DIR/.env" <<ENV
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
PROVIDER=${PROVIDER:-demo}
COMPETITION=WC
TIMEZONE=${TIMEZONE:-Asia/Shanghai}
DEFAULT_LANG=${DEFAULT_LANG:-zh}
DB_PATH=$APP_DIR/worldcup_bot.db
REMINDER_MINUTES=15
# 用真实赛果：到 https://www.football-data.org/ 申请 Key，填下一行并把 PROVIDER 改成 football-data
FOOTBALL_DATA_API_KEY=${FOOTBALL_DATA_API_KEY:-}
ENV
  chmod 600 "$APP_DIR/.env"
  echo "    已生成 $APP_DIR/.env"
else
  echo "    已存在 $APP_DIR/.env，保留不动（如需改配置请手动编辑）"
fi

echo "==> [5/6] 安装 systemd 服务"
install -m 644 "$APP_DIR/deploy/worldcup-bot.service" /etc/systemd/system/worldcup-bot.service
systemctl daemon-reload
systemctl enable worldcup-bot >/dev/null 2>&1 || true
systemctl restart worldcup-bot

echo "==> [6/6] 状态"
sleep 2
systemctl --no-pager --full status worldcup-bot | head -15 || true
echo
echo "✅ 部署完成。实时日志： journalctl -u worldcup-bot -f"
echo "   现在去 Telegram 给你的机器人发 /start 即可开始接收通知。"
