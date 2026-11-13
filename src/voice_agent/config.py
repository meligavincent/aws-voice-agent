import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    region: str = "eu-central-1"
    table: str = "voice-agent-local"
    queue_url: str = ""
    environment: str = "local"
    ai_mode: str = "stub"
    model_id: str = ""
    knowledge_base_id: str = ""
    guardrail_id: str = ""
    guardrail_version: str = ""
    max_tokens: int = 250
    locale: str = "fr_FR"

    @classmethod
    def from_env(cls):
        result = cls(
            region=os.getenv("AWS_REGION", "eu-central-1"),
            table=os.getenv("TABLE_NAME", "voice-agent-local"),
            queue_url=os.getenv("QUEUE_URL", ""),
            environment=os.getenv("APP_ENV", "aws"),
            ai_mode=os.getenv("AI_MODE", "bedrock"),
            model_id=os.getenv("MODEL_ID", ""),
            knowledge_base_id=os.getenv("KNOWLEDGE_BASE_ID", ""),
            guardrail_id=os.getenv("GUARDRAIL_ID", ""),
            guardrail_version=os.getenv("GUARDRAIL_VERSION", ""),
            locale=os.getenv("LOCALE", "fr_FR"),
        )
        if result.ai_mode == "stub" and result.environment != "local":
            raise ValueError("Stub inference is only allowed with APP_ENV=local")
        return result
