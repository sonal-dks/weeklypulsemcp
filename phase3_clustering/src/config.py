from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Phase3Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    themes_path: str = Field(default="phase2_theming/outputs/themes_2026-03-24.json", alias="THEMES_PATH")
    review_theme_map_path: str = Field(
        default="phase2_theming/outputs/review_theme_map_2026-03-24.json",
        alias="REVIEW_THEME_MAP_PATH",
    )
    output_dir: str = Field(default="phase3_clustering/outputs", alias="OUTPUT_DIR")
    max_ambiguous_reclassify: int = Field(default=250, alias="MAX_AMBIGUOUS_RECLASSIFY")
    dominance_threshold: float = Field(default=0.55, alias="DOMINANCE_THRESHOLD")

    def validate_rules(self) -> list[str]:
        errors: list[str] = []
        if self.max_ambiguous_reclassify < 0:
            errors.append("MAX_AMBIGUOUS_RECLASSIFY must be >= 0")
        if self.dominance_threshold <= 0 or self.dominance_threshold >= 1:
            errors.append("DOMINANCE_THRESHOLD must be between 0 and 1")
        return errors
