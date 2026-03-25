from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BridgeConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    mcp_bridge_api_key: str = Field(default="", alias="MCP_BRIDGE_API_KEY")
    google_application_credentials: str = Field(default="", alias="GOOGLE_APPLICATION_CREDENTIALS")
    docs_impersonate_user: str = Field(default="", alias="DOCS_IMPERSONATE_USER")
    gmail_impersonate_user: str = Field(default="", alias="GMAIL_IMPERSONATE_USER")
    gmail_use_impersonation: bool = Field(default=True, alias="GMAIL_USE_IMPERSONATION")
