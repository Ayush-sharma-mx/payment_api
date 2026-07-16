from django.db import models
from django.utils import timezone


class PaymentEvent(models.Model):
    """Append-only log of everything the AI layer is allowed to see."""
    EVENT_TYPES = [
        ("payment_created", "Payment Created"),
        ("duplicate_detected", "Duplicate Detected"),
        ("payment_failed", "Payment Failed"),
        ("stale_lock_recovered", "Stale Lock Recovered"),
        ("payload_mismatch", "Payload Mismatch (422)"),
    ]
    event_type = models.CharField(max_length=32, choices=EVENT_TYPES, db_index=True)
    payment_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    idempotency_key = models.CharField(max_length=255, db_index=True)
    request_fingerprint = models.CharField(max_length=64)  # SHA-256, already computed upstream
    api_key_prefix = models.CharField(max_length=32)       # merchant identifier, never the secret
    status_code = models.IntegerField()
    latency_ms = models.IntegerField(null=True)
    metadata = models.JSONField(default=dict)  # locked_at, retry_count, lock_wait_ms, etc.
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["idempotency_key", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} - {self.idempotency_key} ({self.status_code})"


class DuplicateExplanation(models.Model):
    event = models.OneToOneField(PaymentEvent, on_delete=models.CASCADE, related_name="duplicate_explanation")
    explanation_text = models.TextField()
    reasoning_factors = models.JSONField(default=dict)
    llm_model_used = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Explanation for Event #{self.event_id}"


class FailureAnalysis(models.Model):
    ROOT_CAUSES = [
        ("timeout", "Timeout"),
        ("db_lock", "Database Lock"),
        ("network_retry", "Network Retry"),
        ("duplicate_request", "Duplicate Request"),
        ("gateway_failure", "Gateway Failure"),
        ("server_error", "Server Error"),
        ("unknown", "Unknown"),
    ]
    event = models.OneToOneField(PaymentEvent, on_delete=models.CASCADE, related_name="failure_analysis")
    root_cause = models.CharField(max_length=32, choices=ROOT_CAUSES)
    confidence = models.FloatField()
    explanation_text = models.TextField()
    suggested_fixes = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Failure Analysis #{self.event_id} ({self.root_cause})"


class RiskScore(models.Model):
    RISK_BANDS = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
    ]
    payment_id = models.CharField(max_length=64, db_index=True, null=True, blank=True)
    idempotency_key = models.CharField(max_length=255, db_index=True)
    score = models.FloatField()  # 0.0 - 1.0
    risk_band = models.CharField(max_length=16, choices=RISK_BANDS)
    factors = models.JSONField(default=dict)
    flagged_patterns = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"RiskScore {self.idempotency_key} ({self.score:.2f} - {self.risk_band})"


class LogAnomaly(models.Model):
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    anomaly_type = models.CharField(max_length=32)  # retry_spike, lock_contention, slow_query
    severity = models.CharField(max_length=16)      # low, medium, high
    summary = models.TextField()
    raw_metrics = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Anomaly: {self.anomaly_type} [{self.severity.upper()}]"


class IncidentReport(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("reviewed", "Reviewed"),
        ("published", "Published"),
    ]
    title = models.CharField(max_length=255)
    triggered_by_event = models.ForeignKey(PaymentEvent, null=True, blank=True, on_delete=models.SET_NULL)
    timeline = models.JSONField(default=list)
    affected_endpoints = models.JSONField(default=list)
    probable_cause = models.TextField()
    impact_summary = models.TextField()
    recommended_fixes = models.JSONField(default=list)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="draft")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Incident: {self.title} ({self.status})"


class AIQueryLog(models.Model):
    """Every NL dashboard question — full audit trail, mandatory for a fintech context."""
    user = models.CharField(max_length=150)
    question = models.TextField()
    generated_sql = models.TextField()
    sql_approved = models.BooleanField(default=False)
    execution_time_ms = models.IntegerField(null=True)
    result_summary = models.TextField(blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"NLQuery by {self.user} - Approved: {self.sql_approved}"
