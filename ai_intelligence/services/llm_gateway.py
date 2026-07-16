import json
import logging
import os
from pathlib import Path
from django.conf import settings
from .redaction import redact_pii

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class LLMGatewayError(Exception):
    """Raised when the LLM gateway fails or returns invalid/malformed schema."""
    pass


class BaseAdapter:
    def call(self, prompt: str, model_name: str) -> tuple[str, str, int, int]:
        """Returns (raw_text, model_used, tokens_in, tokens_out)."""
        raise NotImplementedError


class MockAdapter(BaseAdapter):
    """Deterministic, high-quality local mock adapter for unit tests and local demonstrations."""
    def call(self, prompt: str, model_name: str) -> tuple[str, str, int, int]:
        prompt_lower = prompt.lower()
        if "duplicate payment request" in prompt_lower or "duplicate_analysis" in prompt_lower or "looks_normal" in prompt_lower:
            response = {
                "explanation": "Duplicate detected because the incoming request fingerprint exactly matched a previous processing attempt for the same Idempotency-Key. This appears to be a client retry after a network timeout.",
                "looks_normal": True,
                "recommendation": "Return the cached response from the completed idempotency record without re-processing."
            }
        elif "taxonomy choices for root_cause" in prompt_lower or "failure_analysis" in prompt_lower:
            response = {
                "root_cause": "timeout",
                "confidence": 0.92,
                "explanation": "Transaction failed due to an upstream database lock wait timeout exceeding threshold during concurrent key processing.",
                "suggested_fixes": ["Verify select_for_update wait settings.", "Ensure client backoff on 409 Conflict retries."]
            }
        elif "deterministic rules engine has computed a base risk score" in prompt_lower or "adjusted_score" in prompt_lower:
            response = {
                "adjusted_score": 0.25,
                "risk_band": "low",
                "explanation": "The quantitative base score indicates normal transaction velocity and standard payment amounts for this API key. No card-testing or suspicious key rotation patterns detected.",
                "flagged_patterns": []
            }
        elif "incident postmortem report" in prompt_lower or "probable_cause" in prompt_lower:
            response = {
                "probable_cause": "Database lock contention spike on IdempotencyRecord table during high-velocity retry burst from API key pay_9ffb.",
                "impact_summary": "Affected 14 payment requests over a 5-minute window with increased 409 and 502 error responses.",
                "recommended_fixes": ["Implement exponential jittered backoff on client SDKs.", "Optimize index on request_body_hash and idempotency_key."]
            }
        elif "whitelisted schema description" in prompt_lower or "select" in prompt_lower:
            # NL2SQL generator mock
            if "duplicate" in prompt_lower:
                response = {"sql": "SELECT event_type, COUNT(*) as count FROM ai_intelligence_paymentevent WHERE event_type = 'duplicate_detected' GROUP BY event_type LIMIT 100"}
            elif "fail" in prompt_lower or "rejected" in prompt_lower:
                response = {"sql": "SELECT status_code, COUNT(*) as count FROM ai_intelligence_paymentevent WHERE status_code >= 400 GROUP BY status_code LIMIT 100"}
            else:
                response = {"sql": "SELECT event_type, status_code, latency_ms FROM ai_intelligence_paymentevent ORDER BY created_at DESC LIMIT 50"}
        else:
            # Default summary
            response = {"summary": "Analysis completed successfully. Metrics indicate nominal operation within expected statistical bounds."}

        return json.dumps(response), f"mock-{model_name}", 150, 85


class AnthropicAdapter(BaseAdapter):
    def call(self, prompt: str, model_name: str) -> tuple[str, str, int, int]:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=getattr(settings, "AI_API_KEY", ""))
            resp = client.messages.create(
                model=model_name or "claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            text = resp.content[0].text
            return text, resp.model, resp.usage.input_tokens, resp.usage.output_tokens
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise LLMGatewayError(f"Anthropic provider failed: {e}")


class OpenAIAdapter(BaseAdapter):
    def call(self, prompt: str, model_name: str) -> tuple[str, str, int, int]:
        try:
            import openai
            client = openai.OpenAI(api_key=getattr(settings, "AI_API_KEY", ""))
            resp = client.chat.completions.create(
                model=model_name or "gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            text = resp.choices[0].message.content
            return text, resp.model, resp.usage.prompt_tokens, resp.usage.completion_tokens
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise LLMGatewayError(f"OpenAI provider failed: {e}")


class LLMGateway:
    """Single choke point for all model calls — swap providers here only."""

    def __init__(self):
        self.provider_name = getattr(settings, "AI_PROVIDER", "mock").lower()
        self.model_name = getattr(settings, "AI_MODEL_NAME", "claude-3-5-sonnet-20241022")
        self.adapters = {
            "mock": MockAdapter(),
            "anthropic": AnthropicAdapter(),
            "openai": OpenAIAdapter(),
        }

    def _get_adapter(self) -> BaseAdapter:
        return self.adapters.get(self.provider_name, self.adapters["mock"])

    def run(self, prompt_template: str, variables: dict, response_schema: dict = None) -> dict:
        """
        Loads prompt template, injects variables, redacts PII, calls LLM,
        validates JSON response, and logs usage and tokens.
        """
        template_path = PROMPTS_DIR / f"{prompt_template}.md"
        if not template_path.exists():
            raise LLMGatewayError(f"Prompt template {prompt_template}.md not found.")

        with open(template_path, "r", encoding="utf-8") as f:
            template_str = f.read()

        # Render template variables safely without colliding with JSON braces {}
        rendered = template_str
        for key, val in variables.items():
            rendered = rendered.replace(f"{{{key}}}", str(val))

        # Mandatory PII redaction before any prompt leaves your process
        scrubbed_prompt = redact_pii(rendered)

        adapter = self._get_adapter()
        try:
            raw_response, model_used, tokens_in, tokens_out = adapter.call(scrubbed_prompt, self.model_name)
        except Exception as err:
            logger.error(f"LLM call failed for template {prompt_template}: {err}")
            raise LLMGatewayError(str(err))

        # Parse and validate JSON schema
        try:
            # Clean possible markdown code block wrappers (e.g. ```json ... ```)
            cleaned_text = raw_response.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()

            parsed = json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON output for {prompt_template}: {raw_response} - {e}")
            raise LLMGatewayError(f"LLM returned invalid JSON: {raw_response}")

        if response_schema:
            for required_key in response_schema.get("required", []):
                if required_key not in parsed:
                    raise LLMGatewayError(f"LLM JSON missing required key '{required_key}' for {prompt_template}")

        parsed["_model"] = model_used
        self._log_usage(prompt_template, model_used, tokens_in, tokens_out)
        return parsed

    def _log_usage(self, template: str, model: str, tokens_in: int, tokens_out: int):
        logger.info(f"LLM Gateway Call -> Template: {template} | Model: {model} | In: {tokens_in} | Out: {tokens_out}")


llm_gateway = LLMGateway()
