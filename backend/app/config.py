"""Application settings.

The agent's MODEL is intentionally configuration, not code. We run everything through
LiteLLM so the same agent loop works with gpt-5-mini (default) or any Claude model by
changing env vars only — no code change. See `app/agents/model.py`.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+psycopg://ap:ap@db:5432/ap_intake"

    # --- Model selection (swappable without code changes) ---
    # LiteLLM model string. Examples:
    #   "gpt-5-mini"                      (OpenAI, default)
    #   "anthropic/claude-sonnet-4-6"     (Claude via LiteLLM)
    agent_model: str = "gpt-5-mini"
    # Optional stronger model used only when a stage is low-confidence (escalation tier).
    escalation_model: str = "gpt-5.5"

    # How the PDF is handed to the model:
    #   "native" — send the PDF directly (model reads the text layer; best for digital invoices)
    #   "images" — render pages to PNGs and send as vision input (most provider-portable fallback)
    pdf_input_mode: str = "native"

    # API keys — LiteLLM reads whichever the chosen model needs.
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # --- Behaviour ---
    # Below this overall confidence a bill is routed to human review regardless of other checks.
    review_confidence_threshold: float = 0.75
    # Cap the agent loop per stage so a misbehaving run can't run up cost.
    max_turns: int = 12

    # --- Misc ---
    cors_origins: str = "http://localhost:5173,http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
