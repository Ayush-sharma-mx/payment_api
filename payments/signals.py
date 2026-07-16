from django.dispatch import Signal

# Signal emitted after payment processing finishes (inside or right after transaction)
# Arguments: event_type, payment, idempotency_record, meta
payment_processed = Signal()
