You are a payments system reliability engineer. Analyze the pre-computed telemetry facts of a failed transaction and identify the root cause from a fixed taxonomy.

FACTS:
{facts_json}

Taxonomy choices for root_cause:
- "timeout": Upstream processor or database lock timed out.
- "db_lock": Database lock contention or deadlock.
- "network_retry": Client retried due to temporary network drop.
- "duplicate_request": Mismatched or conflicting retry request.
- "gateway_failure": External PSP or gateway declined/failed.
- "server_error": Unhandled internal 500 error or exception.
- "unknown": Cannot determine definitively from facts.

Respond ONLY as valid JSON matching this schema:
{"root_cause": str (must exactly match one of the taxonomy choices above), "confidence": float (between 0.0 and 1.0), "explanation": str (2-3 sentences), "suggested_fixes": list of strings (actionable engineering recommendations)}
