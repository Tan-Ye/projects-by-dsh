"""财务系统接口测试：起一个真服务，用 HTTP 打。

    python -m unittest discover -s tests -v

用独立的临时数据库，不会污染 systems/fin/fin.db。
校验延迟调成 10ms，避免每个用例真等 800ms。
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIN = ROOT / "systems" / "fin"

# 临时库放在仓库内：沙箱不允许在系统临时目录里建文件
TMP = ROOT / "tests" / ".tmp"
TMP.mkdir(exist_ok=True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _Server:
    """在被测进程里跑一个 uvicorn，用完杀掉。"""

    def __init__(self, db_path: Path, token_ttl: int = 900, delay_ms: int = 10) -> None:
        self.port = _free_port()
        env = os.environ.copy()
        env["FIN_DB"] = str(db_path)
        env["FIN_TOKEN_TTL"] = str(token_ttl)
        env["FIN_VALIDATE_DELAY_MS"] = str(delay_ms)
        self.proc = subprocess.Popen(
            [sys.executable, str(FIN / "run.py"), "--port", str(self.port)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._wait_ready()

    def _wait_ready(self) -> None:
        deadline = time.time() + 20
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("服务启动失败，退出码 %s" % self.proc.returncode)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1):
                    return
            except OSError:
                time.sleep(0.15)
        raise RuntimeError("服务 20 秒内没有就绪")

    def call(self, method: str, path: str, body=None, token: str | None = None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, json.loads(resp.read().decode() or "null")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, raw

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def _voucher(ref: str) -> dict:
    return {
        "external_ref": ref,
        "voucher_date": "2024-10-05",
        "summary": "测试报销",
        "dept_code": "MKT",
        "attachment_count": 1,
        "lines": [
            {"account_code": "6601.03", "cost_center": "CC-MKT-01",
             "debit_cents": 12860, "summary": "打车"}
        ],
    }


class FinApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.db_path = TMP / f"fin-api-{uuid.uuid4().hex[:8]}.db"
        cls.server = _Server(cls.db_path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.close()
        cls.db_path.unlink(missing_ok=True)

    def token(self, username: str, password: str) -> str:
        status, body = self.server.call("POST", "/api/login",
                                        {"username": username, "password": password})
        self.assertEqual(status, 200, body)
        return body["token"]

    # ---- 认证 ---------------------------------------------------------- #

    def test_health(self) -> None:
        status, body = self.server.call("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    def test_login_returns_role(self) -> None:
        status, body = self.server.call(
            "POST", "/api/login", {"username": "maker", "password": "maker123"})
        self.assertEqual(status, 200)
        self.assertEqual(body["role"], "maker")
        self.assertTrue(body["token"])
        self.assertIsInstance(body["expires_at"], int)

    def test_login_wrong_password(self) -> None:
        status, body = self.server.call(
            "POST", "/api/login", {"username": "maker", "password": "nope"})
        self.assertEqual(status, 401)
        self.assertEqual(body["code"], "INVALID_CREDENTIALS")

    def test_login_unknown_user_same_error(self) -> None:
        status, body = self.server.call(
            "POST", "/api/login", {"username": "ghost", "password": "x"})
        self.assertEqual((status, body["code"]), (401, "INVALID_CREDENTIALS"))

    def test_login_missing_field_uses_unified_shape(self) -> None:
        status, body = self.server.call("POST", "/api/login", {"username": "maker"})
        self.assertEqual(status, 422)
        self.assertEqual(body["code"], "VALIDATION_ERROR")
        self.assertEqual(body["errors"][0]["field"], "password")

    # ---- meta ---------------------------------------------------------- #

    def test_meta_requires_token(self) -> None:
        status, body = self.server.call("GET", "/api/meta/accounts")
        self.assertEqual(status, 401)
        self.assertEqual(body["code"], "AUTH_REQUIRED")

    def test_accounts_tree(self) -> None:
        token = self.token("maker", "maker123")
        status, tree = self.server.call("GET", "/api/meta/accounts", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]["code"], "6601")
        children = {node["code"]: node for node in tree[0]["children"]}
        self.assertEqual(len(children), 5)
        self.assertEqual(children["6601.05"]["is_leaf"], 0)
        self.assertEqual(len(children["6601.05"]["children"]), 2)
        self.assertEqual(children["6601.09"]["is_active"], 0)

    def test_cost_centers_default_first(self) -> None:
        token = self.token("maker", "maker123")
        status, rows = self.server.call("GET", "/api/meta/cost-centers?dept=SALES", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(rows[0]["code"], "CC-SALES-02")
        self.assertTrue(rows[0]["is_default"])

    def test_cost_centers_unknown_dept_404(self) -> None:
        token = self.token("maker", "maker123")
        status, body = self.server.call("GET", "/api/meta/cost-centers?dept=NOPE", token=token)
        self.assertEqual(status, 404)
        self.assertEqual(body["code"], "NOT_FOUND")

    # ---- 凭证 ---------------------------------------------------------- #

    def test_create_list_detail(self) -> None:
        token = self.token("maker", "maker123")
        status, body = self.server.call("POST", "/api/vouchers", _voucher("BX-A1"), token)
        self.assertEqual(status, 201, body)
        self.assertTrue(body["ok"])
        voucher_id = body["id"]

        status, page = self.server.call("GET", "/api/vouchers?external_ref=BX-A1", token=token)
        self.assertEqual(page["total"], 1)

        status, detail = self.server.call("GET", f"/api/vouchers/{voucher_id}", token=token)
        self.assertEqual(detail["total_cents"], 12860)
        self.assertTrue(detail["validated"])
        self.assertEqual([line["seq"] for line in detail["lines"]], [1])

    def test_duplicate_external_ref(self) -> None:
        token = self.token("maker", "maker123")
        self.server.call("POST", "/api/vouchers", _voucher("BX-DUP"), token)
        status, body = self.server.call("POST", "/api/vouchers", _voucher("BX-DUP"), token)
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], "DUPLICATE_DOC")

    def test_save_rejects_non_leaf_account(self) -> None:
        token = self.token("maker", "maker123")
        _, created = self.server.call("POST", "/api/vouchers", _voucher("BX-BAD"), token)
        payload = _voucher("BX-BAD")
        payload["lines"][0]["account_code"] = "6601.05"

        status, body = self.server.call("PUT", f"/api/vouchers/{created['id']}", payload, token)
        self.assertEqual(status, 200)
        self.assertFalse(body["ok"])
        self.assertIn("ACCOUNT_NOT_LEAF", [e["code"] for e in body["errors"]])

        _, detail = self.server.call("GET", f"/api/vouchers/{created['id']}", token=token)
        self.assertFalse(detail["validated"])

    def test_checker_cannot_edit(self) -> None:
        maker = self.token("maker", "maker123")
        checker = self.token("checker", "checker123")
        _, created = self.server.call("POST", "/api/vouchers", _voucher("BX-RO"), maker)
        voucher_id = created["id"]

        status, body = self.server.call("POST", "/api/vouchers", _voucher("BX-RO-2"), checker)
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "NOT_PERMITTED")

        status, body = self.server.call(
            "PUT", f"/api/vouchers/{voucher_id}", _voucher("BX-RO"), checker)
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "NOT_PERMITTED")

        status, body = self.server.call(
            "POST", f"/api/vouchers/{voucher_id}/submit", None, checker)
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "NOT_PERMITTED")

    def test_two_step_flow_and_state(self) -> None:
        maker = self.token("maker", "maker123")
        checker = self.token("checker", "checker123")
        _, created = self.server.call("POST", "/api/vouchers", _voucher("BX-FLOW"), maker)
        voucher_id = created["id"]

        # 第一步：制单人提交审批 → pending
        status, body = self.server.call("POST", f"/api/vouchers/{voucher_id}/submit", None, maker)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["status"], "pending")
        self.assertIsNone(body["voucher_no"])

        # 只有 checker 能把 pending 变成已入账
        status, body = self.server.call("POST", f"/api/vouchers/{voucher_id}/approve", None, maker)
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "NOT_PERMITTED")

        status, body = self.server.call("POST", f"/api/vouchers/{voucher_id}/approve", None, checker)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["status"], "submitted")
        self.assertTrue(body["voucher_no"].startswith("PZ-"))
        self.assertEqual(body["approved_by"], "checker")

        status, state = self.server.call("GET", "/api/state/BX-FLOW")
        self.assertEqual(status, 200)
        self.assertEqual(state["status"], "submitted")
        self.assertEqual(state["credit_cents"], state["total_cents"])

    def test_checker_rejects_back_to_draft(self) -> None:
        maker = self.token("maker", "maker123")
        checker = self.token("checker", "checker123")
        _, created = self.server.call("POST", "/api/vouchers", _voucher("BX-REJ"), maker)
        voucher_id = created["id"]
        self.server.call("POST", f"/api/vouchers/{voucher_id}/submit", None, maker)

        status, body = self.server.call(
            "POST", f"/api/vouchers/{voucher_id}/reject", {"note": "发票抬头不对"}, checker)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["status"], "draft")
        self.assertEqual(body["review_note"], "发票抬头不对")

        # 退回后制单人能继续改
        status, body = self.server.call(
            "PUT", f"/api/vouchers/{voucher_id}", _voucher("BX-REJ"), maker)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_pending_is_locked(self) -> None:
        maker = self.token("maker", "maker123")
        _, created = self.server.call("POST", "/api/vouchers", _voucher("BX-LOCK"), maker)
        voucher_id = created["id"]
        self.server.call("POST", f"/api/vouchers/{voucher_id}/submit", None, maker)

        status, body = self.server.call(
            "PUT", f"/api/vouchers/{voucher_id}", _voucher("BX-LOCK"), maker)
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], "NOT_DRAFT")

    def test_approve_requires_pending(self) -> None:
        maker = self.token("maker", "maker123")
        checker = self.token("checker", "checker123")
        _, created = self.server.call("POST", "/api/vouchers", _voucher("BX-EARLY"), maker)

        status, body = self.server.call(
            "POST", f"/api/vouchers/{created['id']}/approve", None, checker)
        self.assertEqual(status, 409)
        self.assertEqual(body["code"], "NOT_PENDING")


class TokenExpiryTest(unittest.TestCase):
    """单独起一个 TTL=1 秒的服务，验证过期分支。"""

    def test_expired_token(self) -> None:
        db_path = TMP / f"fin-expiry-{uuid.uuid4().hex[:8]}.db"
        server = _Server(db_path, token_ttl=1)
        try:
            status, body = server.call(
                "POST", "/api/login", {"username": "maker", "password": "maker123"})
            token = body["token"]
            time.sleep(1.3)
            status, body = server.call("GET", "/api/meta/accounts", token=token)
            self.assertEqual(status, 401)
            self.assertEqual(body["code"], "TOKEN_EXPIRED")
        finally:
            server.close()
            db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
