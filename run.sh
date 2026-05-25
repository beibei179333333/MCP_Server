#!/usr/bin/env bash
# 群成员导出工具 · 一键启动脚本
#
#   ./run.sh web                 启动手机网页版 (默认端口 8000)
#   ./run.sh web 8080            指定端口
#   ./run.sh discover            列出 API 接口
#   ./run.sh export <群链接...>  命令行直接导出
#   ./run.sh test                跑离线测试
#
# 密钥：优先读环境变量 GROUP_EXPORT_TOKEN，其次读本目录 token.txt。
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

ensure_deps() {
  if ! "$PY" -c "import flask, requests, openpyxl" >/dev/null 2>&1; then
    echo "[*] 安装依赖中 (flask/requests/openpyxl)…"
    "$PY" -m pip install -r requirements.txt
  fi
}

cmd="${1:-web}"; shift || true
case "$cmd" in
  web)
    ensure_deps
    "$PY" -m group_export serve --port "${1:-8000}"
    ;;
  discover)
    ensure_deps
    "$PY" -m group_export discover
    ;;
  export)
    ensure_deps
    args=(); for g in "$@"; do args+=(--group "$g"); done
    "$PY" -m group_export export "${args[@]}" -o members --format all
    ;;
  test)
    "$PY" tests/test_pipeline.py
    ;;
  *)
    echo "用法: ./run.sh [web|discover|export|test] ..."; exit 1;;
esac
