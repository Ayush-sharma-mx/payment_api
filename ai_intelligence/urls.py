from django.urls import path
from . import views

urlpatterns = [
    path("events/", views.PaymentEventListView.as_view(), name="ai-event-list"),
    path("events/<int:pk>/", views.PaymentEventDetailView.as_view(), name="ai-event-detail"),
    path("risk-scores/", views.RiskScoreListView.as_view(), name="ai-risk-list"),
    path("anomalies/", views.LogAnomalyListView.as_view(), name="ai-anomaly-list"),
    path("incidents/", views.IncidentReportListView.as_view(), name="ai-incident-list"),
    path("incidents/draft/", views.DraftIncidentPostmortemView.as_view(), name="ai-incident-draft"),
    path("query/", views.NL2SQLQueryView.as_view(), name="ai-nl2sql-query"),
    path("query-logs/", views.AIQueryLogListView.as_view(), name="ai-query-log-list"),
]
