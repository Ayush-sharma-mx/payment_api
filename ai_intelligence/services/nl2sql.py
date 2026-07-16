import re
import time
import logging
from django.db import connection
from ai_intelligence.models import AIQueryLog
from ai_intelligence.services.llm_gateway import llm_gateway

logger = logging.getLogger(__name__)

WHITELISTED_TABLES = {
    "ai_intelligence_paymentevent",
    "ai_intelligence_duplicateexplanation",
    "ai_intelligence_failureanalysis",
    "ai_intelligence_riskscore",
    "ai_intelligence_loganomaly",
}

WHITELISTED_SCHEMA_DESC = """
Tables available for querying:
1. ai_intelligence_paymentevent (id, event_type, payment_id, idempotency_key, request_fingerprint, api_key_prefix, status_code, latency_ms, created_at)
2. ai_intelligence_duplicateexplanation (id, event_id, explanation_text, llm_model_used, created_at)
3. ai_intelligence_failureanalysis (id, event_id, root_cause, confidence, explanation_text, created_at)
4. ai_intelligence_riskscore (id, payment_id, idempotency_key, score, risk_band, created_at)
5. ai_intelligence_loganomaly (id, window_start, window_end, anomaly_type, severity, summary, created_at)
"""

FORBIDDEN_SQL_REGEX = re.compile(
    r'\b(insert|update|delete|drop|alter|grant|truncate|exec|create|replace)\b|(--|\/\*)',
    re.IGNORECASE
)


def validate_sql(sql: str) -> tuple[bool, str, str]:
    """
    Static SQL validator guardrail for NL2SQL.
    Returns (is_valid, error_message, sanitized_sql).
    Enforces read-only SELECT, whitelisted schema tables, and LIMIT <= 500.
    """
    if not sql or not isinstance(sql, str):
        return False, "SQL string is empty.", ""

    clean_sql = sql.strip().rstrip(";")

    if not clean_sql.upper().startswith("SELECT"):
        return False, "Only SELECT queries are permitted.", clean_sql

    if FORBIDDEN_SQL_REGEX.search(clean_sql):
        return False, "SQL contains forbidden modification/comment tokens.", clean_sql

    found_tables = re.findall(r'\b(?:from|join)\s+([a-zA-Z0-9_]+)', clean_sql, re.IGNORECASE)
    if not found_tables:
        return False, "No valid whitelisted table specified in FROM clause.", clean_sql

    for t in found_tables:
        if t.lower() not in WHITELISTED_TABLES:
            return False, f"Table '{t}' is not in the whitelisted schema.", clean_sql

    limit_match = re.search(r'\blimit\s+(\d+)\b', clean_sql, re.IGNORECASE)
    if not limit_match:
        clean_sql += " LIMIT 100"
    else:
        limit_val = int(limit_match.group(1))
        if limit_val > 500:
            clean_sql = re.sub(r'\blimit\s+\d+\b', "LIMIT 500", clean_sql, flags=re.IGNORECASE)

    return True, "", clean_sql


def execute_nl_query(user: str, question: str, auto_execute: bool = False) -> dict:
    """
    Translates natural language to SQL, validates against safety guardrails,
    logs audit trail in AIQueryLog, and optionally executes the read-only query.
    """
    log_entry = AIQueryLog.objects.create(
        user=user or "anonymous",
        question=question,
        generated_sql="",
        sql_approved=auto_execute,
    )

    try:
        result = llm_gateway.run(
            prompt_template="nl2sql",
            variables={
                "schema": WHITELISTED_SCHEMA_DESC,
                "question": question,
            },
            response_schema={"required": ["sql"]},
        )
        raw_sql = result["sql"]
    except Exception as e:
        err_msg = f"Failed to generate SQL: {e}"
        log_entry.error = err_msg
        log_entry.save()
        return {"error": err_msg, "sql": "", "log_id": log_entry.id}

    is_valid, err, sanitized_sql = validate_sql(raw_sql)
    log_entry.generated_sql = sanitized_sql

    if not is_valid:
        log_entry.error = f"SQL Safety Validation Failed: {err}"
        log_entry.save()
        return {"error": log_entry.error, "sql": sanitized_sql, "log_id": log_entry.id}

    if not auto_execute:
        log_entry.save()
        return {
            "status": "pending_approval",
            "sql": sanitized_sql,
            "log_id": log_entry.id,
            "message": "SQL generated successfully. Set auto_execute=True or approve to run."
        }

    start_time = time.time()
    rows = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(sanitized_sql)
            columns = [col[0] for col in cursor.description] if cursor.description else []
            raw_rows = cursor.fetchall()
            for row in raw_rows:
                rows.append(dict(zip(columns, row)))

        exec_ms = int((time.time() - start_time) * 1000)
        log_entry.execution_time_ms = exec_ms
        log_entry.result_summary = f"Returned {len(rows)} rows in {exec_ms}ms."
        log_entry.save()
        return {
            "status": "success",
            "sql": sanitized_sql,
            "rows": rows,
            "execution_time_ms": exec_ms,
            "log_id": log_entry.id,
        }
    except Exception as db_err:
        exec_ms = int((time.time() - start_time) * 1000)
        log_entry.execution_time_ms = exec_ms
        log_entry.error = f"Database execution error: {db_err}"
        log_entry.save()
        return {"error": log_entry.error, "sql": sanitized_sql, "log_id": log_entry.id}
