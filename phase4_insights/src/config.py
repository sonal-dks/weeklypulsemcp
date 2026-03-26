from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Phase4Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    themes_path: str = Field(default="", alias="THEMES_PATH")
    review_theme_map_path: str = Field(
        default="phase3_clustering/outputs/review_theme_map.json",
        alias="REVIEW_THEME_MAP_PATH",
    )
    processed_reviews_path: str = Field(
        default="phase1_pipeline/outputs/processed_reviews.json",
        alias="PROCESSED_REVIEWS_PATH",
    )
    cluster_distribution_path: str = Field(
        default="phase3_clustering/outputs/cluster_distribution.json",
        alias="CLUSTER_DISTRIBUTION_PATH",
    )
    output_dir: str = Field(default="phase4_insights/outputs", alias="OUTPUT_DIR")
    top_themes_count: int = Field(default=3, alias="TOP_THEMES_COUNT")

    def validate_rules(self) -> list[str]:
        errors: list[str] = []
        if self.top_themes_count != 3:
            errors.append("TOP_THEMES_COUNT must be 3")
        return errors
