import json
from datetime import timedelta
from django.utils import timezone
from ai_intelligence.models import PaymentEvent, RiskScore
from ai_intelligence.services.llm_gateway import llm_gateway
from ai_intelligence.services.redaction import redact_data_structure, _sanitize_for_json

RISK_RESPONSE_SCHEMA = {
    "required": ["adjusted_score", "risk_band", "explanation", "flagged_patterns"]
}


def compute_risk_score(event: PaymentEvent) -> RiskScore:
    """
    Hybrid Transaction Risk Engine (Rules + LLM).
    Computes deterministic base_score from quantitative features, then uses
    LLM for qualitative explanation and minor adjustment (bounded to ±0.1).
    """
    now = timezone.now()
    window_start = now - timedelta(minutes=5)

    recent_events = PaymentEvent.objects.filter(
        api_key_prefix=event.api_key_prefix,
        created_at__gte=window_start
    ) if event.api_key_prefix else PaymentEvent.objects.none()

    retry_velocity = recent_events.count()
    failed_count = recent_events.filter(status_code__gte=400).count()
    error_rate = (failed_count / retry_velocity) if retry_velocity > 0 else 0.0

    fingerprint_reused_different_key = False
    if event.request_fingerprint:
        fingerprint_reused_different_key = PaymentEvent.objects.filter(
            request_fingerprint=event.request_fingerprint
        ).exclude(idempotency_key=event.idempotency_key).exists()

    base_score = 0.1  # baseline nominal risk
    if retry_velocity > 10:
        base_score += min(0.3, (retry_velocity - 10) * 0.02)
    if fingerprint_reused_different_key:
        base_score += 0.4
    if error_rate > 0.5:
        base_score += 0.2

    base_score = round(max(0.0, min(1.0, base_score)), 3)

    facts = {
        "idempotency_key": event.idempotency_key,
        "api_key_prefix": event.api_key_prefix,
        "retry_velocity_last_5min": retry_velocity,
        "error_rate_last_5min": round(error_rate, 2),
        "fingerprint_reused_across_different_keys": fingerprint_reused_different_key,
        "base_score": base_score,
    }

    scrubbed_facts = redact_data_structure(facts)

    result = llm_gateway.run(
        prompt_template="risk_scoring",
        variables={"facts_json": json.dumps(scrubbed_facts, default=str)},
        response_schema=RISK_RESPONSE_SCHEMA,
    )

    try:
        raw_adjusted = float(result.get("adjusted_score", base_score))
    except (ValueError, TypeError):
        raw_adjusted = base_score

    delta = raw_adjusted - base_score
    if delta > 0.1:
        adjusted_score = base_score + 0.1
    elif delta < -0.1:
        adjusted_score = base_score - 0.1
    else:
        adjusted_score = raw_adjusted

    adjusted_score = round(max(0.0, min(1.0, adjusted_score)), 3)

    if adjusted_score >= 0.7:
        risk_band = "high"
    elif adjusted_score >= 0.4:
        risk_band = "medium"
    else:
        risk_band = "low"

    risk_obj = RiskScore.objects.create(
        payment_id=event.payment_id,
        idempotency_key=event.idempotency_key,
        score=adjusted_score,
        risk_band=risk_band,
        factors={
            **_sanitize_for_json(facts),
            "raw_llm_score": raw_adjusted,
            "final_clamped_score": adjusted_score,
            "explanation": result.get("explanation", ""),
        },
        flagged_patterns=result.get("flagged_patterns", []),
    )
    return risk_obj
