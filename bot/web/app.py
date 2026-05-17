"""FastAPI 管理面板：仪表盘 / 用户 / 规则 / 群发 / 订阅。"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from starlette.middleware.sessions import SessionMiddleware

from ..config import BASE_DIR, settings
from ..database import (
    AutoReply,
    BroadcastJob,
    Chat,
    ForwardRule,
    LedgerAccount,
    LedgerEntry,
    Payment,
    SessionLocal,
    Subscription,
    User,
)

log = logging.getLogger(__name__)
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _is_auth(request: Request) -> bool:
    return bool(request.session.get("user"))


def require_login(request: Request):
    if not _is_auth(request):
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})


def create_app() -> FastAPI:
    app = FastAPI(title="Telegram Bot 控制台", docs_url=None, redoc_url=None)
    app.add_middleware(SessionMiddleware, secret_key=settings.web_secret, max_age=86400)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, err: str = ""):
        return templates.TemplateResponse("login.html", {"request": request, "err": err})

    @app.post("/login")
    async def do_login(request: Request, username: str = Form(...), password: str = Form(...)):
        if (
            secrets.compare_digest(username, settings.web_username)
            and secrets.compare_digest(password, settings.effective_web_password)
        ):
            request.session["user"] = username
            return RedirectResponse("/", status_code=303)
        return RedirectResponse("/login?err=1", status_code=303)

    @app.get("/logout")
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        if not _is_auth(request):
            return RedirectResponse("/login")
        async with SessionLocal() as s:
            users = (await s.execute(select(func.count(User.id)))).scalar() or 0
            chats = (await s.execute(select(func.count(Chat.id)).where(Chat.is_active.is_(True)))).scalar() or 0
            rules = (await s.execute(select(func.count(ForwardRule.id)))).scalar() or 0
            ar = (await s.execute(select(func.count(AutoReply.id)))).scalar() or 0
            entries = (await s.execute(select(func.count(LedgerEntry.id)))).scalar() or 0
            forwarded = (await s.execute(select(func.coalesce(func.sum(ForwardRule.forwarded_count), 0)))).scalar() or 0
            active_subs = (await s.execute(select(func.count(Subscription.id)).where(Subscription.status == "active"))).scalar() or 0
            revenue = (await s.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "paid"))).scalar() or 0
            recent_jobs = (await s.execute(select(BroadcastJob).order_by(BroadcastJob.id.desc()).limit(8))).scalars().all()
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "users": users, "chats": chats, "rules": rules, "ar": ar, "entries": entries,
                "forwarded": forwarded, "active_subs": active_subs, "revenue": revenue,
                "recent_jobs": recent_jobs, "now": datetime.utcnow(),
            },
        )

    @app.get("/users", response_class=HTMLResponse)
    async def users_view(request: Request, q: str = ""):
        if not _is_auth(request):
            return RedirectResponse("/login")
        async with SessionLocal() as s:
            stmt = select(User).order_by(desc(User.last_seen)).limit(200)
            if q:
                stmt = select(User).where(
                    (User.username.ilike(f"%{q}%"))
                    | (User.first_name.ilike(f"%{q}%"))
                ).limit(200)
            rows = (await s.execute(stmt)).scalars().all()
        return templates.TemplateResponse(
            "users.html", {"request": request, "users": rows, "q": q}
        )

    @app.get("/rules", response_class=HTMLResponse)
    async def rules_view(request: Request):
        if not _is_auth(request):
            return RedirectResponse("/login")
        async with SessionLocal() as s:
            rows = (await s.execute(select(ForwardRule).order_by(ForwardRule.id))).scalars().all()
        return templates.TemplateResponse(
            "rules.html", {"request": request, "rules": rows}
        )

    @app.post("/rules/{rid}/toggle")
    async def rule_toggle(request: Request, rid: int):
        if not _is_auth(request):
            return RedirectResponse("/login")
        async with SessionLocal() as s:
            r = await s.get(ForwardRule, rid)
            if r:
                r.enabled = not r.enabled
                await s.commit()
        return RedirectResponse("/rules", status_code=303)

    @app.post("/rules/{rid}/delete")
    async def rule_delete(request: Request, rid: int):
        if not _is_auth(request):
            return RedirectResponse("/login")
        async with SessionLocal() as s:
            r = await s.get(ForwardRule, rid)
            if r:
                await s.delete(r)
                await s.commit()
        return RedirectResponse("/rules", status_code=303)

    @app.get("/broadcasts", response_class=HTMLResponse)
    async def broadcasts_view(request: Request):
        if not _is_auth(request):
            return RedirectResponse("/login")
        async with SessionLocal() as s:
            rows = (await s.execute(select(BroadcastJob).order_by(BroadcastJob.id.desc()).limit(50))).scalars().all()
        return templates.TemplateResponse(
            "broadcasts.html", {"request": request, "jobs": rows}
        )

    @app.get("/subs", response_class=HTMLResponse)
    async def subs_view(request: Request):
        if not _is_auth(request):
            return RedirectResponse("/login")
        async with SessionLocal() as s:
            subs = (
                await s.execute(
                    select(Subscription).order_by(Subscription.id.desc()).limit(100)
                )
            ).scalars().all()
            pays = (
                await s.execute(select(Payment).order_by(Payment.id.desc()).limit(50))
            ).scalars().all()
        return templates.TemplateResponse(
            "subs.html", {"request": request, "subs": subs, "pays": pays}
        )

    @app.get("/chats", response_class=HTMLResponse)
    async def chats_view(request: Request):
        if not _is_auth(request):
            return RedirectResponse("/login")
        async with SessionLocal() as s:
            rows = (
                await s.execute(
                    select(Chat).where(Chat.is_active.is_(True))
                    .order_by(Chat.joined_at.desc())
                )
            ).scalars().all()
        return templates.TemplateResponse(
            "chats.html", {"request": request, "chats": rows}
        )

    @app.get("/autoreplies", response_class=HTMLResponse)
    async def ar_view(request: Request):
        if not _is_auth(request):
            return RedirectResponse("/login")
        async with SessionLocal() as s:
            rows = (
                await s.execute(select(AutoReply).order_by(AutoReply.id.desc()).limit(200))
            ).scalars().all()
        return templates.TemplateResponse(
            "autoreplies.html", {"request": request, "rules": rows}
        )

    @app.post("/autoreplies/{rid}/toggle")
    async def ar_toggle(request: Request, rid: int):
        if not _is_auth(request):
            return RedirectResponse("/login")
        async with SessionLocal() as s:
            r = await s.get(AutoReply, rid)
            if r:
                r.enabled = not r.enabled
                await s.commit()
        return RedirectResponse("/autoreplies", status_code=303)

    @app.post("/autoreplies/{rid}/delete")
    async def ar_delete(request: Request, rid: int):
        if not _is_auth(request):
            return RedirectResponse("/login")
        async with SessionLocal() as s:
            r = await s.get(AutoReply, rid)
            if r:
                await s.delete(r)
                await s.commit()
        return RedirectResponse("/autoreplies", status_code=303)

    @app.get("/ledger", response_class=HTMLResponse)
    async def ledger_view(request: Request):
        if not _is_auth(request):
            return RedirectResponse("/login")
        async with SessionLocal() as s:
            entries = (
                await s.execute(
                    select(LedgerEntry).order_by(LedgerEntry.id.desc()).limit(200)
                )
            ).scalars().all()
            total_in = (await s.execute(
                select(func.coalesce(func.sum(LedgerEntry.amount), 0))
                .where(LedgerEntry.kind == "income")
            )).scalar() or 0
            total_out = (await s.execute(
                select(func.coalesce(func.sum(LedgerEntry.amount), 0))
                .where(LedgerEntry.kind == "expense")
            )).scalar() or 0
        return templates.TemplateResponse(
            "ledger.html",
            {"request": request, "entries": entries,
             "total_in": float(total_in), "total_out": float(total_out)},
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_view(request: Request):
        if not _is_auth(request):
            return RedirectResponse("/login")
        return templates.TemplateResponse(
            "settings.html",
            {"request": request,
             "settings": settings,
             "host_link": f"http://{request.url.hostname}:{settings.web_port}"},
        )

    @app.get("/healthz")
    async def health():
        return {"status": "ok", "ts": datetime.utcnow().isoformat()}

    return app


async def start_web():
    if not settings.web_enabled:
        return
    import uvicorn

    app = create_app()
    cfg = uvicorn.Config(
        app,
        host=settings.web_host,
        port=settings.web_port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(cfg)
    log.info(
        "Web 面板：http://%s:%s  user=%s",
        settings.web_host, settings.web_port, settings.web_username,
    )
    await server.serve()
