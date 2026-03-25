from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Phase1Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_id: str = Field(default="com.nextbillion.groww", alias="APP_ID")
    lookback_weeks: int = Field(default=12, alias="LOOKBACK_WEEKS")
    theme_count: int = Field(default=5, alias="THEME_COUNT")
    max_themes: int = Field(default=5, alias="MAX_THEMES")
    top_reported_themes: int = Field(default=3, alias="TOP_REPORTED_THEMES")
    email_recipient: str = Field(default="owner@example.com", alias="EMAIL_RECIPIENT")

    playstore_lang: str = Field(default="en", alias="PLAYSTORE_LANG")
    playstore_country: str = Field(default="in", alias="PLAYSTORE_COUNTRY")
    batch_size: int = Field(default=200, alias="BATCH_SIZE")
    max_fetch: int = Field(default=4000, alias="MAX_FETCH")

    raw_json_path: str = Field(default="phase1_pipeline/outputs/raw_reviews.json", alias="RAW_JSON_PATH")
    processed_json_path: str = Field(
        default="phase1_pipeline/outputs/processed_reviews.json",
        alias="PROCESSED_JSON_PATH",
    )
    omitted_json_path: str = Field(default="phase1_pipeline/outputs/omitted_reviews.json", alias="OMITTED_JSON_PATH")

    def validate_foundation_rules(self) -> list[str]:
        errors: list[str] = []
        if self.app_id != "com.nextbillion.groww":
            errors.append("APP_ID must be com.nextbillion.groww")
        if self.lookback_weeks != 12:
            errors.append("LOOKBACK_WEEKS must be fixed to 12")
        if self.theme_count != 5:
            errors.append("THEME_COUNT must be fixed to 5")
        if self.max_themes != 5:
            errors.append("MAX_THEMES must be fixed to 5")
        if self.top_reported_themes != 3:
            errors.append("TOP_REPORTED_THEMES must be fixed to 3")
        if self.playstore_lang.lower() != "en":
            errors.append("PLAYSTORE_LANG must be en")
        if self.top_reported_themes > self.theme_count:
            errors.append("TOP_REPORTED_THEMES cannot exceed THEME_COUNT")
        return errors
