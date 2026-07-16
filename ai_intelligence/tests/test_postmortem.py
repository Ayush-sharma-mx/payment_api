from django.test import TestCase
from ai_intelligence.models import PaymentEvent, IncidentReport
from ai_intelligence.services.postmortem import draft_incident_postmortem


class PostmortemServiceTests(TestCase):
    def test_draft_incident_postmortem(self):
        for i in range(5):
            PaymentEvent.objects.create(
                event_type="payment_failed",
                idempotency_key=f"key_pm_{i}",
                request_fingerprint=f"hash_pm_{i}",
                api_key_prefix="pay_pm",
                status_code=502,
                latency_ms=120,
            )

        report = draft_incident_postmortem(title="Test Incident")
        self.assertIsInstance(report, IncidentReport)
        self.assertEqual(report.status, "draft")
        self.assertEqual(report.title, "Test Incident")
        self.assertGreater(len(report.recommended_fixes), 0)
