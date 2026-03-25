import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Phase5Config(BaseSettings):
    _ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    delivery_mode: str = Field(default="draft_only", alias="DELIVERY_MODE")
    email_recipient: str = Field(default="", alias="EMAIL_RECIPIENT")
    approved_recipients: str = Field(default="", alias="APPROVED_RECIPIENTS")
    pulse_path: str = Field(default="phase4_insights/outputs/pulse_2026-03-24.md", alias="PULSE_PATH")
    insights_path: str = Field(default="phase4_insights/outputs/insights_2026-03-24.json", alias="INSIGHTS_PATH")
    fee_data_path: str = Field(default="", alias="FEE_DATA_PATH")
    fee_scenario: str = Field(default="Mutual Fund Exit Load", alias="FEE_SCENARIO")
    output_dir: str = Field(default="phase5_delivery/outputs", alias="OUTPUT_DIR")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    retry_backoff_seconds: float = Field(default=2.0, alias="RETRY_BACKOFF_SECONDS")
    google_doc_id: str = Field(default="", alias="GOOGLE_DOC_ID")
    google_doc_title: str = Field(default="Groww Weekly Product Pulse", alias="GOOGLE_DOC_TITLE")

    # Google Docs: stdio MCP (@a-bonus/google-docs-mcp) or HTTP fallback (mcp_bridge)
    # Default http: works with mcp_bridge or local fallback without Node. Set stdio for @a-bonus/google-docs-mcp.
    gdocs_mcp_transport: str = Field(default="http", alias="GDOCS_MCP_TRANSPORT")
    google_docs_mcp_command: str = Field(default="npx", alias="GOOGLE_DOCS_MCP_COMMAND")
    google_docs_mcp_package: str = Field(default="@a-bonus/google-docs-mcp", alias="GOOGLE_DOCS_MCP_PACKAGE")
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    service_account_path: str = Field(default="", alias="SERVICE_ACCOUNT_PATH")
    google_application_credentials: str = Field(default="", alias="GOOGLE_APPLICATION_CREDENTIALS")
    google_impersonate_user: str = Field(default="", alias="GOOGLE_IMPERSONATE_USER")

    gdocs_mcp_endpoint: str = Field(default="", alias="GDOCS_MCP_ENDPOINT")
    gdocs_mcp_api_key: str = Field(default="", alias="GDOCS_MCP_API_KEY")

    # Gmail: stdio GongRzhe MCP (https://github.com/GongRzhe/Gmail-MCP-Server) or HTTP mcp_bridge
    gmail_mcp_transport: str = Field(default="http", alias="GMAIL_MCP_TRANSPORT")
    google_gmail_mcp_command: str = Field(default="npx", alias="GOOGLE_GMAIL_MCP_COMMAND")
    google_gmail_mcp_package: str = Field(
        default="@gongrzhe/server-gmail-autoauth-mcp",
        alias="GOOGLE_GMAIL_MCP_PACKAGE",
    )
    gmail_credentials_path: str = Field(default="", alias="GMAIL_CREDENTIALS_PATH")
    gmail_mcp_endpoint: str = Field(default="", alias="GMAIL_MCP_ENDPOINT")
    gmail_mcp_api_key: str = Field(default="", alias="GMAIL_MCP_API_KEY")

    def approved_recipient_list(self) -> list[str]:
        return [x.strip().lower() for x in self.approved_recipients.split(",") if x.strip()]

    def google_docs_mcp_args_list(self) -> list[str]:
        return ["-y", self.google_docs_mcp_package.strip()]

    def google_gmail_mcp_args_list(self) -> list[str]:
        return ["-y", self.google_gmail_mcp_package.strip()]

    def google_gmail_mcp_extra_env(self) -> dict[str, str]:
        extra: dict[str, str] = {}
        if self.gmail_credentials_path.strip():
            extra["GMAIL_CREDENTIALS_PATH"] = self.gmail_credentials_path.strip()
        return extra

    def google_docs_mcp_extra_env(self) -> dict[str, str]:
        extra: dict[str, str] = {}
        if self.google_client_id.strip():
            extra["GOOGLE_CLIENT_ID"] = self.google_client_id.strip()
        if self.google_client_secret.strip():
            extra["GOOGLE_CLIENT_SECRET"] = self.google_client_secret.strip()
        if self.google_impersonate_user.strip():
            extra["GOOGLE_IMPERSONATE_USER"] = self.google_impersonate_user.strip()
        sa = self.service_account_path.strip()
        if sa:
            extra["SERVICE_ACCOUNT_PATH"] = sa
        gac = self.google_application_credentials.strip()
        if gac:
            extra["GOOGLE_APPLICATION_CREDENTIALS"] = gac
        return extra

    def validate_rules(self) -> list[str]:
        errors: list[str] = []
        if self.delivery_mode not in {"draft_only", "send"}:
            errors.append("DELIVERY_MODE must be one of: draft_only, send")
        if not self.email_recipient.strip():
            errors.append("EMAIL_RECIPIENT is required")
        if self.max_retries < 1:
            errors.append("MAX_RETRIES must be >= 1")
        if self.retry_backoff_seconds <= 0:
            errors.append("RETRY_BACKOFF_SECONDS must be > 0")
        allowlist = self.approved_recipient_list()
        if allowlist and self.email_recipient.strip().lower() not in allowlist:
            errors.append("EMAIL_RECIPIENT must be in APPROVED_RECIPIENTS")

        transport = (self.gdocs_mcp_transport or "http").strip().lower()
        if transport not in {"stdio", "http"}:
            errors.append("GDOCS_MCP_TRANSPORT must be stdio or http")

        if transport == "http":
            if self.delivery_mode == "send" and not self.gdocs_mcp_endpoint.strip():
                errors.append("GDOCS_MCP_ENDPOINT is required when GDOCS_MCP_TRANSPORT=http and DELIVERY_MODE=send")
        else:
            errors.extend(self._validate_stdio_docs_auth())

        gmail_t = (self.gmail_mcp_transport or "http").strip().lower()
        if gmail_t not in {"stdio", "http"}:
            errors.append("GMAIL_MCP_TRANSPORT must be stdio or http")

        if self.delivery_mode == "send":
            if gmail_t == "http" and not self.gmail_mcp_endpoint.strip():
                errors.append(
                    "GMAIL_MCP_ENDPOINT is required when GMAIL_MCP_TRANSPORT=http and DELIVERY_MODE=send"
                )

        if gmail_t == "stdio":
            errors.extend(self._validate_stdio_gmail_auth())

        return errors

    def _gmail_credentials_file(self) -> Path:
        if self.gmail_credentials_path.strip():
            return Path(self.gmail_credentials_path.strip())
        return Path.home() / ".gmail-mcp" / "credentials.json"

    def _validate_stdio_gmail_auth(self) -> list[str]:
        cred = self._gmail_credentials_file()
        if not cred.is_file():
            return [
                "GMAIL_MCP_TRANSPORT=stdio requires Gmail OAuth tokens. Run "
                "`npx -y @gongrzhe/server-gmail-autoauth-mcp auth` (see "
                "https://github.com/GongRzhe/Gmail-MCP-Server) or set "
                "GMAIL_CREDENTIALS_PATH to credentials.json"
            ]
        return []

    def _validate_stdio_docs_auth(self) -> list[str]:
        has_oauth = bool(self.google_client_id.strip() and self.google_client_secret.strip())
        sa = self.service_account_path.strip()
        has_sa = bool(sa and Path(sa).is_file())
        gac_path = self.google_application_credentials.strip() or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        has_gac = bool(gac_path and Path(gac_path).is_file())
        if not has_oauth and not has_sa and not has_gac:
            return [
                "GDOCS_MCP_TRANSPORT=stdio requires OAuth (GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET), "
                "SERVICE_ACCOUNT_PATH to an existing JSON file, or GOOGLE_APPLICATION_CREDENTIALS in the environment"
            ]
        return []
