from django.test import TestCase
from ai_intelligence.models import AIQueryLog, PaymentEvent
from ai_intelligence.services.nl2sql import validate_sql, execute_nl_query


class NL2SQLServiceTests(TestCase):
    def setUp(self):
        PaymentEvent.objects.create(
            event_type="duplicate_detected",
            idempotency_key="key_nl_1",
            request_fingerprint="hash_nl_1",
            api_key_prefix="pay_test",
            status_code=201,
            latency_ms=15,
        )

    def test_validate_sql_valid_select(self):
        sql = "SELECT event_type, status_code FROM ai_intelligence_paymentevent WHERE status_code = 201"
        is_valid, err, sanitized = validate_sql(sql)
        self.assertTrue(is_valid)
        self.assertIn("LIMIT 100", sanitized)

    def test_validate_sql_limit_clamping(self):
        sql = "SELECT * FROM ai_intelligence_paymentevent LIMIT 1000"
        is_valid, err, sanitized = validate_sql(sql)
        self.assertTrue(is_valid)
        self.assertIn("LIMIT 500", sanitized)

    def test_validate_sql_rejects_forbidden_tokens(self):
        sql = "DELETE FROM ai_intelligence_paymentevent WHERE id > 0"
        is_valid, err, sanitized = validate_sql(sql)
        self.assertFalse(is_valid)
        self.assertIn("Only SELECT", err or "forbidden")

    def test_validate_sql_rejects_non_whitelisted_table(self):
        sql = "SELECT * FROM auth_user"
        is_valid, err, sanitized = validate_sql(sql)
        self.assertFalse(is_valid)
        self.assertIn("not in the whitelisted schema", err)

    def test_execute_nl_query_pending_approval(self):
        res = execute_nl_query("investigator", "Show me duplicate payment events", auto_execute=False)
        self.assertEqual(res["status"], "pending_approval")
        self.assertTrue(AIQueryLog.objects.filter(id=res["log_id"]).exists())

    def test_execute_nl_query_auto_execute(self):
        res = execute_nl_query("investigator", "Show duplicate payments", auto_execute=True)
        self.assertEqual(res["status"], "success")
        self.assertIsInstance(res["rows"], list)
        self.assertGreaterEqual(len(res["rows"]), 1)
