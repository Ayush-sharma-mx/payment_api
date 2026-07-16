from rest_framework import serializers
from ai_intelligence.models import (
    PaymentEvent,
    DuplicateExplanation,
    FailureAnalysis,
    RiskScore,
    LogAnomaly,
    IncidentReport,
    AIQueryLog,
)


class DuplicateExplanationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DuplicateExplanation
        fields = "__all__"


class FailureAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = FailureAnalysis
        fields = "__all__"


class RiskScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskScore
        fields = "__all__"


class PaymentEventSerializer(serializers.ModelSerializer):
    duplicate_explanation = DuplicateExplanationSerializer(read_only=True)
    failure_analysis = FailureAnalysisSerializer(read_only=True)

    class Meta:
        model = PaymentEvent
        fields = "__all__"


class LogAnomalySerializer(serializers.ModelSerializer):
    class Meta:
        model = LogAnomaly
        fields = "__all__"


class IncidentReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidentReport
        fields = "__all__"


class AIQueryLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIQueryLog
        fields = "__all__"
