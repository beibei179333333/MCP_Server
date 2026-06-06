"""Telegram SMM 自动增长引擎 (smm_growth).

读取一份 YAML 配置（频道列表、SMM 面板 API、主力/辅助服务、30 天渐进增长曲线），
计算每天每个频道应当下的单，并通过标准 SMM 面板 API v2 自动下单。

模块划分：
  * config.py   —— 解析 YAML 配置为带类型的数据结构（支持 ${ENV} 变量插值）。
  * curves.py   —— 渐进增长曲线 + 可复现的抖动（让数量看起来更自然）。
  * panel.py    —— SMM 面板 API v2 客户端（add / status / balance / services，含 dry-run）。
  * planner.py  —— 根据配置与日期计算「当天该下哪些单」。
  * runner.py   —— 实际执行：按频道/订单间隔下单，失败重试，主服务失败自动切备用。
  * cli.py      —— 命令行入口：plan / run / balance / status。

安全：API key 不写进仓库。配置里用 ${SMMFOLLOWS_API_KEY} 之类的占位符，
运行时从环境变量读取（见 README）。dry_run=true 时只演练不真正下单。
"""
from __future__ import annotations

__all__ = ["__version__"]
__version__ = "3.0"
