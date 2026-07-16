from rest_framework import generics, status, views
from rest_framework.response import Response
from payments.permissions import HasAPIKey
from ai_intelligence.models import (
    PaymentEvent,
    RiskScore,
    LogAnomaly,
    IncidentReport,
    AIQueryLog,
)
from ai_intelligence.serializers import (
    PaymentEventSerializer,
    RiskScoreSerializer,
    LogAnomalySerializer,
    IncidentReportSerializer,
    AIQueryLogSerializer,
)
from ai_intelligence.services.nl2sql import execute_nl_query
from ai_intelligence.services.postmortem import draft_incident_postmortem


class PaymentEventListView(generics.ListAPIView):
    serializer_class = PaymentEventSerializer
    permission_classes = [HasAPIKey]

    def get_queryset(self):
        qs = PaymentEvent.objects.all()
        idempotency_key = self.request.query_params.get("idempotency_key")
        event_type = self.request.query_params.get("event_type")
        api_key_prefix = self.request.query_params.get("api_key_prefix")

        if idempotency_key:
            qs = qs.filter(idempotency_key=idempotency_key)
        if event_type:
            qs = qs.filter(event_type=event_type)
        if api_key_prefix:
            qs = qs.filter(api_key_prefix=api_key_prefix)
        return qs[:100]


class PaymentEventDetailView(generics.RetrieveAPIView):
    queryset = PaymentEvent.objects.all()
    serializer_class = PaymentEventSerializer
    permission_classes = [HasAPIKey]


class RiskScoreListView(generics.ListAPIView):
    serializer_class = RiskScoreSerializer
    permission_classes = [HasAPIKey]

    def get_queryset(self):
        qs = RiskScore.objects.all()
        idempotency_key = self.request.query_params.get("idempotency_key")
        risk_band = self.request.query_params.get("risk_band")
        if idempotency_key:
            qs = qs.filter(idempotency_key=idempotency_key)
        if risk_band:
            qs = qs.filter(risk_band=risk_band)
        return qs[:100]


class LogAnomalyListView(generics.ListAPIView):
    queryset = LogAnomaly.objects.all()
    serializer_class = LogAnomalySerializer
    permission_classes = [HasAPIKey]


class IncidentReportListView(generics.ListCreateAPIView):
    queryset = IncidentReport.objects.all()
    serializer_class = IncidentReportSerializer
    permission_classes = [HasAPIKey]


class DraftIncidentPostmortemView(views.APIView):
    permission_classes = [HasAPIKey]

    def post(self, request):
        title = request.data.get("title")
        try:
            window_minutes = int(request.data.get("time_window_minutes", 60))
        except (ValueError, TypeError):
            window_minutes = 60

        report = draft_incident_postmortem(title=title, time_window_minutes=window_minutes)
        serializer = IncidentReportSerializer(report)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class NL2SQLQueryView(views.APIView):
    """
    Sandboxed NL2SQL query endpoint.
    POST /api/ai/query/ -> {"question": "...", "auto_execute": true}
    """
    permission_classes = [HasAPIKey]

    def post(self, request):
        question = request.data.get("question")
        if not question:
            return Response({"error": "A 'question' parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        auto_execute = request.data.get("auto_execute", False)
        if isinstance(auto_execute, str):
            auto_execute = auto_execute.lower() == "true"

        user_id = getattr(request, "api_key_prefix", "unknown_client")
        result = execute_nl_query(user=user_id, question=question, auto_execute=auto_execute)

        if "error" in result and not result.get("sql"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_200_OK)


class AIQueryLogListView(generics.ListAPIView):
    queryset = AIQueryLog.objects.all()
    serializer_class = AIQueryLogSerializer
    permission_classes = [HasAPIKey]
