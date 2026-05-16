#!/usr/bin/env bash
# ============================================================================
# Telegram All-in-One Bot — 一行命令全自动部署
#
# 用法（在你服务器的 SSH 终端粘贴）：
#
#   curl -fsSL https://raw.githubusercontent.com/beibei179333333/mcp_server/claude/telegram-bot-features-efxHj/deploy/install.sh \
#     | BOT_TOKEN=xxxxx ADMIN_IDS=yyy bash
#
# 支持发行版：AlmaLinux/Rocky/RHEL/CentOS 8+、Ubuntu 20.04+、Debian 11+
# 不需要 docker。直接 venv + systemd。
# ============================================================================
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/telegram-bot}"
REPO_URL="${REPO_URL:-https://github.com/beibei179333333/mcp_server}"
REPO_BRANCH="${REPO_BRANCH:-claude/telegram-bot-features-efxHj}"
PY_BIN="${PY_BIN:-python3.11}"
SERVICE_USER="${SERVICE_USER:-botuser}"

BOT_TOKEN_VAL="${BOT_TOKEN:-}"
ADMIN_IDS_VAL="${ADMIN_IDS:-}"
TG_API_ID_VAL="${TG_API_ID:-}"
TG_API_HASH_VAL="${TG_API_HASH:-}"
TG_PHONE_VAL="${TG_PHONE:-}"
TZ_VAL="${TIMEZONE:-Asia/Shanghai}"
WEB_PORT_VAL="${WEB_PORT:-8000}"

bold(){ printf "\033[1m%s\033[0m\n" "$*"; }
green(){ printf "\033[1;32m%s\033[0m\n" "$*"; }
red(){ printf "\033[1;31m%s\033[0m\n" "$*" >&2; }
hr(){ printf "%0.s─" {1..60}; echo; }

[[ $EUID -eq 0 ]] || { red "请用 root 执行：sudo bash install.sh"; exit 1; }
[[ -n "$BOT_TOKEN_VAL" ]] || { red "缺少 BOT_TOKEN 环境变量"; exit 1; }

bold "🚀 Telegram All-in-One Bot 部署器"
hr

# ----------------------------------------------------------------------------
# 1. 检测发行版 + 安装依赖
# ----------------------------------------------------------------------------
if [[ -f /etc/os-release ]]; then
  . /etc/os-release
  DISTRO=$ID
else
  red "无法检测发行版"; exit 1
fi
bold "检测到发行版：$PRETTY_NAME"

case "$DISTRO" in
  ubuntu|debian)
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y --no-install-recommends \
      git curl ca-certificates tzdata \
      python3 python3-venv python3-pip python3-dev \
      build-essential libffi-dev libssl-dev libjpeg-dev zlib1g-dev \
      fonts-dejavu-core ufw
    PY_BIN=python3
    ;;
  almalinux|rocky|rhel|centos|fedora)
    dnf install -y epel-release || true
    dnf install -y \
      git curl ca-certificates tzdata \
      python3.11 python3.11-devel python3-pip \
      gcc gcc-c++ make \
      libffi-devel openssl-devel libjpeg-turbo-devel zlib-devel \
      dejavu-sans-fonts firewalld policycoreutils-python-utils || \
    dnf install -y \
      git curl ca-certificates tzdata \
      python3 python3-devel python3-pip \
      gcc gcc-c++ make \
      libffi-devel openssl-devel libjpeg-turbo-devel zlib-devel \
      dejavu-sans-fonts firewalld
    # 找一个能用的 python ≥ 3.10
    if command -v python3.11 >/dev/null 2>&1; then PY_BIN=python3.11
    elif command -v python3.12 >/dev/null 2>&1; then PY_BIN=python3.12
    elif command -v python3.10 >/dev/null 2>&1; then PY_BIN=python3.10
    else PY_BIN=python3; fi
    ;;
  *)
    red "不支持的发行版：$DISTRO"; exit 1
    ;;
esac

green "✓ 系统依赖已安装（python=$PY_BIN）"
hr

# ----------------------------------------------------------------------------
# 2. 时区
# ----------------------------------------------------------------------------
timedatectl set-timezone "$TZ_VAL" 2>/dev/null || true
green "✓ 时区：$(date +%Z)"
hr

# ----------------------------------------------------------------------------
# 3. 拉取代码
# ----------------------------------------------------------------------------
if [[ -d "$INSTALL_DIR/.git" ]]; then
  bold "更新已有仓库..."
  git -C "$INSTALL_DIR" fetch --all --prune
  git -C "$INSTALL_DIR" reset --hard "origin/$REPO_BRANCH"
else
  bold "克隆仓库到 $INSTALL_DIR ..."
  rm -rf "$INSTALL_DIR"
  git clone -b "$REPO_BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"
green "✓ 代码就绪：$(git -C "$INSTALL_DIR" log -1 --oneline)"
hr

# ----------------------------------------------------------------------------
# 4. 虚拟环境 + 依赖
# ----------------------------------------------------------------------------
bold "创建虚拟环境..."
"$PY_BIN" -m venv .venv
./.venv/bin/pip install --upgrade pip wheel setuptools >/dev/null
bold "安装依赖（≈ 1-3 分钟）..."
./.venv/bin/pip install --no-cache-dir -r requirements.txt
green "✓ 依赖安装完成"
hr

# ----------------------------------------------------------------------------
# 5. 生成 .env
# ----------------------------------------------------------------------------
RANDOM_SECRET=$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 40)
cat > .env <<EOF
# 自动生成 $(date -Iseconds)
BOT_TOKEN=${BOT_TOKEN_VAL}
ADMIN_IDS=${ADMIN_IDS_VAL}

TG_API_ID=${TG_API_ID_VAL}
TG_API_HASH=${TG_API_HASH_VAL}
TG_PHONE=${TG_PHONE_VAL}

DATABASE_URL=sqlite+aiosqlite:///./data/bot.db
TIMEZONE=${TZ_VAL}

BROADCAST_INTERVAL_MS=80
BROADCAST_BATCH=30

ENABLE_CAPTCHA=true
CAPTCHA_TIMEOUT=120
ENABLE_ANTI_SPAM=true

SUBSCRIPTION_ENABLED=true
DEFAULT_TRIAL_DAYS=7

WEB_ENABLED=true
WEB_HOST=0.0.0.0
WEB_PORT=${WEB_PORT_VAL}
WEB_SECRET=${RANDOM_SECRET}
WEB_USERNAME=admin
WEB_PASSWORD=

DEFAULT_LANG=zh
LOG_LEVEL=INFO
LOG_RETENTION_DAYS=14
EOF
chmod 600 .env
mkdir -p data logs
green "✓ 已写入 .env（权限 600）"
hr

# ----------------------------------------------------------------------------
# 6. 防火墙 + SELinux
# ----------------------------------------------------------------------------
if command -v firewall-cmd >/dev/null 2>&1; then
  systemctl enable --now firewalld 2>/dev/null || true
  firewall-cmd --permanent --add-port=${WEB_PORT_VAL}/tcp || true
  firewall-cmd --reload || true
  green "✓ firewalld 已放行 ${WEB_PORT_VAL}/tcp"
fi
if command -v ufw >/dev/null 2>&1; then
  ufw allow ${WEB_PORT_VAL}/tcp || true
fi
# SELinux 让 systemd 进程能监听任意端口
if command -v setsebool >/dev/null 2>&1; then
  setsebool -P httpd_can_network_connect 1 2>/dev/null || true
fi
hr

# ----------------------------------------------------------------------------
# 7. systemd 服务
# ----------------------------------------------------------------------------
cat > /etc/systemd/system/telegram-bot.service <<EOF
[Unit]
Description=Telegram All-in-One Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/run.py
Restart=on-failure
RestartSec=5
StandardOutput=append:${INSTALL_DIR}/logs/stdout.log
StandardError=append:${INSTALL_DIR}/logs/stderr.log
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable telegram-bot
systemctl restart telegram-bot
sleep 3
green "✓ systemd 服务已启动"
hr

# ----------------------------------------------------------------------------
# 8. 验证
# ----------------------------------------------------------------------------
IP=$(curl -s -m 5 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')
echo
bold "📊 状态："
systemctl status telegram-bot --no-pager | head -20 || true
echo
hr
green "🎉 部署完成！"
echo
echo "  🤖 BOT @username（看下方日志最后几行）"
echo "  🖥  Web 控制台：http://${IP}:${WEB_PORT_VAL}"
echo "      默认用户：admin"
echo "      默认密码：见日志启动行（WEB_SECRET 派生）"
echo
echo "  📜 实时日志：  journalctl -u telegram-bot -f"
echo "  🔁 重启：      systemctl restart telegram-bot"
echo "  ⏹  停止：       systemctl stop telegram-bot"
echo "  📁 安装目录：  $INSTALL_DIR"
echo
bold "👉 下一步：在 Telegram 找到你的 bot，发 /start"
echo "   如果设置了 ADMIN_IDS，你的私聊里应已收到："
echo "     ✅ 我已经准备好了，可以工作！"
echo
hr
echo "最近 30 行启动日志："
tail -n 30 "$INSTALL_DIR/logs/stdout.log" 2>/dev/null || journalctl -u telegram-bot --no-pager -n 30
