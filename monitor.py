#!/usr/bin/env python3
"""Monitor Xiaohongshu (RedNote) keywords and accounts over time.

Each run searches the keywords you name and reads the newest notes of the accounts you name, appends one row per
note (likes, saves, comments, shares) to <out>/snapshots.csv, and prints a short report: the notes that are new
since the last run, and the ones whose likes + saves + comments grew the most between the last two runs. Run it
every day from cron or GitHub Actions and the CSV becomes a time series you can chart.

Data comes from the okdata API (https://okdata.online/?src=gh-xiaohongshu-keyword-monitor), $0.02 per page of
about 20 notes. Python 3.9+, standard library only. The key goes in the OKDATA_API_KEY environment variable.

    python3 monitor.py --keyword "露营装备" --account 562f892fe00dd8540fd94691
    python3 monitor.py --keyword "防晒霜 推荐" --sort popular --lang zh --dry-run
"""
from __future__ import annotations

import argparse
import csv
import http.client
import json
import os
import re
import sys
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

VERSION = "0.1.0"
SOURCE = "gh-xiaohongshu-keyword-monitor"
API = os.environ.get("OKDATA_BASE_URL", "https://api.okdata.online").rstrip("/")
KEYWORD_NOTES = "xiaohongshu.notes.search"
ACCOUNT_NOTES = "xiaohongshu.users.notes.list"
# Fallback prices (USD) if the free catalog cannot be read; the live catalog wins.
PRICES = {KEYWORD_NOTES: Decimal("0.02"), ACCOUNT_NOTES: Decimal("0.02")}
FIELDS = ["run_at", "source", "note_id", "url", "type", "author_id", "author_name", "title", "published_at",
          "likes", "saves", "comments", "shares"]
COUNTS = ("likes", "saves", "comments", "shares")
ENGAGEMENT = ("likes", "saves", "comments")  # what "interactions" adds up, as Xiaohongshu marketers count it
CSV_NAME = "snapshots.csv"
TITLE_LIMIT = 100  # characters kept in the CSV
REPORT_TITLE_LIMIT = 40  # characters shown in the report
KEYWORD_LIMIT = 50
SORTS = ("latest", "popular", "general")
# Errors that every later call would hit too, so the run stops instead of trying the next source.
STOP_CODES = {"unauthorized", "insufficient_balance", "key_budget_exceeded", "cost_cap_exceeded", "key_scope_denied",
              "account_suspended", "budget_reached"}
RETRY_STATUSES = {429, 500, 502, 503, 504}
WHITESPACE = re.compile("[\t\n\v\f\r    　]+")
ACCOUNT_ID = re.compile(r"^[0-9a-f]{24}$")
PROFILE_URL = re.compile(r"xiaohongshu\.com/user/profile/([0-9a-fA-F]{24})")
NAMED = re.compile(r"^(.*[0-9a-fA-F]{24})\s*=(.*)$", re.S)
INTEGER = re.compile(r"-?[0-9]+")
AMOUNT = re.compile(r"[0-9]+(\.[0-9]+)?")

Source = Tuple[str, str, Dict[str, str]]  # (label in the CSV, endpoint, parameters)

TEXT = {
    "en": {
        "run": "Xiaohongshu monitor run {current} ",
        "previous": "(previous run {previous})",
        "first": "(first run)",
        "per_source": "{n} notes",
        "first_saved": "First snapshot saved. Run again later to see new notes and the biggest movers.",
        "new": "New since the last run: {n}",
        "new_lead": "{likes} likes",
        "posted": "posted {date}",
        "more": "...and {n} more in the CSV",
        "movers": "Biggest movers since the last run (likes + saves + comments):",
        "no_movers": "No note gained likes, saves or comments between the last two runs.",
        "mover_lead": "+{n} interactions{pct}",
        "now": "now {likes} likes, {saves} saves, {comments} comments",
    },
    "zh": {
        "run": "小红书监控 {current}",
        "previous": "（上次 {previous}）",
        "first": "（首次运行）",
        "per_source": "{n} 篇",
        "first_saved": "已存下第一份快照。过一段时间再跑一次，就能看到新笔记和互动涨得最快的笔记。",
        "new": "上次以来的新笔记：{n} 篇",
        "new_lead": "{likes} 赞",
        "posted": "发布于 {date}",
        "more": "……另外 {n} 篇在 CSV 里",
        "movers": "互动涨得最多（赞 + 藏 + 评）：",
        "no_movers": "两次运行之间没有笔记的赞、藏、评有增长。",
        "mover_lead": "+{n} 互动{pct}",
        "now": "现在 {likes} 赞 {saves} 藏 {comments} 评",
    },
}


def links(lang: str) -> Tuple[str, str]:
    prefix = "/zh" if lang == "zh" else ""
    return (f"https://okdata.online{prefix}/signup/?src={SOURCE}", f"https://okdata.online{prefix}/console/?src={SOURCE}")


class ApiError(Exception):
    def __init__(self, code: str, message: str, *, charged: Optional[bool] = False, retry: str = "no",
                 retry_after: Optional[float] = None, amount: Any = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code, self.charged, self.retry, self.retry_after = code, charged, retry, retry_after
        self.amount = amount


class OutputError(Exception):
    """The CSV cannot be used: other columns, or not a writable file."""


class Okdata:
    """The two okdata calls this script needs, with safe retries and a hard spending cap."""

    def __init__(self, key: Optional[str], budget: Optional[Decimal] = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.key = key
        self.budget = budget
        self.sleep = sleep
        self.spent = Decimal("0")
        self.caps = dict(PRICES)

    def _headers(self, idempotency_key: Optional[str]) -> Dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": f"{SOURCE}/{VERSION} (python)"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def prices(self) -> Dict[str, Decimal]:
        """Current prices from the free catalog (no key needed); the built-in table if it cannot be read."""
        try:
            data = request_json(f"{API}/v1/catalog", self._headers(None), self.sleep)["data"]
            live = {e["id"]: dollars(e.get("maxCharge")) for e in data["endpoints"]}
            self.caps = {k: live.get(k) or v for k, v in PRICES.items()}
        except (ApiError, KeyError, TypeError, AttributeError):
            self.caps = dict(PRICES)
        return self.caps

    def call(self, endpoint: str, **params: Any) -> Dict[str, Any]:
        cap = self.caps.get(endpoint, Decimal("0"))
        if self.budget is not None and self.spent + cap > self.budget:
            raise ApiError("budget_reached", f"the next call could cost ${usd(cap)} and pass the --budget of "
                                             f"${usd(self.budget)}")
        query = urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{API}/v1/{endpoint.replace('.', '/')}?{query}"
        try:
            body = request_json(url, self._headers(str(uuid.uuid4())), self.sleep)
        except ApiError as err:
            if err.charged is True:  # keep the spend in step with the amount the API reports
                self.spent += dollars(err.amount) or Decimal("0")
            raise
        self.spent += dollars(((body.get("meta") or {}).get("billing") or {}).get("amount")) or Decimal("0")
        return body


def _http_error(exc: HTTPError) -> ApiError:
    try:
        body = json.loads(exc.read().decode("utf-8"))
    except (ValueError, OSError, http.client.HTTPException):  # not JSON, or the body was cut off
        body = None
    if isinstance(body, dict) and "code" in body:
        return ApiError(str(body["code"]), str(body.get("message")), charged=body.get("charged", False),
                        retry=str(body.get("retry", "no")), retry_after=body.get("retry_after_seconds"),
                        amount=body.get("amount"))
    return ApiError(f"http_{exc.code}", str(exc.reason), charged=None,
                    retry="yes" if exc.code in RETRY_STATUSES else "no")


def request_json(url: str, headers: Dict[str, str], sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """GET with up to 2 retries that reuse the same Idempotency-Key, so a lost answer is replayed instead of run
    twice. After a lost answer the call may still be running on the server, so a rate_limited reply is waited out."""
    retries, waits, ambiguous = 0, 0, False
    while True:
        try:
            with urlopen(Request(url, headers=headers), timeout=90) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if isinstance(body, dict) and body.get("code") == "ok":
                return body
            err = (ApiError(str(body.get("code")), str(body.get("message"))) if isinstance(body, dict)
                   else ApiError("bad_response", "unexpected answer", charged=None, retry="same_key"))
        except HTTPError as exc:
            err = _http_error(exc)
        except (OSError, ValueError, http.client.HTTPException) as exc:  # network, timeout, cut-off or non-JSON
            err = ApiError("connection_error", str(exc), charged=None, retry="same_key")
        ambiguous = ambiguous or err.charged is None
        if ambiguous and err.code == "rate_limited" and waits < 5:
            waits += 1
            sleep(_wait(err.retry_after, 1.0))
            continue
        if err.retry not in ("yes", "same_key") or retries == 2:
            if ambiguous and err.charged is False:
                err.charged = None  # an earlier attempt may still finish
            raise err
        sleep(_wait(err.retry_after, 2.0 ** retries))
        retries += 1


def _wait(value: Any, default: float) -> float:
    """Seconds to sleep: the server's hint if it is a sane number, capped at 30."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(seconds, 0.0), 30.0)


def use_utf8() -> None:
    """Chinese titles and emoji in and out, also on Windows consoles and pipes."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace" if stream is sys.stderr else "strict")


def dollars(value: Any) -> Optional[Decimal]:
    """An amount from the API ("0.02", 0.02 or 1e-8) as a Decimal; None if it is not a sane amount."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def usd(amount: Decimal) -> str:
    """0.020 -> "0.02", 1.50 -> "1.5"."""
    return format(amount.normalize(), "f")


def charged(err: ApiError) -> str:
    return {True: "yes", False: "no"}.get(err.charged, "unknown")  # type: ignore[arg-type]


def cell(value: Any) -> Any:
    """Text that starts like a spreadsheet formula gets a leading ' so Excel shows it instead of running it."""
    return "'" + value if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def clip(text: Any, limit: int) -> str:
    """One line, at most `limit` characters, with … where it was cut."""
    line = str(text or "").encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    line = WHITESPACE.sub(" ", line).strip(" ")
    return line if len(line) <= limit else line[: limit - 1].rstrip(" ") + "…"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- what to monitor ---------------------------------------------------------------------------------------------

def keyword(value: str) -> str:
    text = WHITESPACE.sub(" ", value).strip(" ")
    if not text or len(text) > KEYWORD_LIMIT:
        raise argparse.ArgumentTypeError(f"not a search keyword (1 to {KEYWORD_LIMIT} characters): {value!r}")
    return text


def account(value: str) -> Tuple[str, str]:
    """An id or profile link, optionally with =NAME right after the id. The account notes list gives the author's
    id but not the name, so NAME is what the CSV and the report call the account. Only an = that directly follows
    the 24-character id starts a name, so the query string of a copied link (?xsec_token=...) is left alone."""
    named = NAMED.match(value.strip())
    text, name = (named.group(1), WHITESPACE.sub(" ", named.group(2)).strip(" ")) if named else (value.strip(), "")
    found = PROFILE_URL.search(text)
    account_id = (found.group(1) if found else text).lower()
    if not ACCOUNT_ID.match(account_id):
        raise argparse.ArgumentTypeError(
            f"not a Xiaohongshu account id or profile link: {value!r} (use the 24-character id from "
            "xiaohongshu.com/user/profile/<id>; short xhslink.com links do not work)")
    return account_id, clip(name, TITLE_LIMIT)


def plan_sources(keywords: List[str], accounts: List[str], sort: str) -> List[Source]:
    planned = [(f"keyword:{k}", KEYWORD_NOTES, {"query": k, "sort": sort}) for k in keywords]
    planned += [(f"account:{a}", ACCOUNT_NOTES, {"id": a}) for a in accounts]
    unique: Dict[str, Source] = {}
    for source in planned:
        unique.setdefault(source[0], source)
    return list(unique.values())


def plan_cost(caps: Dict[str, Decimal], sources: List[Source], pages: int) -> Decimal:
    return sum((caps[endpoint] * pages for _, endpoint, _ in sources), Decimal("0"))


# --- fetching and storing ----------------------------------------------------------------------------------------

def notes(ok: Okdata, endpoint: str, params: Dict[str, str], pages: int,
          cached: List[str]) -> Iterator[Dict[str, Any]]:
    """The notes of one keyword or account, page by page. When a page is a copy the API fetched a little earlier
    (meta.cached), its fetch time goes into `cached`."""
    cursor = None
    for _ in range(pages):
        body = ok.call(endpoint, **params, cursor=cursor, view="compact")
        meta = body.get("meta") or {}
        if meta.get("cached"):
            cached.append(str(meta.get("fetched_at") or "?"))
        yield from (body.get("data") or {}).get("items") or []
        cursor = (body.get("page") or {}).get("next_cursor")
        if not cursor:
            return


def to_row(run_at: str, source: str, item: Dict[str, Any], names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    metrics = {k: int(v) if isinstance(v, float) and v.is_integer() else v
               for k, v in (item.get("metrics") or {}).items()}
    author = item.get("author") or {}
    return {
        "run_at": run_at,
        "source": source,
        "note_id": str(item.get("id") or ""),
        "url": item.get("url"),
        "type": item.get("type"),
        "author_id": author.get("id"),
        "author_name": clip(author.get("name"), TITLE_LIMIT) or (names or {}).get(str(author.get("id")), ""),
        "title": clip(item.get("title") or item.get("text"), TITLE_LIMIT),
        "published_at": item.get("published_at"),
        "likes": metrics.get("likes"),
        "saves": metrics.get("favorites"),
        "comments": metrics.get("comments"),
        "shares": metrics.get("shares"),
    }


def read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:  # -sig: also reads a file a spreadsheet saved
        reader = csv.DictReader(f, restval="")
        if reader.fieldnames != FIELDS:
            raise OutputError(f"{path} has other columns than this monitor writes; use another --out")
        return list(reader)


def check_writable(path: Path) -> None:
    """Fail before any paid call if the CSV could not be written afterwards."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not path.is_file():
        raise OutputError(f"{path} is not a file")
    if not os.access(path if path.exists() else path.parent, os.W_OK):
        raise OutputError(f"{path} is not writable")


def ends_with_newline(path: Path) -> bool:
    with path.open("rb") as f:
        f.seek(-1, os.SEEK_END)
        return f.read(1) in (b"\n", b"\r")


def append_rows(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists() or path.stat().st_size == 0
    newline_first = not fresh and not ends_with_newline(path)  # a file saved without a final newline
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        if newline_first:
            f.write("\n")
        if fresh:
            writer.writeheader()
        writer.writerows({k: cell(v) for k, v in row.items()} for row in rows)


# --- the report --------------------------------------------------------------------------------------------------

def number(value: Any) -> Optional[int]:
    return int(value) if value is not None and INTEGER.fullmatch(str(value)) else None


def count(value: Optional[int]) -> str:
    return "?" if value is None else f"{value:,}"


def interactions(row: Dict[str, str]) -> Optional[int]:
    values = [number(row[k]) for k in ENGAGEMENT]
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def growth_percent(growth: int, before: int) -> str:
    """Integer maths, rounded half up."""
    if before <= 0:
        return ""
    tenths = (growth * 1000 + before // 2) // before
    return f" (+{tenths // 10}.{tenths % 10}%)" if tenths else " (<0.1%)"


def width(text: str) -> int:
    """Columns the text takes in a terminal: Chinese characters take two."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def source_name(source: str, rows: List[Dict[str, str]]) -> str:
    """account:<id> plus the account's name, taken from its own notes (an account page can include
    collaborations, so the most common author wins)."""
    if not source.startswith("account:"):
        return source
    names: Dict[str, int] = {}
    for r in rows:
        if r["source"] == source and r["author_id"] == source[len("account:"):] and r["author_name"]:
            names[r["author_name"]] = names.get(r["author_name"], 0) + 1
    return f"{source} ({max(names, key=lambda n: (names[n], n))})" if names else source


def first_by_note(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    found: Dict[str, Dict[str, str]] = {}
    for row in rows:
        found.setdefault(row["note_id"], row)
    return found


def note_lines(lead: str, row: Dict[str, str], extra: str) -> List[str]:
    parts = [lead, row["author_name"] or "?", extra, clip(row["title"], REPORT_TITLE_LIMIT)]
    return ["  " + " · ".join(p for p in parts if p), f"    {row['url']}"]


def report(rows: List[Dict[str, str]], top: int, lang: str = "en") -> str:
    """New notes in the latest run, and the biggest interaction gains between the last two runs."""
    t = TEXT[lang]
    runs = sorted({r["run_at"] for r in rows})
    if not runs:
        return ""
    current = runs[-1]
    previous = runs[-2] if len(runs) > 1 else None
    now = [r for r in rows if r["run_at"] == current]
    per_source: Dict[str, int] = {}
    for r in now:
        per_source[r["source"]] = per_source.get(r["source"], 0) + 1
    names = {s: source_name(s, now) for s in per_source}
    widest = max(width(n) for n in names.values())
    head = t["previous"].format(previous=previous) if previous else t["first"]
    lines = [t["run"].format(current=current) + head]
    lines += [f"  {names[s]}{' ' * (widest - width(names[s]))}  " + t["per_source"].format(n=n)
              for s, n in per_source.items()]
    if previous is None:
        lines += ["", t["first_saved"]]
        return "\n".join(lines) + "\n"

    latest = first_by_note(now)
    seen = {r["note_id"] for r in rows if r["run_at"] < current}
    fresh = sorted((r for r in latest.values() if r["note_id"] not in seen),
                   key=lambda r: (-(number(r["likes"]) or 0), r["note_id"]))
    lines += ["", t["new"].format(n=len(fresh))]
    for r in fresh[:top]:
        lines += note_lines(t["new_lead"].format(likes=count(number(r["likes"]))), r,
                            t["posted"].format(date=(r["published_at"] or "?")[:10]))
    if len(fresh) > top:
        lines.append("  " + t["more"].format(n=len(fresh) - top))

    before = first_by_note([r for r in rows if r["run_at"] == previous])
    movers = []
    for r in latest.values():
        after = interactions(r)
        old = interactions(before[r["note_id"]]) if r["note_id"] in before else None
        if after is not None and old is not None and after > old:
            movers.append((after - old, old, r))
    movers.sort(key=lambda m: (-m[0], m[2]["note_id"]))
    lines += ["", t["movers"]]
    if not movers:
        lines.append("  " + t["no_movers"])
    for growth, old, r in movers[:top]:
        now_text = t["now"].format(likes=count(number(r["likes"])), saves=count(number(r["saves"])),
                                   comments=count(number(r["comments"])))
        lines += note_lines(t["mover_lead"].format(n=f"{growth:,}", pct=growth_percent(growth, old)), r, now_text)
    return "\n".join(lines) + "\n"


# --- the command -------------------------------------------------------------------------------------------------

def hint(code: str, lang: str) -> str:
    sign_up, console = links(lang)
    return {
        "unauthorized": f"Check OKDATA_API_KEY, or get a key at {sign_up}",
        "insufficient_balance": f"Top up at {console} and run again.",
        "key_budget_exceeded": f"This key reached the spending limit set for it at {console}",
        "budget_reached": "Stopped at --budget.",
        "cost_cap_exceeded": "The account reached its daily spending allowance; it resets at the next UTC day.",
        "not_found": "Check the account id.",
    }.get(code, "")


def run(args: argparse.Namespace, ok: Okdata, now: Callable[[], str]) -> int:
    names = {account_id: name for account_id, name in args.account or [] if name}
    sources = plan_sources(args.keyword or [], [account_id for account_id, _ in args.account or []], args.sort)
    most = plan_cost(ok.prices(), sources, args.pages)
    path = Path(args.out) / CSV_NAME
    sign_up, _ = links(args.lang)
    print(f"plan: {len(sources)} source(s) x up to {args.pages} page(s) = up to {len(sources) * args.pages} "
          f"call(s); at most ${usd(most)}", file=sys.stderr)
    for label, endpoint, _ in sources:
        print(f"  {label}  ({endpoint}, ${usd(ok.caps[endpoint])} per page)", file=sys.stderr)
    print(f"  appends to {path}", file=sys.stderr)
    if args.dry_run:
        return 0
    if most > args.budget:
        print(f"over the --budget of ${usd(args.budget)}; raise it or use fewer --pages", file=sys.stderr)
        return 3
    if not ok.key:
        print(f"OKDATA_API_KEY is not set. Get a key at {sign_up}", file=sys.stderr)
        return 2

    read_rows(path)  # refuse a foreign or unwritable CSV before spending anything
    check_writable(path)
    run_at = now()
    saved, failed, stopped = 0, 0, False
    for label, endpoint, params in sources:
        rows: List[Dict[str, Any]] = []
        cached: List[str] = []
        try:
            for item in notes(ok, endpoint, params, args.pages, cached):
                rows.append(to_row(run_at, label, item, names))
            note = f" (counts as of {min(cached)})" if cached else ""
            print(f"{label}: {len(rows)} notes{note}", file=sys.stderr)
        except ApiError as err:
            failed += 1
            print(f"{label}: {err} (charged: {charged(err)}). {hint(err.code, args.lang)}".rstrip(), file=sys.stderr)
            if err.code in STOP_CODES:
                stopped = True
                break
        finally:
            if rows:  # saved per source, so a later failure or Ctrl-C keeps what was paid for
                append_rows(path, rows)
                saved += len(rows)
    if saved:
        print(f"appended {saved} rows to {path}", file=sys.stderr)
        sys.stdout.write(report(read_rows(path), args.top, args.lang))
    print(f"spent ${usd(ok.spent)}", file=sys.stderr)
    if stopped or failed == len(sources):
        return 1
    return 4 if failed else 0


def money(value: str) -> Decimal:
    if not AMOUNT.fullmatch(value.strip()):
        raise argparse.ArgumentTypeError(f"not an amount in USD: {value!r}")
    return Decimal(value.strip())


def positive(value: str) -> int:
    if not re.fullmatch(r"[0-9]+", value.strip()) or int(value) < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return int(value)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        allow_abbrev=False,
        description="Monitor Xiaohongshu (RedNote) keywords and accounts: append the notes and their likes, saves, "
                    "comments and shares to a CSV, then report new notes and the biggest movers "
                    "(okdata API, $0.02 per page of about 20 notes).")
    p.add_argument("--keyword", action="append", type=keyword, metavar="TEXT",
                   help="search keywords, as typed into the Xiaohongshu search box (repeat for more)")
    p.add_argument("--account", action="append", type=account, metavar="ID",
                   help="an account id or xiaohongshu.com/user/profile/<id> link, optionally followed by =NAME "
                        "to name it in the CSV and the report (repeat for more)")
    p.add_argument("--sort", choices=SORTS, default="latest",
                   help="order of keyword results: latest, popular or general (default latest)")
    p.add_argument("--pages", type=positive, default=1, metavar="N",
                   help="pages per keyword or account, about 20 notes each (default 1)")
    p.add_argument("--out", default="data", metavar="DIR", help="folder for snapshots.csv (default data)")
    p.add_argument("--top", type=positive, default=5, metavar="N", help="how many new notes and movers to list (default 5)")
    p.add_argument("--budget", type=money, default=Decimal("0.5"), metavar="USD",
                   help="refuse runs that could cost more (USD, default 0.5)")
    p.add_argument("--lang", choices=tuple(TEXT), default="en", help="language of the report: en or zh (default en)")
    p.add_argument("--dry-run", action="store_true", help="print the plan and the most it can cost, then stop")
    args = p.parse_args(argv)
    if not (args.keyword or args.account):
        p.error("give at least one --keyword or --account")
    return args


def main(argv: Optional[List[str]] = None, now: Callable[[], str] = utc_now) -> int:
    use_utf8()
    args = parse_args(argv)
    ok = Okdata(os.environ.get("OKDATA_API_KEY", "").strip() or None, budget=args.budget)
    try:
        return run(args, ok, now)
    except (OutputError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
