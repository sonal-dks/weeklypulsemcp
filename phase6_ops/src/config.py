from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Phase6Config(BaseSettings):
    _ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # If empty, Phase 6 auto-detects latest week tag from artifacts.
    week_tag: str = Field(default="", alias="WEEK_TAG")

    phase1_config_check_path: str = Field(default="phase1_pipeline/outputs/config_check.json", alias="PHASE1_CONFIG_CHECK_PATH")
    phase2_themes_path: str = Field(default="phase2_theming/outputs/themes_{week}.json", alias="PHASE2_THEMES_PATH")
    phase4_insights_path: str = Field(default="phase4_insights/outputs/insights_{week}.json", alias="PHASE4_INSIGHTS_PATH")
    phase4_pulse_path: str = Field(default="phase4_insights/outputs/pulse_{week}.md", alias="PHASE4_PULSE_PATH")
    phase5_doc_report_path: str = Field(default="phase5_delivery/outputs/doc_append_report_{week}.json", alias="PHASE5_DOC_REPORT_PATH")
    phase5_combined_payload_path: str = Field(default="phase5_delivery/outputs/combined_payload_{week}.json", alias="PHASE5_COMBINED_PAYLOAD_PATH")

    # Use a phase-specific env var name to avoid collisions with other phases.
    output_dir: str = Field(default="phase6_ops/outputs", alias="PHASE6_OUTPUT_DIR")

    def out_path(self, week: str) -> Path:
        return Path(self.output_dir) / f"run_summary_{week}.json"

