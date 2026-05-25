"""Command-line entry point.

Examples
--------
  # discover available endpoints from the swagger spec
  python -m group_export discover

  # export one group, full clean pipeline, to xlsx + csv + json
  python -m group_export export --group -1001234567890 -o members --format all

  # export several groups and auto-merge/dedup across them
  python -m group_export export --group AAA --group BBB -o merged

  # also merge in members from previously exported files
  python -m group_export export --group AAA --merge-in old_export.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List

from .api import ApiClient, ApiConfig
from .config import resolve_base_url, resolve_token
from .export import write
from .filters import DEFAULT_AD_KEYWORDS, FilterConfig
from .models import Member
from .pipeline import run


def _load_members_from_file(path: str) -> List[Member]:
    ext = os.path.splitext(path)[1].lower()
    out: List[Member] = []
    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        recs = data if isinstance(data, list) else data.get("data", [])
        for r in recs:
            out.append(Member.from_raw(r, group=f"file:{os.path.basename(path)}"))
    elif ext == ".csv":
        import csv
        with open(path, "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                out.append(Member.from_raw(r, group=f"file:{os.path.basename(path)}"))
    else:
        raise SystemExit(f"unsupported --merge-in file type: {path}")
    return out


def _build_api_config(args, token: str, base_url: str) -> ApiConfig:
    return ApiConfig(
        base_url=base_url,
        token=token,
        endpoint=args.endpoint,
        method=args.method,
        group_param=args.group_param,
        page_param=args.page_param,
        size_param=args.size_param,
        page_size=args.page_size,
        paginate_by_offset=args.offset_pagination,
        page_starts_at=0 if args.offset_pagination else 1,
        extra_params=dict(p.split("=", 1) for p in (args.param or [])),
        verbose=not args.quiet,
    )


def cmd_discover(args) -> int:
    token = resolve_token(args.token)
    base_url = resolve_base_url(args.base_url)
    if not token:
        print("warning: no token provided; swagger may still be public", file=sys.stderr)
    client = ApiClient(ApiConfig(base_url=base_url, token=token or "", verbose=True))
    spec = client.fetch_spec()
    if not spec:
        print("No swagger spec reachable. Check base URL / network / token.")
        return 1
    paths = spec.get("paths", {})
    print(f"\n{len(paths)} paths found:\n")
    for path, ops in paths.items():
        for method, op in (ops or {}).items():
            if not isinstance(op, dict):
                continue
            summary = op.get("summary") or op.get("operationId") or ""
            print(f"  {method.upper():6} {path}   {summary}")
    found = client.discover_endpoint()
    if found:
        print(f"\nBest match for 'export group members': {found[1]} {found[0]}")
    return 0


def cmd_export(args) -> int:
    token = resolve_token(args.token)
    if not token:
        raise SystemExit(
            "No token. Pass --token, set GROUP_EXPORT_TOKEN, or create token.txt."
        )
    base_url = resolve_base_url(args.base_url)
    api_cfg = _build_api_config(args, token, base_url)
    client = ApiClient(api_cfg)

    raw_members: List[Member] = []

    # 1) fetch from each group (paginated until complete)
    for group in args.group or []:
        records = client.fetch_members(str(group))
        for rec in records:
            raw_members.append(Member.from_raw(rec, group=str(group)))

    # 2) optionally merge in previously exported files
    for path in args.merge_in or []:
        existing = _load_members_from_file(path)
        print(f"merged in {len(existing)} records from {path}")
        raw_members.extend(existing)

    if not raw_members:
        raise SystemExit("no members fetched/loaded; nothing to do.")

    # 3) dedup + merge + filter
    fcfg = FilterConfig(
        require_username=not args.keep_no_username,
        filter_ads=not args.keep_ads,
        filter_bots=not args.keep_bots,
        filter_scam_fake=not args.keep_scam,
        ad_keywords=_load_keywords(args.ad_keywords_file),
        ad_threshold=args.ad_threshold,
    )
    kept, removed, stats = run(raw_members, fcfg)

    # 4) export
    out_base = args.output
    fmts = ["csv", "json", "xlsx"] if args.format == "all" else [args.format]
    written = []
    for fmt in fmts:
        ext = "xlsx" if fmt in ("xlsx", "excel") else fmt
        path = f"{out_base}.{ext}"
        write(kept, path, fmt)
        written.append(path)

    if args.dump_removed and removed:
        rem_path = f"{out_base}.removed.csv"
        write([m for m, _ in removed], rem_path, "csv")
        written.append(rem_path)

    # 5) report
    print("\n===== SUMMARY =====")
    print(f"raw records seen : {stats.seen}")
    print(f"unique members   : {stats.unique}  (merged duplicates: {stats.merged})")
    for reason, n in sorted(stats.filtered.items()):
        print(f"filtered [{reason}] : {n}")
    print(f"total filtered   : {stats.total_filtered}")
    print(f"KEPT (exported)  : {stats.kept}")
    print("files written    : " + ", ".join(written))
    return 0


def cmd_serve(args) -> int:
    from .webapp import serve
    serve(host=args.host, port=args.port)
    return 0


def _load_keywords(path):
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as f:
        kws = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    return kws or DEFAULT_AD_KEYWORDS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="group_export",
        description="Automated Telegram group-member export & cleaning tool.",
    )
    p.add_argument("--token", help="JWT bearer token (or use env/token.txt).")
    p.add_argument("--base-url", help="API base URL (default http://fun-stat-bot.net).")
    p.add_argument("--quiet", action="store_true", help="less logging.")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="list swagger endpoints.")
    d.set_defaults(func=cmd_discover)

    s = sub.add_parser("serve", help="启动手机网页版（批量群链接导出）。")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)

    e = sub.add_parser("export", help="export + clean group members.")
    e.add_argument("--group", action="append",
                   help="group/chat id (repeatable for multi-group merge).")
    e.add_argument("-o", "--output", default="members",
                   help="output basename (no extension).")
    e.add_argument("--format", choices=["csv", "json", "xlsx", "all"], default="all")
    e.add_argument("--merge-in", action="append",
                   help="also merge members from a prior .json/.csv export.")
    # endpoint overrides
    e.add_argument("--endpoint", help="explicit export path (skip auto-discovery).")
    e.add_argument("--method", default="GET", choices=["GET", "POST"])
    e.add_argument("--group-param", help="name of the group-id parameter.")
    e.add_argument("--page-param", help="name of the page/offset parameter.")
    e.add_argument("--size-param", help="name of the page-size/limit parameter.")
    e.add_argument("--page-size", type=int, default=200)
    e.add_argument("--offset-pagination", action="store_true",
                   help="page-param is an item offset, not a page number.")
    e.add_argument("--param", action="append",
                   help="extra query param key=value (repeatable).")
    # filter toggles
    e.add_argument("--keep-no-username", action="store_true",
                   help="do NOT drop members without a username.")
    e.add_argument("--keep-ads", action="store_true",
                   help="do NOT drop ad/marketing accounts.")
    e.add_argument("--keep-bots", action="store_true")
    e.add_argument("--keep-scam", action="store_true")
    e.add_argument("--ad-threshold", type=int, default=2,
                   help="ad-score threshold for filtering (lower = stricter).")
    e.add_argument("--ad-keywords-file",
                   help="newline-delimited custom ad keyword list.")
    e.add_argument("--dump-removed", action="store_true",
                   help="also write a .removed.csv of filtered-out members.")
    e.set_defaults(func=cmd_export)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
