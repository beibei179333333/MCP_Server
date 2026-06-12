#!/usr/bin/env bash
# 2026 世界杯 Telegram 机器人 · 一键启动
#
#   ./run_bot.sh            启动机器人
#   ./run_bot.sh check      只检查配置 / 数据源，不启动
#   ./run_bot.sh selftest   离线自测（验证通知逻辑，无需网络/Token）
#
# Token 等配置从环境变量或本目录 .env 读取（见 .env.example）。
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if ! "$PY" -c "import requests" >/dev/null 2>&1; then
  echo "[*] 安装依赖 requests …"
  "$PY" -m pip install -r worldcup_bot/requirements.txt
fi

cmd="${1:-run}"
exec "$PY" -m worldcup_bot "$cmd"
