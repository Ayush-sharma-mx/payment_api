from django.test import TestCase
from ai_intelligence.models import PaymentEvent, DuplicateExplanation, RiskScore, LogAnomaly
from ai_intelligence.tasks import analyze_event, detect_log_anomalies


class TaskTests(TestCase):
    def test_analyze_event_duplicate_creates_explanation_and_risk(self):
        event = PaymentEvent.objects.create(
            event_type="duplicate_detected",
            payment_id="pay_999",
            idempotency_key="key_task_1",
            request_fingerprint="hash_task_1",
            api_key_prefix="pay_task",
            status_code=201,
            latency_ms=10,
        )
        analyze_event(event.id)

        # Check DuplicateExplanation created
        self.assertTrue(DuplicateExplanation.objects.filter(event=event).exists())
        # Check RiskScore created
        self.assertTrue(RiskScore.objects.filter(idempotency_key="key_task_1").exists())

    def test_detect_log_anomalies_triggers_during_error_spike(self):
        for i in range(6):
            PaymentEvent.objects.create(
                event_type="payment_failed",
                idempotency_key=f"key_err_{i}",
                request_fingerprint=f"hash_err_{i}",
                api_key_prefix="pay_task",
                status_code=500,
                latency_ms=600,
            )

        res = detect_log_anomalies()
        self.assertIn("Anomaly created", str(res))
        self.assertTrue(LogAnomaly.objects.filter(anomaly_type="error_spike").exists())
