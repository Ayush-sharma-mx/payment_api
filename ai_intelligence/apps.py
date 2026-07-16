from django.apps import AppConfig


class AiIntelligenceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai_intelligence'
    verbose_name = 'AI Payment Intelligence Layer'

    def ready(self):
        try:
            from payments.signals import payment_processed
            from .receivers import on_payment_processed
            payment_processed.connect(on_payment_processed)
        except ImportError:
            pass
