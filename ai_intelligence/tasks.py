import logging
from django.utils import timezone
from datetime import timedelta
from ai_intelligence.models import PaymentEvent, LogAnomaly
from ai_intelligence.services.duplicate_analyzer import analyze_duplicate
from ai_intelligence.services.failure_analyzer import analyze_failure
from ai_intelligence.services.risk_engine import compute_risk_score
from ai_intelligence.services.llm_gateway import llm_gateway

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
except ImportError:
    def shared_task(*args, **kwargs):
        def decorator(func):
            func.delay = func
            return func
        if len(args) == 1 and callable(args[0]):
            args[0].delay = args[0]
            return args[0]
        return decorator


def _run_event_analysis(event_id: int):
    """Core logic for running event analyzers."""
    try:
        event = PaymentEvent.objects.get(id=event_id)
    except PaymentEvent.DoesNotExist:
        logger.warning(f"analyze_event called with non-existent PaymentEvent id={event_id}")
        return

    logger.info(f"Starting AI analysis for PaymentEvent #{event.id} ({event.event_type})")

    try:
        compute_risk_score(event)
    except Exception as e:
        logger.error(f"Error computing risk score for Event #{event.id}: {e}", exc_info=True)

    if event.event_type == "duplicate_detected":
        try:
            analyze_duplicate(event)
        except Exception as e:
            logger.error(f"Error analyzing duplicate for Event #{event.id}: {e}", exc_info=True)
    elif event.event_type in ("payment_failed", "stale_lock_recovered", "payload_mismatch"):
        try:
            analyze_failure(event)
        except Exception as e:
            logger.error(f"Error analyzing failure for Event #{event.id}: {e}", exc_info=True)


@shared_task(max_retries=3)
def analyze_event(event_id: int):
    """
    Asynchronous Celery worker task triggered when a PaymentEvent is created.
    Runs the appropriate analyzer (`duplicate`, `failure`, `risk`) based on event type.
    """
    return _run_event_analysis(event_id)


@shared_task
def detect_log_anomalies():
    """
    Periodic background task (e.g. runs every 5-15 minutes).
    Aggregates recent telemetry, detects spikes in 4xx/5xx or latency,
    and records LogAnomaly alerts.
    """
    now = timezone.now()
    window_start = now - timedelta(minutes=15)

    recent_events = PaymentEvent.objects.filter(created_at__gte=window_start)
    total_count = recent_events.count()
    if total_count == 0:
        return "No recent events in window."

    error_events = recent_events.filter(status_code__gte=400)
    error_count = error_events.count()
    error_rate = error_count / total_count

    high_latency_events = recent_events.filter(latency_ms__gt=500)
    high_latency_count = high_latency_events.count()

    if error_rate > 0.30 or error_count >= 5 or high_latency_count >= 3:
        anomaly_type = "error_spike" if error_rate > 0.30 else "latency_spike"
        summary_query = f"High {anomaly_type} detected: {error_count} errors out of {total_count} total requests in last 15 minutes."
        
        sample_rows = list(
            error_events.order_by("-created_at")[:10].values(
                "event_type", "status_code", "latency_ms", "idempotency_key", "api_key_prefix"
            )
        )

        try:
            result = llm_gateway.run(
                prompt_template="log_summary",
                variables={
                    "question": summary_query,
                    "rows": str(sample_rows),
                },
                response_schema={"required": ["summary"]},
            )
            summary_text = result["summary"]
        except Exception as e:
            logger.error(f"Failed to generate anomaly summary via LLM: {e}")
            summary_text = f"Automated anomaly detection triggered: {summary_query}"

        anomaly = LogAnomaly.objects.create(
            window_start=window_start,
            window_end=now,
            anomaly_type=anomaly_type,
            severity="high" if error_rate > 0.50 else "medium",
            summary=summary_text,
            raw_metrics={
                "total_count": total_count,
                "error_count": error_count,
                "error_rate": round(error_rate, 3),
                "high_latency_count": high_latency_count,
                "sample_rows": sample_rows,
            },
        )
        logger.info(f"Generated LogAnomaly #{anomaly.id} ({anomaly.anomaly_type})")
        return f"Anomaly created #{anomaly.id}"

    return "Nominal window, no anomaly detected."
