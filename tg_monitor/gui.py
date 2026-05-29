"""Tkinter 监控窗口：能显示在屏幕上实时盯着状态、日志，一键启停。

功能：
- 关键词 / 扫描间隔 / 冷却 可改
- 「框选监控区域」：弹出半透明全屏遮罩，拖一个框把 Telegram 窗口圈进去
- 「只提示不点击」演练开关
- 实时日志 + 统计（扫描 / 命中 / 点击次数）
- 开始 / 停止

不在电脑前也能用：把窗口放角落、点「开始监控」，它会一直盯着。
"""

from __future__ import annotations

import queue
from typing import Optional

from .config import MonitorConfig
from .monitor import Monitor, MonitorEvent


def run_gui(config: Optional[MonitorConfig] = None) -> None:
    import tkinter as tk
    from tkinter import ttk, messagebox

    cfg = config or MonitorConfig()
    events: "queue.Queue[MonitorEvent]" = queue.Queue()

    root = tk.Tk()
    root.title("Telegram 领取监控  ·  关键词自动点击")
    root.geometry("560x560")
    root.minsize(480, 480)

    monitor_holder = {"monitor": None}  # type: ignore

    # ---------- 顶部：设置 ----------
    frm = ttk.Frame(root, padding=10)
    frm.pack(fill="x")

    ttk.Label(frm, text="关键词（多个用空格 / 逗号分隔）：").grid(row=0, column=0, sticky="w")
    kw_var = tk.StringVar(value=" ".join(cfg.keywords))
    ttk.Entry(frm, textvariable=kw_var, width=40).grid(row=0, column=1, columnspan=3, sticky="we", pady=3)

    ttk.Label(frm, text="扫描间隔(秒)：").grid(row=1, column=0, sticky="w")
    interval_var = tk.StringVar(value=str(cfg.interval))
    ttk.Entry(frm, textvariable=interval_var, width=8).grid(row=1, column=1, sticky="w")

    ttk.Label(frm, text="点击冷却(秒)：").grid(row=1, column=2, sticky="e")
    cooldown_var = tk.StringVar(value=str(cfg.cooldown))
    ttk.Entry(frm, textvariable=cooldown_var, width=8).grid(row=1, column=3, sticky="w")

    region_var = tk.StringVar(value=_region_text(cfg.region))
    ttk.Label(frm, text="监控区域：").grid(row=2, column=0, sticky="w")
    ttk.Label(frm, textvariable=region_var, foreground="#0a7").grid(row=2, column=1, columnspan=2, sticky="w")

    dryrun_var = tk.BooleanVar(value=not cfg.auto_click)
    ttk.Checkbutton(frm, text="只提示不点击(演练)", variable=dryrun_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=3)
    sound_var = tk.BooleanVar(value=cfg.sound_alert)
    ttk.Checkbutton(frm, text="命中响铃提醒", variable=sound_var).grid(row=3, column=2, columnspan=2, sticky="w")

    frm.columnconfigure(1, weight=1)

    # ---------- 按钮行 ----------
    btns = ttk.Frame(root, padding=(10, 0))
    btns.pack(fill="x")

    def pick_region():
        reg = _select_region(root)
        if reg:
            cfg.region = reg
            region_var.set(_region_text(reg))

    select_btn = ttk.Button(btns, text="📐 框选监控区域", command=pick_region)
    select_btn.pack(side="left")

    def use_fullscreen():
        cfg.region = None
        region_var.set(_region_text(None))

    ttk.Button(btns, text="全屏", command=use_fullscreen).pack(side="left", padx=4)

    status_var = tk.StringVar(value="● 已停止")
    status_lbl = ttk.Label(btns, textvariable=status_var, foreground="#c00")
    status_lbl.pack(side="right")

    # ---------- 统计 ----------
    stats_var = tk.StringVar(value="扫描 0 · 命中 0 · 点击 0")
    ttk.Label(root, textvariable=stats_var, padding=(10, 4)).pack(fill="x")

    # ---------- 日志 ----------
    log_frame = ttk.Frame(root, padding=10)
    log_frame.pack(fill="both", expand=True)
    log = tk.Text(log_frame, height=14, wrap="word", state="disabled", font=("Consolas", 10))
    scroll = ttk.Scrollbar(log_frame, command=log.yview)
    log.configure(yscrollcommand=scroll.set)
    log.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    log.tag_config("hit", foreground="#d60")
    log.tag_config("click", foreground="#0a0")
    log.tag_config("error", foreground="#c00")
    log.tag_config("info", foreground="#06c")

    def append_log(text: str, tag: str = "") -> None:
        log.configure(state="normal")
        log.insert("end", text + "\n", tag)
        log.see("end")
        log.configure(state="disabled")

    # ---------- 启停 ----------
    def collect_config() -> Optional[MonitorConfig]:
        kws = [k for k in kw_var.get().replace("，", " ").replace(",", " ").split() if k]
        if not kws:
            messagebox.showwarning("提示", "请至少填一个关键词，比如：领取")
            return None
        try:
            interval = float(interval_var.get())
            cooldown = float(cooldown_var.get())
        except ValueError:
            messagebox.showwarning("提示", "间隔/冷却必须是数字")
            return None
        cfg.keywords = kws
        cfg.interval = max(0.2, interval)
        cfg.cooldown = max(0.0, cooldown)
        cfg.auto_click = not dryrun_var.get()
        cfg.sound_alert = sound_var.get()
        return cfg

    def on_event(ev: MonitorEvent):
        events.put(ev)  # 跨线程：丢进队列，由主线程轮询渲染

    def start():
        if monitor_holder["monitor"] and monitor_holder["monitor"].running:
            return
        c = collect_config()
        if not c:
            return
        if c.auto_click:
            ok = messagebox.askokcancel(
                "确认",
                "即将开启【自动点击】。\n监控时它会在检测到关键词时自动移动并点击你的鼠标。\n\n"
                "紧急中止：把鼠标快速甩到屏幕左上角即可。\n\n确定开始？",
            )
            if not ok:
                return
        m = Monitor(c, on_event=on_event)
        monitor_holder["monitor"] = m
        m.start()
        start_btn.configure(state="disabled")
        stop_btn.configure(state="normal")

    def stop():
        m = monitor_holder["monitor"]
        if m:
            m.stop()
        stop_btn.configure(state="disabled")

    start_btn = ttk.Button(btns, text="▶ 开始监控", command=start)
    start_btn.pack(side="left", padx=(12, 4))
    stop_btn = ttk.Button(btns, text="■ 停止", command=stop, state="disabled")
    stop_btn.pack(side="left")

    # ---------- 事件轮询 ----------
    def pump():
        try:
            while True:
                ev = events.get_nowait()
                _render_event(ev, append_log, status_var, stats_var, monitor_holder,
                              start_btn, stop_btn)
        except queue.Empty:
            pass
        root.after(120, pump)

    append_log("提示：先用「框选监控区域」把 Telegram 聊天窗口圈进去，识别更快更准。", "info")
    append_log("然后点「开始监控」。检测到关键词会自动点击；左上角甩鼠标可紧急中止。", "info")
    root.after(120, pump)

    def on_close():
        m = monitor_holder["monitor"]
        if m:
            m.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


def _render_event(ev, append_log, status_var, stats_var, holder, start_btn, stop_btn):
    import time
    ts = time.strftime("%H:%M:%S", time.localtime(ev.timestamp))
    tag = {"hit": "hit", "click": "click", "error": "error", "info": "info"}.get(ev.kind, "")
    if ev.kind == "state":
        if ev.message == "started":
            status_var.set("● 监控中")
        elif ev.message == "stopped":
            status_var.set("● 已停止")
            start_btn.configure(state="normal")
            stop_btn.configure(state="disabled")
        return
    if ev.kind == "scan":
        # 扫描刷状态栏即可，不刷屏日志
        m = holder["monitor"]
        if m:
            stats_var.set(f"扫描 {m.stats.scans} · 命中 {m.stats.hits} · 点击 {m.stats.clicks}")
        return
    if ev.message:
        append_log(f"[{ts}] {ev.message}", tag)
    m = holder["monitor"]
    if m:
        stats_var.set(f"扫描 {m.stats.scans} · 命中 {m.stats.hits} · 点击 {m.stats.clicks}")


def _region_text(region) -> str:
    if not region:
        return "全屏"
    l, t, w, h = region
    return f"({l}, {t})  {w}×{h}"


def _select_region(parent):
    """弹一个半透明全屏遮罩，拖动选一个矩形，返回 (left, top, w, h)。"""
    import tkinter as tk

    overlay = tk.Toplevel(parent)
    overlay.attributes("-fullscreen", True)
    try:
        overlay.attributes("-alpha", 0.25)
    except tk.TclError:
        pass
    overlay.configure(bg="black")
    overlay.attributes("-topmost", True)

    canvas = tk.Canvas(overlay, cursor="cross", bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    canvas.create_text(
        overlay.winfo_screenwidth() // 2, 40,
        text="按住鼠标拖动，把 Telegram 窗口框起来；松手确认，按 Esc 取消",
        fill="white", font=("微软雅黑", 16),
    )

    state = {"x0": 0, "y0": 0, "rect": None, "result": None}

    def on_press(e):
        state["x0"], state["y0"] = e.x_root, e.y_root
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#0f0", width=2)

    def on_drag(e):
        if state["rect"]:
            x0 = state["x0"] - overlay.winfo_rootx()
            y0 = state["y0"] - overlay.winfo_rooty()
            canvas.coords(state["rect"], x0, y0, e.x, e.y)

    def on_release(e):
        l = min(state["x0"], e.x_root)
        t = min(state["y0"], e.y_root)
        w = abs(e.x_root - state["x0"])
        h = abs(e.y_root - state["y0"])
        if w > 5 and h > 5:
            state["result"] = (int(l), int(t), int(w), int(h))
        overlay.destroy()

    def on_cancel(e=None):
        overlay.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    overlay.bind("<Escape>", on_cancel)
    overlay.grab_set()
    parent.wait_window(overlay)
    return state["result"]
