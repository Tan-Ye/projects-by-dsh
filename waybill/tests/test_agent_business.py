"""agent 业务纯函数的单元测试。

    python -m unittest discover -s tests -t tests -p "test_*.py" -v

这些函数不碰网络、不碰浏览器、不碰数据库，
所以测试就是"给数据、断言结果"。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from business.classify_policy import CONFIDENCE_THRESHOLD, decide  # noqa: E402
from business.mapping import (  # noqa: E402
    build_voucher,
    classify_account,
    match_department,
)
from business.parse import normalize_label, parse_count, parse_yuan  # noqa: E402
from business.repair import line_index, repair  # noqa: E402
from business.verify import verify_voucher  # noqa: E402


class ParseTest(unittest.TestCase):
    def test_parse_yuan(self) -> None:
        self.assertEqual(parse_yuan("￥128.60元"), 12860)
        self.assertEqual(parse_yuan("￥1,286.00元"), 128600)
        self.assertEqual(parse_yuan("0.07"), 7)
        for bad in ("", "abc", "-1", "1.005"):
            with self.assertRaises(ValueError):
                parse_yuan(bad)

    def test_normalize_label(self) -> None:
        self.assertEqual(normalize_label("单   号"), "单号")
        self.assertEqual(normalize_label("附单据数"), "附单据数")

    def test_parse_count(self) -> None:
        self.assertEqual(parse_count("3 张"), 3)
        self.assertEqual(parse_count("没有数字"), 0)


class MappingTest(unittest.TestCase):
    def test_rule_priority(self) -> None:
        # 同时含"打车"和"餐饮"时，规则表里排前面的赢——这是已知限制，钉住它
        code, _ = classify_account("跟客户吃饭顺便打车")
        self.assertEqual(code, "6601.03")

    def test_rule_miss_returns_none(self) -> None:
        code, pattern = classify_account("会议物料采购")
        self.assertIsNone(code)
        self.assertEqual(pattern, "")

    def test_match_department(self) -> None:
        departments = [{"code": "MKT", "name": "市场部", "is_active": 1}]
        self.assertEqual(match_department("市场部", departments), "MKT")
        self.assertIsNone(match_department("不存在部", departments))

    def test_build_voucher_uses_override_only_when_rule_misses(self) -> None:
        base = dict(
            doc_no="X",
            voucher_date="2024-10-01",
            reason="r",
            attachment_count=1,
            dept_code="MKT",
            cost_center="CC-MKT-01",
            rows=[{"费用说明": "会议物料采购", "金额": "￥300.00元"}],
            leaf_accounts={"6601.05.01"},
        )
        payload, problems = build_voucher(**base)
        self.assertEqual(payload["lines"], [])
        self.assertTrue(problems)

        payload, problems = build_voucher(
            **base, account_overrides={"会议物料采购": "6601.05.01"}
        )
        self.assertEqual(problems, [])
        self.assertEqual(payload["lines"][0]["account_code"], "6601.05.01")
        self.assertEqual(payload["lines"][0]["debit_cents"], 30000)


class RepairTest(unittest.TestCase):
    def test_line_index(self) -> None:
        self.assertEqual(line_index("lines[3].cost_center"), 3)
        self.assertIsNone(line_index("attachment_count"))

    def test_cost_center_is_repaired(self) -> None:
        payload = {
            "external_ref": "X",
            "voucher_date": "2024-10-01",
            "summary": "r",
            "dept_code": "MKT",
            "attachment_count": 1,
            "lines": [
                {
                    "account_code": "6601.03",
                    "cost_center": "CC-RD-01",
                    "debit_cents": 100,
                    "summary": "",
                }
            ],
        }
        errors = [
            {
                "field": "lines[0].cost_center",
                "code": "COST_CENTER_MISMATCH",
                "message": "不属于部门",
            }
        ]
        centers = [
            {"code": "CC-MKT-01", "name": "", "dept_code": "MKT", "is_default": 1, "is_active": 1}
        ]
        fixed, unfixable = repair(payload, errors, centers)
        self.assertEqual(unfixable, [])
        self.assertEqual(fixed["lines"][0]["cost_center"], "CC-MKT-01")

    def test_unknown_error_is_not_fixed(self) -> None:
        centers = [
            {"code": "CC-MKT-01", "name": "", "dept_code": "MKT", "is_default": 1, "is_active": 1}
        ]
        errors = [
            {"field": "lines[0].account_code", "code": "ACCOUNT_NOT_LEAF", "message": "不是末级"}
        ]
        _fixed, unfixable = repair(
            {
                "external_ref": "X",
                "voucher_date": "2024-10-01",
                "summary": "r",
                "dept_code": "MKT",
                "attachment_count": 1,
                "lines": [],
            },
            errors,
            centers,
        )
        self.assertEqual(len(unfixable), 1)


class PolicyTest(unittest.TestCase):
    def test_accept(self) -> None:
        decision = decide("6601.03", CONFIDENCE_THRESHOLD)
        self.assertTrue(decision["accepted"])
        self.assertEqual(decision["code"], "6601.03")

    def test_below_threshold(self) -> None:
        decision = decide("6601.03", 0.1)
        self.assertFalse(decision["accepted"])
        self.assertIsNone(decision["code"])
        self.assertIn("低于阈值", decision["reason"])

    def test_none(self) -> None:
        self.assertFalse(decide(None, 0.99)["accepted"])


class VerifyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = {"单号": "BX-1", "附单据数": "1 张"}
        self.rows = [{"金额": "￥128.60元"}]
        self.detail = {
            "external_ref": "BX-1",
            "total_cents": 12860,
            "lines": [{}],
            "dept_code": "MKT",
            "attachment_count": 1,
        }

    def test_all_pass(self) -> None:
        checks = verify_voucher(
            doc=self.doc, rows=self.rows, detail=self.detail, dept_code="MKT"
        )
        self.assertEqual(len(checks), 5)
        self.assertTrue(all(check["passed"] for check in checks))

    def test_amount_mismatch(self) -> None:
        detail = {**self.detail, "total_cents": 10000}
        checks = verify_voucher(
            doc=self.doc, rows=self.rows, detail=detail, dept_code="MKT"
        )
        failed = [check for check in checks if not check["passed"]]
        self.assertEqual([check["field"] for check in failed], ["total_cents"])
        self.assertEqual(failed[0]["reason_code"], "AMOUNT_MISMATCH")

    def test_row_count_mismatch(self) -> None:
        detail = {**self.detail, "lines": [{}, {}]}
        checks = verify_voucher(
            doc=self.doc, rows=self.rows, detail=detail, dept_code="MKT"
        )
        failed = [check for check in checks if not check["passed"]]
        self.assertEqual([check["field"] for check in failed], ["line_count"])


if __name__ == "__main__":
    unittest.main()
