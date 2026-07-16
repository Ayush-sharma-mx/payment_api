import json
from datetime import timedelta
from django.utils import timezone
from ai_intelligence.models import PaymentEvent, IncidentReport
from ai_intelligence.services.llm_gateway import llm_gateway
from ai_intelligence.services.redaction import redact_data_structure, _sanitize_for_json

POSTMORTEM_RESPONSE_SCHEMA = {
    "required": ["probable_cause", "impact_summary", "recommended_fixes"]
}


def draft_incident_postmortem(title: str = None, triggered_by_event: PaymentEvent = None, time_window_minutes: int = 60) -> IncidentReport:
    """
    Drafts an engineering incident postmortem report using aggregated error metrics
    and AI cause/impact analysis. Created in 'draft' state for human review.
    """
    now = timezone.now()
    window_start = now - timedelta(minutes=time_window_minutes)

    events = PaymentEvent.objects.filter(created_at__gte=window_start)
    total_requests = events.count()
    failed_events = events.filter(status_code__gte=400)
    failed_count = failed_events.count()

    # Aggregate errors by status code
    status_breakdown = {}
    for ev in failed_events:
        sc = str(ev.status_code)
        status_breakdown[sc] = status_breakdown.get(sc, 0) + 1

    # Affected API keys / endpoints
    affected_keys = list(failed_events.values_list("api_key_prefix", flat=True).distinct())
    affected_endpoints = ["/api/payments/process-payment/"] if failed_count > 0 else []

    # Timeline sampling
    timeline = []
    if failed_count > 0:
        first_err = failed_events.order_by("created_at").first()
        last_err = failed_events.order_by("-created_at").first()
        timeline = [
            {"time": first_err.created_at.isoformat(), "event": f"Error spike detected (status {first_err.status_code})"},
            {"time": last_err.created_at.isoformat(), "event": f"Most recent recorded failure (status {last_err.status_code})"},
        ]

    metrics = {
        "time_window_minutes": time_window_minutes,
        "total_requests": total_requests,
        "failed_requests": failed_count,
        "error_rate": round(failed_count / total_requests, 3) if total_requests > 0 else 0.0,
        "status_code_breakdown": status_breakdown,
        "affected_api_key_prefixes": affected_keys,
        "sample_timeline": timeline,
    }

    scrubbed_metrics = redact_data_structure(_sanitize_for_json(metrics))

    result = llm_gateway.run(
        prompt_template="incident_postmortem",
        variables={"metrics_json": json.dumps(scrubbed_metrics, default=str)},
        response_schema=POSTMORTEM_RESPONSE_SCHEMA,
    )

    report_title = title or f"Incident Report: Payment Processing Disruption ({now.strftime('%Y-%m-%d %H:%M UTC')})"

    report = IncidentReport.objects.create(
        title=report_title,
        triggered_by_event=triggered_by_event,
        timeline=timeline,
        affected_endpoints=affected_endpoints,
        probable_cause=result.get("probable_cause", "Analysis pending."),
        impact_summary=result.get("impact_summary", f"{failed_count} failures observed across window."),
        recommended_fixes=result.get("recommended_fixes", []),
        status="draft",
    )
    return report
