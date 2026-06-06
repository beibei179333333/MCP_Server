"""SMM 面板 API v2 客户端（smmfollows / smmstone / fenba 等 "Perfect Panel" 克隆）。

标准接口：向面板 URL POST 表单参数。
  * 下单    : key, action=add, service, link, quantity  (评论可带 comments)
  * 查询    : key, action=status, order  (或 orders=1,2,3)
  * 余额    : key, action=balance
  * 服务列表: key, action=services

dry_run=True 时不发任何网络请求，只回填一个模拟订单号，便于先演练、核对数量与花费。
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from .config import Panel

_FAKE_ORDER_SEQ = itertools.count(900000)


@dataclass
class OrderResult:
    """一次下单的结果。"""
    ok: bool
    panel: str
    service_id: int
    link: str
    quantity: int
    order_id: Optional[Any] = None
    error: Optional[str] = None
    dry_run: bool = False
    cost: float = 0.0
    payload: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        if self.dry_run:
            return (f"[DRY] {self.panel} svc={self.service_id} qty={self.quantity} "
                    f"→ {self.link}  (≈${self.cost:.4f})")
        if self.ok:
            return (f"[OK ] {self.panel} svc={self.service_id} qty={self.quantity} "
                    f"order={self.order_id} → {self.link}  (≈${self.cost:.4f})")
        return (f"[ERR] {self.panel} svc={self.service_id} qty={self.quantity} "
                f"→ {self.link}  :: {self.error}")


class PanelClient:
    """单个面板的下单/查询客户端。"""

    def __init__(self, panel: Panel, *, dry_run: bool = True, timeout: int = 60,
                 max_retries: int = 3, retry_delay: float = 5.0, verbose: bool = True):
        self.panel = panel
        self.dry_run = dry_run
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "smm-growth/3.0"})

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    # ---- 底层请求：失败重试 + 指数退避 -------------------------------------
    def _post(self, params: Dict[str, Any]) -> Dict[str, Any]:
        delay = self.retry_delay
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.post(self.panel.url, data=params,
                                         timeout=self.timeout)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"可重试状态码 {resp.status_code}")
                try:
                    return resp.json()
                except ValueError:
                    return {"error": f"非 JSON 响应: {resp.text[:200]}"}
            except requests.RequestException as exc:
                last_exc = exc
                if attempt == self.max_retries:
                    break
                self._log(f"    请求失败（{exc}）；{delay:.0f}s 后第 {attempt} 次重试")
                time.sleep(delay)
                delay *= 2
        return {"error": f"重试 {self.max_retries} 次后仍失败: {last_exc}"}

    # ---- 下单 --------------------------------------------------------------
    def add(self, service_id: int, link: str, quantity: int, *,
            cost: float = 0.0, extra: Optional[Dict[str, Any]] = None) -> OrderResult:
        params: Dict[str, Any] = {
            "key": self.panel.key,
            "action": "add",
            "service": service_id,
            "link": link,
            "quantity": quantity,
        }
        if extra:
            params.update(extra)

        if self.dry_run:
            return OrderResult(
                ok=True, panel=self.panel.name, service_id=service_id, link=link,
                quantity=quantity, order_id=next(_FAKE_ORDER_SEQ), dry_run=True,
                cost=cost, payload={**params, "key": "***"},
            )

        if not self.panel.has_key:
            return OrderResult(
                ok=False, panel=self.panel.name, service_id=service_id, link=link,
                quantity=quantity, error="缺少 API key（请设置对应环境变量）",
                cost=cost, payload={**params, "key": "***"},
            )

        data = self._post(params)
        if isinstance(data, dict) and data.get("order") is not None and not data.get("error"):
            return OrderResult(
                ok=True, panel=self.panel.name, service_id=service_id, link=link,
                quantity=quantity, order_id=data.get("order"), cost=cost,
                payload={**params, "key": "***"},
            )
        err = data.get("error") if isinstance(data, dict) else str(data)
        return OrderResult(
            ok=False, panel=self.panel.name, service_id=service_id, link=link,
            quantity=quantity, error=str(err or "未知错误"), cost=cost,
            payload={**params, "key": "***"},
        )

    # ---- 查询 / 余额 / 服务 -------------------------------------------------
    def status(self, order_ids: List[Any]) -> Dict[str, Any]:
        if not order_ids:
            return {}
        if len(order_ids) == 1:
            return self._post({"key": self.panel.key, "action": "status",
                               "order": order_ids[0]})
        return self._post({"key": self.panel.key, "action": "status",
                           "orders": ",".join(str(o) for o in order_ids)})

    def balance(self) -> Dict[str, Any]:
        return self._post({"key": self.panel.key, "action": "balance"})

    def services(self) -> Any:
        return self._post({"key": self.panel.key, "action": "services"})


def build_clients(campaign, *, dry_run: bool, verbose: bool = True
                  ) -> Dict[str, PanelClient]:
    """按配置里的每个面板建立一个 PanelClient。"""
    return {
        name: PanelClient(
            panel, dry_run=dry_run, verbose=verbose,
            max_retries=campaign.execution.max_retries,
            retry_delay=campaign.execution.retry_delay,
        )
        for name, panel in campaign.panels.items()
    }
