from django.test import TestCase
from ai_intelligence.models import PaymentEvent, DuplicateExplanation, FailureAnalysis, RiskScore
from ai_intelligence.services.redaction import redact_pii
from ai_intelligence.services.llm_gateway import llm_gateway, LLMGatewayError
from ai_intelligence.services.duplicate_analyzer import analyze_duplicate
from ai_intelligence.services.failure_analyzer import analyze_failure
from ai_intelligence.services.risk_engine import compute_risk_score


class RedactionServiceTests(TestCase):
    def test_redact_credit_card(self):
        raw = "User card 4111222233334444 declined."
        redacted = redact_pii(raw)
        self.assertNotIn("4111222233334444", redacted)
        self.assertIn("[REDACTED_CARD_NUMBER]", redacted)

    def test_redact_cvv_and_email(self):
        raw = "Contact test@example.com with cvv: 123 immediately."
        redacted = redact_pii(raw)
        self.assertNotIn("test@example.com", redacted)
        self.assertNotIn("123", redacted)
        self.assertIn("[REDACTED_EMAIL]", redacted)


class LLMGatewayTests(TestCase):
    def test_run_mock_adapter_duplicate(self):
        result = llm_gateway.run("duplicate_analysis", {"facts_json": "{}"})
        self.assertIn("explanation", result)
        self.assertIn("_model", result)
        self.assertTrue(result["_model"].startswith("mock"))

    def test_missing_template_raises_error(self):
        with self.assertRaises(LLMGatewayError):
            llm_gateway.run("nonexistent_template_404", {})


class CoreAnalyzersTests(TestCase):
    def setUp(self):
        self.event = PaymentEvent.objects.create(
            event_type="duplicate_detected",
            payment_id="pay_123",
            idempotency_key="key_abc",
            request_fingerprint="hash_xyz",
            api_key_prefix="pay_test",
            status_code=201,
            latency_ms=12,
            metadata={"retry_count": 1}
        )

    def test_analyze_duplicate_service(self):
        explanation = analyze_duplicate(self.event)
        self.assertIsInstance(explanation, DuplicateExplanation)
        self.assertEqual(explanation.event, self.event)
        self.assertTrue(explanation.reasoning_factors["fingerprint_match"])

    def test_analyze_failure_service(self):
        fail_event = PaymentEvent.objects.create(
            event_type="payment_failed",
            idempotency_key="key_fail",
            request_fingerprint="hash_fail",
            api_key_prefix="pay_test",
            status_code=502,
            latency_ms=250,
            metadata={"error_detail": "Lock wait timeout exceeded"}
        )
        analysis = analyze_failure(fail_event)
        self.assertIsInstance(analysis, FailureAnalysis)
        self.assertEqual(analysis.root_cause, "timeout")
        self.assertGreater(analysis.confidence, 0.0)

    def test_compute_risk_score_hybrid_clamping(self):
        # Create multiple events to drive up base velocity and trigger fingerprint reuse across keys
        for i in range(15):
            PaymentEvent.objects.create(
                event_type="payment_failed",
                idempotency_key=f"key_{i}",
                request_fingerprint=self.event.request_fingerprint,  # reused fingerprint across different keys
                api_key_prefix="pay_test",
                status_code=409,
            )

        risk = compute_risk_score(self.event)
        self.assertIsInstance(risk, RiskScore)
        # Base score calculation: 0.1 + 0.12 (velocity) + 0.4 (shared hash) + 0.2 (error rate) = 0.82
        # Mock adjusted_score is 0.25, delta (-0.57) clamped to -0.1 -> 0.72!
        self.assertGreaterEqual(risk.score, 0.65)
        self.assertEqual(risk.risk_band, "high")
        self.assertEqual(risk.factors["final_clamped_score"], risk.score)
