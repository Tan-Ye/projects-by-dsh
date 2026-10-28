"""财务系统数据层与校验规则的单元测试（不起服务）。

    python -m unittest discover -s tests -v

直接用临时数据库，每个用例前重建，互不影响。
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "systems" / "fin"))

from app import config, db, validation  # noqa: E402

# 临时库放在仓库内：沙箱不允许在系统临时目录里建文件
TMP = ROOT / "tests" / ".tmp"
TMP.mkdir(exist_ok=True)


class FinUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = TMP / f"fin-unit-{uuid.uuid4().hex[:8]}.db"
        self.addCleanup(self.db_path.unlink, missing_ok=True)
        # 库路径由 config 持有，连接层每次建连接时现读——所以换测试库要改这里
        self._old_path = config.DB_PATH
        config.DB_PATH = self.db_path
        self.addCleanup(setattr, config, "DB_PATH", self._old_path)
        db.init_db()
        self.conn = db.connect()
        self.addCleanup(self.conn.close)

    # ---- 种子与幂等 ---------------------------------------------------- #

    def test_seed_counts(self) -> None:
        counts = {
            table: self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("accounts", "departments", "cost_centers", "users")
        }
        self.assertEqual(counts, {"accounts": 8, "departments": 6,
                                  "cost_centers": 13, "users": 2})

    def test_init_is_idempotent(self) -> None:
        db.init_db()
        db.init_db()
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], 8)

    # ---- 密码 ---------------------------------------------------------- #

    def test_password_roundtrip(self) -> None:
        hashed = db.hash_password("secret")
        self.assertTrue(db.verify_password("secret", hashed))
        self.assertFalse(db.verify_password("wrong", hashed))

    def test_password_salt_is_random(self) -> None:
        self.assertNotEqual(db.hash_password("secret"), db.hash_password("secret"))

    def test_verify_garbage_does_not_raise(self) -> None:
        self.assertFalse(db.verify_password("x", "not-a-hash"))

    # ---- 查询 ---------------------------------------------------------- #

    def test_get_user_filters_inactive(self) -> None:
        self.assertIsNotNone(db.get_user(self.conn, "maker"))
        self.conn.execute("UPDATE users SET is_active = 0 WHERE username = 'maker'")
        self.conn.commit()
        self.assertIsNone(db.get_user(self.conn, "maker"))

    def test_cost_centers_order(self) -> None:
        codes = [c["code"] for c in db.get_cost_centers(self.conn, "SALES")]
        self.assertEqual(codes, ["CC-SALES-02", "CC-SALES-01"])

    # ---- 校验规则 ------------------------------------------------------ #

    def _base(self) -> db.VoucherInput:
        return {
            "external_ref": "BX-U1",
            "voucher_date": "2024-10-05",
            "summary": "单测",
            "dept_code": "MKT",
            "attachment_count": 1,
            "lines": [{"account_code": "6601.03", "cost_center": "CC-MKT-01",
                       "debit_cents": 100, "summary": ""}],
        }

    def codes(self, data: db.VoucherInput) -> list[str]:
        return [e["code"] for e in validation.validate(self.conn, data)]

    def test_valid_payload_passes(self) -> None:
        self.assertEqual(self.codes(self._base()), [])

    def test_no_lines(self) -> None:
        data = self._base()
        data["lines"] = []
        self.assertIn("NO_LINES", self.codes(data))

    def test_attachment_required(self) -> None:
        data = self._base()
        data["attachment_count"] = 0
        self.assertIn("ATTACHMENT_REQUIRED", self.codes(data))

    def test_amount_must_be_positive(self) -> None:
        data = self._base()
        data["lines"][0]["debit_cents"] = 0
        self.assertIn("AMOUNT_INVALID", self.codes(data))

    def test_account_must_be_leaf(self) -> None:
        data = self._base()
        data["lines"][0]["account_code"] = "6601.05"
        self.assertIn("ACCOUNT_NOT_LEAF", self.codes(data))

    def test_inactive_account(self) -> None:
        data = self._base()
        data["lines"][0]["account_code"] = "6601.09"
        self.assertIn("ACCOUNT_INACTIVE", self.codes(data))

    def test_unknown_account(self) -> None:
        data = self._base()
        data["lines"][0]["account_code"] = "9999"
        self.assertIn("ACCOUNT_NOT_FOUND", self.codes(data))

    def test_cost_center_must_match_dept(self) -> None:
        data = self._base()
        data["lines"][0]["cost_center"] = "CC-RD-01"
        self.assertIn("COST_CENTER_MISMATCH", self.codes(data))

    def test_unknown_cost_center(self) -> None:
        data = self._base()
        data["lines"][0]["cost_center"] = "CC-NOPE"
        self.assertIn("COST_CENTER_MISMATCH", self.codes(data))

    # ---- 写入 ---------------------------------------------------------- #

    def test_create_and_get_voucher(self) -> None:
        voucher_id = db.create_voucher(self.conn, self._base(), "maker", [])
        detail = db.get_voucher(self.conn, voucher_id)
        assert detail is not None
        self.assertEqual(detail["status"], "draft")
        self.assertEqual(detail["total_cents"], 100)
        self.assertTrue(detail["validated"])
        self.assertEqual(detail["lines"][0]["seq"], 1)

    def test_replace_renumbers_seq(self) -> None:
        voucher_id = db.create_voucher(self.conn, self._base(), "maker", [])
        data = self._base()
        data["lines"] = [
            {"account_code": "6601.03", "cost_center": "CC-MKT-01", "debit_cents": 100, "summary": ""},
            {"account_code": "6601.01", "cost_center": "CC-MKT-01", "debit_cents": 200, "summary": ""},
            {"account_code": "6601.04", "cost_center": "CC-MKT-01", "debit_cents": 300, "summary": ""},
        ]
        db.replace_voucher(self.conn, voucher_id, data, [])
        detail = db.get_voucher(self.conn, voucher_id)
        assert detail is not None
        self.assertEqual([line["seq"] for line in detail["lines"]], [1, 2, 3])
        self.assertEqual(detail["total_cents"], 600)

    def test_errors_mark_not_validated(self) -> None:
        errors = [{"field": "lines[0].debit_cents", "code": "AMOUNT_INVALID", "message": "x"}]
        voucher_id = db.create_voucher(self.conn, self._base(), "maker", errors)
        detail = db.get_voucher(self.conn, voucher_id)
        assert detail is not None
        self.assertFalse(detail["validated"])
        self.assertEqual(len(detail["errors"]), 1)

    def test_duplicate_external_ref_raises_integrity(self) -> None:
        db.create_voucher(self.conn, self._base(), "maker", [])
        with self.assertRaises(sqlite3.IntegrityError):
            db.create_voucher(self.conn, self._base(), "maker", [])

    def test_list_filters_and_paginates(self) -> None:
        for i in range(3):
            data = self._base()
            data["external_ref"] = f"BX-L{i}"
            db.create_voucher(self.conn, data, "maker", [])

        page = db.list_vouchers(self.conn, page_size=2)
        self.assertEqual(page["total"], 3)
        self.assertEqual(len(page["items"]), 2)

        filtered = db.list_vouchers(self.conn, external_ref="BX-L1")
        self.assertEqual(filtered["total"], 1)


if __name__ == "__main__":
    unittest.main()
