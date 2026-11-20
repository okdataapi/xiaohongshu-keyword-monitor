"""Runs monitor.py against a local mock of the okdata API with canned answers. No network, no real key."""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
os.environ["NO_PROXY"] = "*"

import monitor as tool  # noqa: E402
from mock_okdata import TEST_KEY, MockOkdata, error, ok  # noqa: E402

API = json.loads((FIXTURES / "api.json").read_text(encoding="utf-8"))
BRAND = API["brand_id"]
ARGS = ["--keyword", "  露营　装备 ", "--account", f"https://www.xiaohongshu.com/user/profile/{BRAND}=露营品牌E",
        "--pages", "2"]


class MonitorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.run_index = 0
        self.api = MockOkdata({"/v1/xiaohongshu/notes/search": self.keyword_page,
                               "/v1/xiaohongshu/users/notes/list": self.account_page})
        tool.API = self.api.url
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "data"

    def tearDown(self) -> None:
        self.api.close()
        self.tmp.cleanup()

    def keyword_page(self, query: dict) -> tuple:
        pages = API["runs"][self.run_index]["keyword"]
        if query.get("cursor") == "p2":
            return 200, ok("xiaohongshu.notes.search", items=pages[1], amount="0.02")
        return 200, ok("xiaohongshu.notes.search", items=pages[0], next_cursor="p2", amount="0.02")

    def account_page(self, query: dict) -> tuple:
        if query["id"] != BRAND:
            return 404, error("not_found")
        return 200, ok("xiaohongshu.users.notes.list", items=API["runs"][self.run_index]["account"][0], amount="0.02")

    def run_tool(self, *argv: str, key: str = TEST_KEY, run: int = 0) -> tuple:
        self.run_index = run
        os.environ["OKDATA_API_KEY"] = key
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = tool.main([*argv, "--out", str(self.out)], now=lambda: API["runs"][run]["run_at"])
        return code, out.getvalue(), err.getvalue()

    def snapshots(self) -> str:
        return (self.out / "snapshots.csv").read_text(encoding="utf-8")

    def test_two_runs_append_one_csv_and_report_new_notes_and_movers(self) -> None:
        code, out, log = self.run_tool(*ARGS, run=0)
        self.assertEqual(code, 0, log)
        self.assertIn("(first run)", out)
        self.assertIn("spent $0.06", log)
        code, out, log = self.run_tool(*ARGS, run=1)
        self.assertEqual(code, 0, log)
        self.assertEqual(self.snapshots(), (FIXTURES / "expected-snapshots.csv").read_text(encoding="utf-8"))
        self.assertEqual(out, (FIXTURES / "expected-report.txt").read_text(encoding="utf-8"))
        searches = [r["query"] for r in self.api.paid() if "notes/search" in r["path"]]
        self.assertEqual([q.get("cursor") for q in searches], [None, "p2", None, "p2"])
        self.assertEqual({(q["query"], q["sort"], q["view"]) for q in searches}, {("露营 装备", "latest", "compact")})

    def test_report_in_chinese(self) -> None:
        self.run_tool(*ARGS, run=0)
        code, out, log = self.run_tool(*ARGS, "--lang", "zh", run=1)
        self.assertEqual(code, 0, log)
        self.assertEqual(out, (FIXTURES / "expected-report-zh.txt").read_text(encoding="utf-8"))
        self.assertIn("https://okdata.online/zh/", tool.links("zh")[0])

    def test_csv_rows_are_clipped_and_safe_for_spreadsheets(self) -> None:
        self.run_tool(*ARGS, run=0)
        rows = list(csv.DictReader(io.StringIO(self.snapshots())))
        by_id = {r["note_id"]: r for r in rows}
        formula = next(r for r in rows if "SUM" in r["title"])
        self.assertTrue(formula["title"].startswith("'="))
        self.assertTrue(formula["author_name"].startswith("'@"))
        long_text = next(r for r in rows if r["type"] == "video")
        self.assertLessEqual(len(long_text["title"]), tool.TITLE_LIMIT)
        self.assertTrue(long_text["title"].endswith("…"))
        self.assertNotIn("\n", long_text["title"])
        brand = [r for r in by_id.values() if r["source"] == f"account:{BRAND}"]
        self.assertEqual({r["author_name"] for r in brand}, {"露营品牌E"})

    def test_dry_run_needs_no_key_and_calls_nothing_paid(self) -> None:
        code, out, log = self.run_tool(*ARGS, "--dry-run", key="")
        self.assertEqual(code, 0, log)
        self.assertEqual(self.api.paid(), [])
        self.assertIn("at most $0.08", log)  # 2 sources x 2 pages
        self.assertFalse((self.out / "snapshots.csv").exists())

    def test_live_catalog_prices_win(self) -> None:
        self.api.prices = {"xiaohongshu.notes.search": "0.03", "xiaohongshu.users.notes.list": "0.02"}
        code, _, log = self.run_tool(*ARGS, "--dry-run", key="")
        self.assertEqual(code, 0)
        self.assertIn("at most $0.1", log)  # 2 x $0.03 + 2 x $0.02

    def test_over_budget_calls_nothing(self) -> None:
        code, _, log = self.run_tool(*ARGS, "--pages", "20", run=0)
        self.assertEqual(code, 3)
        self.assertIn("over the --budget of $0.5", log)
        self.assertEqual(self.api.paid(), [])

    def test_bad_key_stops_the_run(self) -> None:
        code, out, log = self.run_tool(*ARGS, key="okd_wrong", run=0)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("unauthorized", log)
        self.assertEqual(len(self.api.paid()), 1)  # stopped after the first call

    def test_missing_key(self) -> None:
        code, _, log = self.run_tool(*ARGS, key="", run=0)
        self.assertEqual(code, 2)
        self.assertIn("OKDATA_API_KEY is not set", log)

    def test_a_failed_account_keeps_the_keyword_rows(self) -> None:
        code, out, log = self.run_tool("--keyword", "露营装备", "--account", "5f" + "1" * 22, run=0)
        self.assertEqual(code, 4)
        self.assertIn("not_found", log)
        self.assertIn("Check the account id", log)
        self.assertIn("keyword:露营装备  2 notes", out)  # one page by default

    def test_foreign_csv_is_refused_before_any_paid_call(self) -> None:
        self.out.mkdir(parents=True)
        (self.out / "snapshots.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        code, _, log = self.run_tool(*ARGS, run=0)
        self.assertEqual(code, 1)
        self.assertIn("other columns", log)
        self.assertEqual(self.api.paid(), [])

    def test_retry_reuses_the_idempotency_key(self) -> None:
        answers = [(503, error("upstream_unavailable", retry="yes")),
                   (200, ok("xiaohongshu.notes.search", items=[], amount="0.02"))]
        self.api.routes["/v1/xiaohongshu/notes/search"] = lambda q: answers.pop(0)
        ok_client = tool.Okdata(TEST_KEY, sleep=lambda s: None)
        ok_client.call("xiaohongshu.notes.search", query="露营")
        keys = [r["headers"]["idempotency-key"] for r in self.api.paid()]
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(ok_client.spent, Decimal("0.02"))


class ArgumentTest(unittest.TestCase):
    def test_accounts(self) -> None:
        self.assertEqual(tool.account(f"https://www.xiaohongshu.com/user/profile/{BRAND.upper()}"), (BRAND, ""))
        self.assertEqual(tool.account(f" {BRAND} = 某 品牌 "), (BRAND, "某 品牌"))
        link = f"https://www.xiaohongshu.com/user/profile/{BRAND}?xsec_token=AB12=&xsec_source=pc_search"
        self.assertEqual(tool.account(link), (BRAND, ""))
        for bad in ("", "https://xhslink.com/a/abc", "5f12", "not an id"):
            with self.assertRaises(Exception):
                tool.account(bad)

    def test_keywords(self) -> None:
        self.assertEqual(tool.keyword(" 防晒霜　 推荐 "), "防晒霜 推荐")
        for bad in ("", "   ", "长" * 51):
            with self.assertRaises(Exception):
                tool.keyword(bad)

    def test_needs_something_to_monitor(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            tool.parse_args([])

    def test_duplicate_sources_are_called_once(self) -> None:
        sources = tool.plan_sources(["露营", "露营"], [BRAND, BRAND], "latest")
        self.assertEqual([s[0] for s in sources], ["keyword:露营", f"account:{BRAND}"])


if __name__ == "__main__":
    unittest.main()
