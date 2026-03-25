from __future__ import annotations

from google.oauth2 import service_account
from googleapiclient.discovery import build

DOCS_SCOPE = "https://www.googleapis.com/auth/documents"
GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
)


def _delegated_credentials(
    sa_path: str,
    scopes: tuple[str, ...] | list[str],
    subject: str | None,
) -> service_account.Credentials:
    base = service_account.Credentials.from_service_account_file(sa_path, scopes=list(scopes))
    if subject:
        return base.with_subject(subject)
    return base


def docs_service(sa_path: str, delegated_subject: str | None):
    creds = _delegated_credentials(sa_path, (DOCS_SCOPE,), delegated_subject)
    return build("docs", "v1", credentials=creds, cache_discovery=False)


def gmail_service(sa_path: str, delegated_subject: str | None):
    if not delegated_subject:
        raise ValueError("Gmail requires GMAIL_IMPERSONATE_USER with service-account delegation")
    creds = _delegated_credentials(sa_path, GMAIL_SCOPES, delegated_subject)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)
