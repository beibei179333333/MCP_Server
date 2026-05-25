"""Automated Telegram group-member export & cleaning toolkit.

Pipeline: fetch (paginated, until complete) -> normalize -> dedup/merge
-> filter (no-username, ad/marketing) -> export (csv/json/xlsx).
"""

__version__ = "1.0.0"
