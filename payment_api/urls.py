"""
URL configuration for payment_api project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.shortcuts import render
import hashlib
from payments.models import APIKey

DEMO_RAW_API_KEY = "pay_demo.live_reviewer_test_key_2026"

def get_or_create_demo_api_key():
    try:
        prefix = "demo"
        hashed = hashlib.sha256(DEMO_RAW_API_KEY.encode()).hexdigest()
        key_obj = APIKey.objects.filter(prefix=prefix).first()
        if not key_obj:
            APIKey.objects.create(
                name="Live Reviewer Demo Key",
                prefix=prefix,
                hashed_key=hashed,
                is_active=True
            )
        elif not key_obj.is_active:
            key_obj.is_active = True
            key_obj.save()
    except Exception:
        pass
    return DEMO_RAW_API_KEY

def get_api_status_dict():
    return {
        "project": "Idempotent Payment API Backend + AI Intelligence Layer",
        "status": "Online & Active",
        "pitch": "Idempotent payment engine with an AI intelligence layer that explains duplicates, scores risk, and answers questions in plain English.",
        "endpoints": {
            "admin_panel": "/admin/",
            "list_payments": "/api/payments/",
            "process_payment": "/api/payments/process-payment/",
            "ai_events": "/api/ai/events/",
            "ai_risk_scores": "/api/ai/risk-scores/",
            "ai_nl2sql_query": "/api/ai/query/",
            "ai_incidents": "/api/ai/incidents/"
        }
    }

def home(request):
    accept_header = request.META.get('HTTP_ACCEPT', '').lower()
    if 'application/json' in accept_header or request.GET.get('format') == 'json':
        return JsonResponse(get_api_status_dict())
    
    demo_key = get_or_create_demo_api_key()
    return render(request, 'landing.html', {
        "status_json": get_api_status_dict(),
        "demo_api_key": demo_key,
        "host_url": request.build_absolute_uri('/')[:-1]
    })

def api_root(request):
    return JsonResponse(get_api_status_dict())

urlpatterns = [
    path('', home),
    path('api/', api_root),
    path('admin/', admin.site.urls),
    path('api/payments/', include('payments.urls')),
    path('api/ai/', include('ai_intelligence.urls')),
]
