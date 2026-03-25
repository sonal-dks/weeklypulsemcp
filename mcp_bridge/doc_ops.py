from __future__ import annotations

from typing import Any

from googleapiclient.discovery import Resource


def _document_end_index(doc: dict[str, Any]) -> int:
    content = doc.get("body", {}).get("content", [])
    if not content:
        return 1
    return int(content[-1]["endIndex"])


def create_document(docs: Resource, title: str) -> str:
    created = docs.documents().create(body={"title": title}).execute()
    return str(created["documentId"])


def append_weekly_section(
    docs: Resource,
    *,
    doc_id: str,
    section_title: str,
    content_markdown: str,
    insert_page_break: bool,
) -> None:
    doc = docs.documents().get(documentId=doc_id).execute()
    idx = _document_end_index(doc) - 1
    if idx < 1:
        idx = 1

    if insert_page_break:
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertPageBreak": {"location": {"index": idx}}}]},
        ).execute()
        doc = docs.documents().get(documentId=doc_id).execute()
        idx = _document_end_index(doc) - 1
        if idx < 1:
            idx = 1

    block = f"\n{section_title}\n\n{content_markdown}\n"
    docs.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {"location": {"index": idx}, "text": block}}]},
    ).execute()


def doc_url(doc_id: str) -> str:
    return f"https://docs.google.com/document/d/{doc_id}/edit"
