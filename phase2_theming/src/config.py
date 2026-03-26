from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Phase2Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    input_processed_reviews_path: str = Field(
        default="phase1_pipeline/outputs/processed_reviews.json",
        alias="INPUT_PROCESSED_REVIEWS_PATH",
    )
    output_dir: str = Field(default="phase2_theming/outputs", alias="OUTPUT_DIR")
    theme_count: int = Field(default=5, alias="THEME_COUNT")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    batch_size_reviews: int = Field(default=160, alias="BATCH_SIZE_REVIEWS")

    def validate_rules(self) -> list[str]:
        errors: list[str] = []
        if self.theme_count != 5:
            errors.append("THEME_COUNT must be fixed to 5")
        if self.max_retries < 1:
            errors.append("MAX_RETRIES must be >= 1")
        if self.batch_size_reviews < 20:
            errors.append("BATCH_SIZE_REVIEWS must be >= 20")
        return errors
