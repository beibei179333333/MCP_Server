"""Mobile-friendly web UI for batch group-member export.

Run:  python -m group_export serve            (then open the printed URL on your phone)
The heavy lifting reuses api.py / pipeline.py / filters.py.
"""
from __future__ import annotations

import os
import random
import tempfile
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, send_file, send_from_directory

from .api import ApiClient, ApiConfig
from .config import resolve_base_url, resolve_token
from .export import write
from .filters import FilterConfig
from .links import parse_many
from .models import EXPORT_COLUMNS, Member
from .pipeline import run

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# Chinese column headers for the results table (loose/spacious layout in CSS).
COLUMN_LABELS = {
    "user_id": "用户ID",
    "username": "用户名",
    "full_name": "昵称",
    "first_name": "名",
    "last_name": "姓",
    "phone": "电话",
    "is_bot": "机器人",
    "is_premium": "会员",
    "is_verified": "认证",
    "is_scam": "诈骗",
    "is_fake": "仿冒",
    "language_code": "语言",
    "message_count": "消息数",
    "join_date": "加入时间",
    "last_seen": "最后在线",
    "bio": "简介",
    "groups": "所属群",
}
# Columns shown in the on-screen table (full set still goes to file exports).
TABLE_COLUMNS = ["username", "full_name", "user_id", "message_count",
                 "is_premium", "language_code", "groups"]


class Job:
    def __init__(self, job_id: str):
        self.id = job_id
        self.status = "pending"        # pending | running | done | error
        self.message = "排队中…"
        self.groups_total = 0
        self.groups_done = 0
        self.raw_count = 0
        self.stats: Dict[str, Any] = {}
        self.rows: List[Dict[str, Any]] = []
        self.error: Optional[str] = None
        self.dir = tempfile.mkdtemp(prefix=f"grpexp_{job_id}_")
        self.files: Dict[str, str] = {}
        self.created = time.time()


JOBS: Dict[str, Job] = {}
_LOCK = threading.Lock()


def _demo_members(group: str, n: int = 25) -> List[dict]:
    """Synthetic data so the UI / table can be previewed without network."""
    first = ["小明", "Alice", "李雷", "Bob", "韩梅梅", "Carol", "王伟", "Dave", "赵敏"]
    spam_names = ["出售飞机号 t.me/spam", "广告推广加我", "USDT承兑通道",
                  "招商代理👑👑👑👑", "网赚兼职日入过千"]
    out = []
    for i in range(n):
        r = random.random()
        if r < 0.18:                       # ad / marketing
            out.append({"id": 90000 + i, "username": f"promo{i}",
                        "first_name": random.choice(spam_names), "message_count": random.randint(0, 3)})
        elif r < 0.30:                     # no username
            out.append({"id": 80000 + i, "first_name": random.choice(first),
                        "message_count": random.randint(0, 50)})
        elif r < 0.36:                     # scam flagged
            out.append({"id": 70000 + i, "username": f"x{i}", "is_scam": True,
                        "first_name": "可疑账号"})
        else:                              # normal
            out.append({"id": 1000 + i, "username": f"user_{group[:4]}_{i}",
                        "first_name": random.choice(first),
                        "is_premium": random.random() < 0.2,
                        "language_code": random.choice(["zh", "en", "ru"]),
                        "message_count": random.randint(1, 500)})
    # inject a cross-group duplicate to show merge
    out.append({"id": 1000, "username": f"user_{group[:4]}_0", "last_name": "(合并)"})
    return out


def _run_job(job: Job, groups: List[str], token: str, base_url: str,
             opts: Dict[str, Any]) -> None:
    try:
        job.status = "running"
        job.groups_total = len(groups)
        demo = bool(opts.get("demo"))

        client = None
        if not demo:
            api_cfg = ApiConfig(
                base_url=base_url, token=token,
                endpoint=opts.get("endpoint") or None,
                method=opts.get("method") or "GET",
                group_param=opts.get("group_param") or None,
                page_param=opts.get("page_param") or None,
                size_param=opts.get("size_param") or None,
                page_size=int(opts.get("page_size") or 200),
                verbose=False,
            )
            client = ApiClient(api_cfg)

        raw: List[Member] = []
        for g in groups:
            job.message = f"正在抓取群：{g}"
            if demo:
                records = _demo_members(g)
            else:
                records = client.fetch_members(g)
            for rec in records:
                raw.append(Member.from_raw(rec, group=g))
            job.groups_done += 1
            job.raw_count = len(raw)

        job.message = "去重 / 合并 / 过滤中…"
        fcfg = FilterConfig(
            require_username=opts.get("require_username", True),
            filter_ads=opts.get("filter_ads", True),
            filter_bots=opts.get("filter_bots", True),
            filter_scam_fake=opts.get("filter_scam", True),
            ad_threshold=int(opts.get("ad_threshold") or 2),
        )
        kept, removed, stats = run(raw, fcfg)

        # write downloadable files
        base = os.path.join(job.dir, "members")
        for fmt in ("csv", "json", "xlsx"):
            try:
                ext = "xlsx" if fmt == "xlsx" else fmt
                path = f"{base}.{ext}"
                write(kept, path, fmt)
                job.files[fmt] = path
            except Exception:  # xlsx optional
                pass

        job.rows = [m.to_row() for m in kept]
        job.stats = {
            "seen": stats.seen, "unique": stats.unique, "merged": stats.merged,
            "filtered": stats.filtered, "total_filtered": stats.total_filtered,
            "kept": stats.kept,
        }
        job.message = "完成"
        job.status = "done"
    except Exception as exc:  # noqa
        job.status = "error"
        job.error = str(exc)
        job.message = f"出错：{exc}"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    @app.get("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.post("/api/parse")
    def api_parse():
        data = request.get_json(force=True, silent=True) or {}
        groups, skipped = parse_many(data.get("text", ""))
        return jsonify({"groups": groups, "count": len(groups), "skipped": skipped})

    @app.post("/api/export")
    def api_export():
        data = request.get_json(force=True, silent=True) or {}
        groups, skipped = parse_many(data.get("text", ""))
        if not groups:
            return jsonify({"error": "没有解析到有效的群链接"}), 400

        opts = data.get("options", {}) or {}
        token = resolve_token(data.get("token"))
        base_url = resolve_base_url(data.get("base_url"))
        if not opts.get("demo") and not token:
            return jsonify({"error": "缺少密钥(Token)。请在设置里填写，或用演示模式。"}), 400

        job = Job(uuid.uuid4().hex[:12])
        with _LOCK:
            JOBS[job.id] = job
        t = threading.Thread(target=_run_job,
                             args=(job, groups, token or "", base_url, opts),
                             daemon=True)
        t.start()
        return jsonify({"job_id": job.id, "groups": groups, "skipped": skipped})

    @app.get("/api/job/<job_id>")
    def api_job(job_id):
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404
        return jsonify({
            "id": job.id, "status": job.status, "message": job.message,
            "groups_total": job.groups_total, "groups_done": job.groups_done,
            "raw_count": job.raw_count, "stats": job.stats,
            "error": job.error,
            "downloads": {k: f"/api/job/{job.id}/download/{k}" for k in job.files},
        })

    @app.get("/api/job/<job_id>/result")
    def api_result(job_id):
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404
        return jsonify({
            "columns": TABLE_COLUMNS,
            "labels": {c: COLUMN_LABELS.get(c, c) for c in TABLE_COLUMNS},
            "rows": job.rows,
            "stats": job.stats,
        })

    @app.get("/api/job/<job_id>/download/<fmt>")
    def api_download(job_id, fmt):
        job = JOBS.get(job_id)
        if not job or fmt not in job.files:
            return jsonify({"error": "not available"}), 404
        return send_file(job.files[fmt], as_attachment=True,
                         download_name=f"群成员_{job_id}.{ 'xlsx' if fmt=='xlsx' else fmt}")

    return app


def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    app = create_app()
    port = int(os.environ.get("PORT", port))
    import socket
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "127.0.0.1"
    print("=" * 56)
    print(" 群成员导出 · 网页版已启动")
    print(f"   本机访问：   http://127.0.0.1:{port}")
    print(f"   手机访问：   http://{ip}:{port}   (需与电脑同一WiFi)")
    print("   按 Ctrl+C 停止")
    print("=" * 56)
    app.run(host=host, port=port, threaded=True)
