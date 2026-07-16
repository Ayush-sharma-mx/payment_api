import hashlib
from rest_framework import permissions
from .models import APIKey


class HasAPIKey(permissions.BasePermission):
    """
    Custom permission class that checks for a valid, active API Key.
    Supports either:
      - X-API-Key: pay_abc123.xyz...
      - Authorization: Api-Key pay_abc123.xyz...
    """

    message = "Invalid or missing API key."

    def has_permission(self, request, view):
        api_key = request.headers.get("X-API-Key")

        if not api_key:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Api-Key "):
                api_key = auth_header.split(" ", 1)[1]

        if not api_key:
            return False

        hashed_key = hashlib.sha256(api_key.encode()).hexdigest()

        key_obj = APIKey.objects.filter(hashed_key=hashed_key, is_active=True).first()
        if key_obj:
            request.api_key = key_obj
            request.api_key_prefix = key_obj.prefix
            return True
        return False
