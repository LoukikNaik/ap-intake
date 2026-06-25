"""Model factory.

Everything runs through LiteLLM so the model is pure configuration. Default is
gpt-5-mini; set AGENT_MODEL=anthropic/claude-sonnet-4-6 (plus ANTHROPIC_API_KEY) to
switch to Claude with no code change.
"""

from agents.extensions.models.litellm_model import LitellmModel

from app.config import get_settings


def _api_key_for(model: str) -> str | None:
    s = get_settings()
    if model.startswith("anthropic/") or model.startswith("claude"):
        return s.anthropic_api_key
    return s.openai_api_key


def get_model(model_name: str | None = None) -> LitellmModel:
    s = get_settings()
    name = model_name or s.agent_model
    return LitellmModel(model=name, api_key=_api_key_for(name))


def get_escalation_model() -> LitellmModel:
    return get_model(get_settings().escalation_model)
