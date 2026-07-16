from django.contrib import admin
from .models import (
    PaymentEvent,
    DuplicateExplanation,
    FailureAnalysis,
    RiskScore,
    LogAnomaly,
    IncidentReport,
    AIQueryLog,
)


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "payment_id", "idempotency_key", "status_code", "latency_ms", "created_at")
    list_filter = ("event_type", "status_code", "created_at")
    search_fields = ("payment_id", "idempotency_key", "api_key_prefix")
    readonly_fields = ("created_at",)


@admin.register(DuplicateExplanation)
class DuplicateExplanationAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "llm_model_used", "created_at")
    readonly_fields = ("created_at",)


@admin.register(FailureAnalysis)
class FailureAnalysisAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "root_cause", "confidence", "created_at")
    list_filter = ("root_cause", "created_at")
    readonly_fields = ("created_at",)


@admin.register(RiskScore)
class RiskScoreAdmin(admin.ModelAdmin):
    list_display = ("id", "payment_id", "idempotency_key", "score", "risk_band", "created_at")
    list_filter = ("risk_band", "created_at")
    search_fields = ("payment_id", "idempotency_key")
    readonly_fields = ("created_at",)


@admin.register(LogAnomaly)
class LogAnomalyAdmin(admin.ModelAdmin):
    list_display = ("id", "anomaly_type", "severity", "window_start", "window_end", "created_at")
    list_filter = ("severity", "anomaly_type", "created_at")
    readonly_fields = ("created_at",)


@admin.register(IncidentReport)
class IncidentReportAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "created_at")
    list_filter = ("status", "created_at")
    readonly_fields = ("created_at",)


@admin.register(AIQueryLog)
class AIQueryLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "question", "sql_approved", "execution_time_ms", "created_at")
    list_filter = ("sql_approved", "created_at")
    search_fields = ("user", "question", "generated_sql")
    readonly_fields = ("created_at",)
