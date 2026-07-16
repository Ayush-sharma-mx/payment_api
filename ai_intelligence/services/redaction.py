import re
import json
import datetime
import decimal
import uuid

# Regex patterns for common PII and PCI-DSS sensitive data
CREDIT_CARD_REGEX = re.compile(r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|6(?:011|5[0-9][0-9])[0-9]{12}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|(?:2131|1800|35\d{3})\d{11})\b')
CVV_REGEX = re.compile(r'\b(?:cvv|cvc|cvv2|security_code)\s*[:=]\s*([0-9]{3,4})\b', re.IGNORECASE)
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')
PHONE_REGEX = re.compile(r'\b(?:\+?(\d{1,3}))?[-. (]*(\d{3})[-. )]*(\d{3})[-. ]*(\d{4})(?: *x(\d+))?\b')
SSN_REGEX = re.compile(r'\b\d{3}[-.]?\d{2}[-.]?\d{4}\b')


def _sanitize_for_json(obj):
    """Recursively convert datetimes, decimals, and UUIDs to strings for JSON serializability."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [_sanitize_for_json(item) for item in obj]
    elif isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    elif isinstance(obj, (decimal.Decimal, uuid.UUID)):
        return str(obj)
    return obj


def redact_pii(text: str) -> str:
    """
    Mandatory PII/PCI scrubber before any prompt is sent to a third-party LLM.
    Redacts card numbers, CVVs, emails, phone numbers, and SSNs.
    """
    if not text or not isinstance(text, str):
        return str(text) if text is not None else ""

    redacted = CREDIT_CARD_REGEX.sub("[REDACTED_CARD_NUMBER]", text)
    redacted = CVV_REGEX.sub(r"cvv: [REDACTED_CVV]", redacted)
    redacted = EMAIL_REGEX.sub("[REDACTED_EMAIL]", redacted)
    redacted = SSN_REGEX.sub("[REDACTED_SSN]", redacted)
    return redacted


def redact_data_structure(data):
    """Recursively scrub strings inside dictionaries or lists before prompt formatting."""
    if isinstance(data, str):
        return redact_pii(data)
    elif isinstance(data, dict):
        return {k: redact_data_structure(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [redact_data_structure(item) for item in data]
    return data
