import json
from ai_intelligence.models import PaymentEvent, FailureAnalysis
from ai_intelligence.services.llm_gateway import llm_gateway
from ai_intelligence.services.redaction import redact_data_structure, _sanitize_for_json

FAILURE_RESPONSE_SCHEMA = {
    "required": ["root_cause", "confidence", "explanation", "suggested_fixes"]
}

VALID_ROOT_CAUSES = {
    "timeout",
    "db_lock",
    "network_retry",
    "duplicate_request",
    "gateway_failure",
    "server_error",
    "unknown",
}


def analyze_failure(event: PaymentEvent) -> FailureAnalysis:
    """
    Analyzes a failed transaction using deterministic telemetry features and
    classifies the failure into a fixed taxonomy.
    """
    prior_events = list(
        PaymentEvent.objects.filter(idempotency_key=event.idempotency_key)
        .exclude(id=event.id)
        .order_by("-created_at")[:5]
        .values("event_type", "status_code", "created_at")
    )

    facts = {
        "status_code": event.status_code,
        "latency_ms": event.latency_ms,
        "error_detail": event.metadata.get("error_detail", "No specific exception logged"),
        "locked_at": event.metadata.get("locked_at"),
        "prior_events_for_key": prior_events,
    }

    scrubbed_facts = redact_data_structure(_sanitize_for_json(facts))

    result = llm_gateway.run(
        prompt_template="failure_analysis",
        variables={"facts_json": json.dumps(scrubbed_facts, default=str)},
        response_schema=FAILURE_RESPONSE_SCHEMA,
    )

    root_cause = result.get("root_cause", "unknown")
    if root_cause not in VALID_ROOT_CAUSES:
        root_cause = "unknown"

    try:
        confidence = float(result.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
    except (ValueError, TypeError):
        confidence = 0.5

    analysis_obj = FailureAnalysis.objects.create(
        event=event,
        root_cause=root_cause,
        confidence=confidence,
        explanation_text=result.get("explanation", "Analysis completed."),
        suggested_fixes=result.get("suggested_fixes", []),
    )
    return analysis_obj
