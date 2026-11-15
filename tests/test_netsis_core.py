import unittest
from decimal import Decimal
from unittest.mock import patch
from netsis_core import (
    NetsisRepository, NetsisSettings, Stock, PriceChange, AuditLogError,
    profit_margin, profit_markup, propose_change, round_up_to_90,
)


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.stock = Stock("abc", "Deneme", "", "", "", Decimal("100"), Decimal("120"))

    def test_margin_is_different_from_markup(self):
        self.assertEqual(profit_markup(Decimal("100"), Decimal("120")), Decimal("20"))
        self.assertEqual(profit_margin(Decimal("100"), Decimal("120")).quantize(Decimal(".01")), Decimal("16.67"))

    def test_zero_division_is_safe(self):
        self.assertIsNone(profit_markup(Decimal("0"), Decimal("20")))
        self.assertIsNone(profit_margin(Decimal("3"), Decimal("0")))

    def test_only_real_changes_become_preview(self):
        self.assertIsNone(propose_change(self.stock, "0", "0"))
        ch = propose_change(self.stock, "5", "10")
        self.assertEqual(ch.new_purchase, Decimal("105.00"))
        self.assertEqual(ch.new_sale, Decimal("132.00"))

    def test_rounding_never_lowers_price(self):
        self.assertEqual(round_up_to_90(Decimal("12.95")), Decimal("13.90"))
        self.assertEqual(round_up_to_90(Decimal("12.90")), Decimal("12.90"))

    def test_invalid_percentage_rejected(self):
        with self.assertRaises(ValueError):
            propose_change(self.stock, "-101", "0")


class FakeCursor:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.queries = []
        self.rowcount = 0

    def execute(self, query, *params):
        self.queries.append((query, params))
        if query.startswith("UPDATE"):
            self.rowcount = self.outcomes.pop(0)
        return self


class FakeConnection:
    def __init__(self, outcomes):
        self.cursor_obj = FakeCursor(outcomes)
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.change = PriceChange("abc", Decimal("10"), Decimal("20"),
                                  Decimal("11"), Decimal("22"))

    def test_read_only_rejects_write_before_connecting(self):
        settings = NetsisSettings("server", "db", write_enabled=False)
        repo = NetsisRepository(settings, connect_factory=lambda *_: self.fail("Bağlantı açılmamalı"))
        with self.assertRaises(PermissionError):
            repo.save_changes([self.change])

    def test_updates_only_changed_and_commits(self):
        conn = FakeConnection([1])
        repo = NetsisRepository(NetsisSettings("server", "db", write_enabled=True),
                                connect_factory=lambda *_: conn)
        with patch.object(repo, "_write_audit"):
            self.assertEqual(repo.save_changes([self.change]), 1)
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 0)
        self.assertEqual(len(conn.cursor_obj.queries), 1)
        sql, params = conn.cursor_obj.queries[0]
        self.assertIn("WHERE STOK_KODU=?", sql)
        self.assertEqual(params[2], "abc")

    def test_audit_failure_does_not_claim_sql_rollback(self):
        conn = FakeConnection([1])
        repo = NetsisRepository(NetsisSettings("server", "db", write_enabled=True),
                                connect_factory=lambda *_: conn)
        with patch.object(repo, "_write_audit", side_effect=OSError("disk full")):
            with self.assertRaises(AuditLogError):
                repo.save_changes([self.change])
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 0)

    def test_concurrent_price_change_rolls_back_everything(self):
        conn = FakeConnection([1, 0])
        other = PriceChange("def", Decimal("10"), Decimal("20"),
                            Decimal("12"), Decimal("24"))
        repo = NetsisRepository(NetsisSettings("server", "db", write_enabled=True),
                                connect_factory=lambda *_: conn)
        with self.assertRaises(RuntimeError):
            repo.save_changes([self.change, other])
        self.assertEqual(conn.commits, 0)
        self.assertEqual(conn.rollbacks, 1)
        self.assertTrue(conn.closed)


if __name__ == "__main__":
    unittest.main()
