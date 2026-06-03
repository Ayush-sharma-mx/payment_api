
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import IdempotencyRecord

class PaymentView(APIView):
    def post(self, request):
        # 1. Get the key from the request headers
        key = request.headers.get('Idempotency-Key')
        
        if not key:
            return Response({"error": "Idempotency-Key header is required"}, status=400)
            
        # 2. Check if we've already processed a request with this key
        if IdempotencyRecord.objects.filter(idempotency_key=key).exists():
            record = IdempotencyRecord.objects.get(idempotency_key=key)
            return Response(record.response_data, status=record.status_code)
        
        # 3. Logic to process payment
        result = {"message": "Payment successful", "status": "success"}
        status_code = 200
        
        # 4. Save the result so future retries get this same response
        IdempotencyRecord.objects.create(
            idempotency_key=key, 
            response_data=result, 
            status_code=status_code
        )
            
        return Response(result, status=status_code)
# Create your views here.
