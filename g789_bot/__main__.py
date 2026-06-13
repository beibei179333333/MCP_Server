"""Entry point: ``python -m g789_bot``.

Modes:
  python -m g789_bot              run the bot (long polling)
  python -m g789_bot --selftest   load & validate the skill library offline (no tokens needed)
  python -m g789_bot --list [N]   print the first N scenarios
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from .config import Config
from .skills import Catalog


def _load_dotenv() -> None:
    """Populate os.environ from a local .env file if present (no dependency)."""
    path = Path(".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        os.environ.setdefault(key, value)


def _selftest() -> int:
    catalog = Catalog()
    n = len(catalog)
    print(f"Loaded {n} skills.")
    cats = catalog.categories()
    print(f"{len(cats)} categories. Top 10 by count:")
    for name, count in cats[:10]:
        print(f"  {name:<10} {count}")
    # Spot-check a couple of lookups.
    for probe in ("S-001", "42", "S-500"):
        s = catalog.get(probe)
        print(f"  get({probe!r}) -> {s.title if s else None}")
    hits = catalog.search("成人")
    print(f"  search('成人') -> {len(hits)} hits")
    ok = n == 500 and catalog.get("S-001") is not None
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def _list(limit: int) -> int:
    for s in Catalog().skills[:limit]:
        print(f"{s.id}  [{s.category}]  {s.name}")
    return 0


def main(argv: list[str]) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if argv and argv[0] == "--selftest":
        return _selftest()
    if argv and argv[0] == "--list":
        limit = int(argv[1]) if len(argv) > 1 else 50
        return _list(limit)

    _load_dotenv()
    config = Config.from_env()
    missing = config.missing()
    if missing:
        print("Missing required environment variables: " + ", ".join(missing))
        print("\nSet them and retry, e.g.:")
        print('  export TELEGRAM_BOT_TOKEN="123456:ABC..."')
        print('  export ANTHROPIC_API_KEY="sk-ant-..."')
        print("  python -m g789_bot")
        return 2

    from .bot import build_application

    app = build_application(config)
    catalog = app.bot_data["catalog"]
    log = logging.getLogger("g789_bot")
    log.info("Serving %d skills with model %s. Starting long polling…",
             len(catalog), config.model)
    app.run_polling(allowed_updates=None)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
