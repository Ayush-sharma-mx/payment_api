import datetime
import decimal
import logging
import uuid
from django.db import transaction
from .models import PaymentEvent
from .services.redaction import _sanitize_for_json

logger = logging.getLogger(__name__)


def on_payment_processed(sender, event_type, payment, idempotency_record, meta, **kwargs):
    """
    Receiver for payments.signals.payment_processed.
    Records append-only PaymentEvent and enqueues asynchronous AI analysis.
    NEVER breaks or interrupts the upstream database transaction.
    """
    try:
        api_key_prefix = ""
        if idempotency_record and hasattr(idempotency_record, "api_key") and idempotency_record.api_key:
            api_key_prefix = idempotency_record.api_key.prefix
        elif meta and meta.get("api_key_prefix"):
            api_key_prefix = meta.get("api_key_prefix")

        sanitized_meta = _sanitize_for_json(meta or {})

        try:
            with transaction.atomic():
                event = PaymentEvent.objects.create(
                    event_type=event_type,
                    payment_id=payment.id if payment else None,
                    idempotency_key=idempotency_record.idempotency_key if idempotency_record else meta.get("idempotency_key", ""),
                    request_fingerprint=idempotency_record.request_body_hash if idempotency_record and hasattr(idempotency_record, "request_body_hash") else meta.get("request_hash", ""),
                    api_key_prefix=api_key_prefix,
                    status_code=meta.get("status_code", 500),
                    latency_ms=meta.get("latency_ms"),
                    metadata=sanitized_meta,
                )
                logger.info(f"Recorded PaymentEvent #{event.id}: {event_type} for key {event.idempotency_key}")
        except Exception as db_err:
            logger.error(f"Failed to record PaymentEvent inside savepoint: {db_err}")
            return

        try:
            from .tasks import analyze_event
            analyze_event.delay(event.id)
        except Exception as task_err:
            logger.debug(f"Could not enqueue async analyze_event for PaymentEvent #{event.id}: {task_err}")
    except Exception as e:
        logger.error(f"Error in on_payment_processed receiver: {e}", exc_info=True)
