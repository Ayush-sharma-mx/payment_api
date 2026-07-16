import json
from django.utils import timezone
from ai_intelligence.models import PaymentEvent, DuplicateExplanation
from ai_intelligence.services.llm_gateway import llm_gateway
from ai_intelligence.services.redaction import redact_data_structure, _sanitize_for_json

DUPLICATE_RESPONSE_SCHEMA = {
    "required": ["explanation", "looks_normal", "recommendation"]
}


def analyze_duplicate(event: PaymentEvent) -> DuplicateExplanation:
    """
    Analyzes a duplicate_detected PaymentEvent using deterministic pre-computed facts
    plus LLM narration.
    """
    prior_events = list(
        PaymentEvent.objects.filter(idempotency_key=event.idempotency_key)
        .exclude(id=event.id)
        .order_by("-created_at")[:5]
        .values("event_type", "created_at", "status_code", "latency_ms")
    )

    first_attempt_dt = None
    if prior_events:
        first_attempt_dt = prior_events[-1]["created_at"]
    seconds_since_first = (event.created_at - first_attempt_dt).total_seconds() if first_attempt_dt else 0.0

    facts = {
        "fingerprint_match": True,  # SHA-256 matched upstream or body matched cached record
        "idempotency_key": event.idempotency_key,
        "retry_count": event.metadata.get("retry_count", len(prior_events)),
        "seconds_since_first_attempt": round(seconds_since_first, 2),
        "status_code": event.status_code,
        "prior_events_for_key": prior_events,
    }

    # Scrub any potential PII inside facts and ensure datetimes are stringified
    scrubbed_facts = redact_data_structure(_sanitize_for_json(facts))

    result = llm_gateway.run(
        prompt_template="duplicate_analysis",
        variables={"facts_json": json.dumps(scrubbed_facts, default=str)},
        response_schema=DUPLICATE_RESPONSE_SCHEMA,
    )

    explanation_obj = DuplicateExplanation.objects.create(
        event=event,
        explanation_text=result["explanation"],
        reasoning_factors={
            **scrubbed_facts,
            "looks_normal": result.get("looks_normal", True),
            "recommendation": result.get("recommendation", ""),
        },
        llm_model_used=result["_model"],
    )
    return explanation_obj
