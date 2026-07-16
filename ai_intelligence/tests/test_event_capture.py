import uuid
import secrets
import hashlib
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from payments.models import APIKey
from ai_intelligence.models import PaymentEvent


class EventCaptureTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.prefix = secrets.token_hex(4)
        self.secret = secrets.token_urlsafe(32)
        self.raw_key = f"pay_{self.prefix}.{self.secret}"
        hashed_key = hashlib.sha256(self.raw_key.encode()).hexdigest()
        self.api_key = APIKey.objects.create(
            name="Test Client",
            prefix=self.prefix,
            hashed_key=hashed_key,
        )
        self.headers = {
            "HTTP_X_API_KEY": self.raw_key,
            "HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4()),
        }
        self.payload = {
            "amount": "50.00",
            "currency": "USD",
            "payer_email": "test@example.com",
            "description": "Test Event Capture",
        }

    def test_payment_created_emits_event(self):
        initial_count = PaymentEvent.objects.count()
        response = self.client.post(
            "/api/payments/process-payment/",
            self.payload,
            format="json",
            **self.headers
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PaymentEvent.objects.count(), initial_count + 1)
        event = PaymentEvent.objects.latest("created_at")
        self.assertEqual(event.event_type, "payment_created")
        self.assertEqual(event.status_code, 201)
        self.assertEqual(event.idempotency_key, self.headers["HTTP_IDEMPOTENCY_KEY"])
        self.assertEqual(event.api_key_prefix, self.api_key.prefix)

    def test_duplicate_detected_emits_event(self):
        # First request
        self.client.post("/api/payments/process-payment/", self.payload, format="json", **self.headers)
        initial_count = PaymentEvent.objects.count()

        # Second request (duplicate)
        response = self.client.post("/api/payments/process-payment/", self.payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PaymentEvent.objects.count(), initial_count + 1)
        event = PaymentEvent.objects.latest("created_at")
        self.assertEqual(event.event_type, "duplicate_detected")

    def test_payload_mismatch_emits_event(self):
        self.client.post("/api/payments/process-payment/", self.payload, format="json", **self.headers)
        initial_count = PaymentEvent.objects.count()

        mismatched_payload = self.payload.copy()
        mismatched_payload["amount"] = "999.00"
        response = self.client.post("/api/payments/process-payment/", mismatched_payload, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(PaymentEvent.objects.count(), initial_count + 1)
        event = PaymentEvent.objects.latest("created_at")
        self.assertEqual(event.event_type, "payload_mismatch")
        self.assertEqual(event.status_code, 422)
