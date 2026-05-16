#!/usr/bin/env bash
# 一键安装脚本（Ubuntu / Debian）
# 用法：
#   curl -L https://example.com/install.sh | bash
#   或：bash deploy/install.sh
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/telegram-bot}"
PY_BIN="${PY_BIN:-python3}"

echo "==> 安装 Telegram All-in-One Bot 到 ${INSTALL_DIR}"

# 1. 系统依赖
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    build-essential libffi-dev libssl-dev libjpeg-dev zlib1g-dev \
    fonts-dejavu-core git ca-certificates
fi

# 2. 拷贝代码（假设当前目录就是源码）
sudo mkdir -p "${INSTALL_DIR}"
sudo cp -r ./* "${INSTALL_DIR}/"
cd "${INSTALL_DIR}"

# 3. 虚拟环境 + 依赖
sudo "${PY_BIN}" -m venv .venv
sudo .venv/bin/pip install --upgrade pip
sudo .venv/bin/pip install -r requirements.txt

# 4. 配置文件
if [ ! -f .env ]; then
  sudo cp .env.example .env
  echo "==> 已生成 .env，请编辑后再启动："
  echo "    sudo nano ${INSTALL_DIR}/.env"
fi

# 5. systemd 服务
if [ -d /etc/systemd/system ]; then
  sudo cp deploy/telegram-bot.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable telegram-bot
  echo "==> 已注册 systemd 服务：sudo systemctl start telegram-bot"
fi

# 6. user-bot 首次登录提示
echo ""
echo "============================================================"
echo "  安装完成！"
echo ""
echo "  下一步："
echo "  1. 编辑配置：       sudo nano ${INSTALL_DIR}/.env"
echo "  2. 首次登录 user-bot（交互式）："
echo "       cd ${INSTALL_DIR} && sudo .venv/bin/python run.py"
echo "     完成后 Ctrl+C 退出"
echo "  3. 启动 systemd 服务：sudo systemctl start telegram-bot"
echo "  4. 查看日志：         journalctl -u telegram-bot -f"
echo "  5. Web 控制台：       http://<IP>:8000"
echo "============================================================"
