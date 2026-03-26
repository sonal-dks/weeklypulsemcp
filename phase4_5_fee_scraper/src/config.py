from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# Fixed list of 10 Quant funds to scrape — matches Architecture.md
FUND_SOURCES: list[dict[str, str]] = [
    {
        "name": "Quant Small Cap Fund",
        "url": "https://groww.in/mutual-funds/quant-small-cap-fund-direct-plan-growth",
    },
    {
        "name": "Quant Infrastructure Fund",
        "url": "https://groww.in/mutual-funds/quant-infrastructure-fund-direct-growth",
    },
    {
        "name": "Quant Flexi Cap Fund",
        "url": "https://groww.in/mutual-funds/quant-flexi-cap-fund-direct-growth",
    },
    {
        "name": "Quant ELSS Tax Saver Fund",
        "url": "https://groww.in/mutual-funds/quant-elss-tax-saver-fund-direct-growth",
    },
    {
        "name": "Quant Large Cap Fund",
        "url": "https://groww.in/mutual-funds/quant-large-cap-fund-direct-growth",
    },
    {
        "name": "Quant ESG Integration Strategy Fund",
        "url": "https://groww.in/mutual-funds/quant-esg-integration-strategy-fund-direct-growth",
    },
    {
        "name": "Quant Mid Cap Fund",
        "url": "https://groww.in/mutual-funds/quant-mid-cap-fund-direct-growth",
    },
    {
        "name": "Quant Multi Cap Fund",
        "url": "https://groww.in/mutual-funds/quant-multi-cap-fund-direct-growth",
    },
    {
        "name": "Quant Aggressive Hybrid Fund",
        "url": "https://groww.in/mutual-funds/quant-aggressive-hybrid-fund-direct-growth",
    },
    {
        "name": "Quant Focused Fund",
        "url": "https://groww.in/mutual-funds/quant-focused-fund-direct-growth",
    },
]


class Phase45Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    output_dir: str = Field(default="phase4_5_fee_scraper/outputs", alias="OUTPUT_DIR")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    retry_backoff_seconds: float = Field(default=2.0, alias="RETRY_BACKOFF_SECONDS")
    request_timeout_seconds: int = Field(default=30, alias="REQUEST_TIMEOUT_SECONDS")
    use_playwright_fallback: bool = Field(default=True, alias="USE_PLAYWRIGHT_FALLBACK")
    playwright_timeout_ms: int = Field(default=30000, alias="PLAYWRIGHT_TIMEOUT_MS")
