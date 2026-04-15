from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .utils import iter_jsonl


def resolve_archive_dir(path: Path) -> Path:
    if path.is_dir():
        return path
    return path.parent


def load_post_from_archive(path: Path, post_ref: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    archive_dir = resolve_archive_dir(path)
    normalized = post_ref.strip()
    normalized_tokens = {normalized}
    if normalized.startswith("@"):
        normalized_tokens.add(normalized[1:])
    else:
        normalized_tokens.add(f"@{normalized}")

    search_docs_path = archive_dir / "search_docs.jsonl"
    for row in iter_jsonl(search_docs_path):
        row_tokens = {
            str(row.get("post_number", "")),
            str(row.get("post_id", "")),
            *[str(token) for token in row.get("permalink_tokens", [])],
        }
        if row_tokens & normalized_tokens:
            return row, _load_attachments_for_post(archive_dir, str(row.get("post_number") or row.get("post_id") or ""))
    raise KeyError(f"Could not find post '{post_ref}' in {search_docs_path}")


def format_post_for_display(post: dict[str, Any], attachments: list[dict[str, Any]]) -> str:
    lines = []
    number = post.get("post_number", "")
    subject = post.get("subject", "")
    network_id = post.get("network_id", "")
    lines.append(f"Post {number}: {subject}")
    if network_id and number:
        lines.append(f"URL: https://piazza.com/class/{network_id}/post/{number}")
    meta = []
    if post.get("post_type"):
        meta.append(f"type={post['post_type']}")
    if post.get("status"):
        meta.append(f"status={post['status']}")
    if post.get("resolved") is not None:
        meta.append(f"resolved={post['resolved']}")
    if post.get("folders"):
        meta.append(f"folders={', '.join(post['folders'])}")
    if post.get("labels"):
        meta.append(f"labels={', '.join(post['labels'])}")
    if post.get("created_at"):
        meta.append(f"created={post['created_at']}")
    if post.get("updated_at"):
        meta.append(f"updated={post['updated_at']}")
    if post.get("view_count") is not None:
        meta.append(f"views={post['view_count']}")
    if meta:
        lines.append("Meta: " + " | ".join(meta))
    if post.get("body_text"):
        lines.extend(["", "Body", post["body_text"]])
    student = post.get("student_answer", {})
    if student.get("content_text"):
        lines.extend(["", "Student Answer", _format_answer_block(student)])
    instructor = post.get("instructor_answer", {})
    if instructor.get("content_text"):
        lines.extend(["", "Instructor Answer", _format_answer_block(instructor)])
    followups = post.get("followups", [])
    if followups:
        lines.extend(["", "Followups"])
        for item in followups:
            lines.extend(_format_followup(item, indent=0))
    if attachments:
        lines.extend(["", "Attachments"])
        for item in attachments:
            parts = [item.get("filename", "")]
            local_path = item.get("local_path")
            if local_path:
                parts.append(f"saved={local_path}")
            status = item.get("download_status")
            if status:
                parts.append(f"status={status}")
            url = item.get("url")
            if url:
                parts.append(f"url={url}")
            lines.append(" - " + " | ".join(part for part in parts if part))
    return "\n".join(lines)


def _load_attachments_for_post(archive_dir: Path, post_ref: str) -> list[dict[str, Any]]:
    manifest_path = archive_dir / "attachments_manifest.jsonl"
    if not manifest_path.exists():
        return []
    rows = []
    for row in iter_jsonl(manifest_path):
        if str(row.get("post_id", "")) == post_ref:
            rows.append(row)
    return rows


def _format_answer_block(block: dict[str, Any]) -> str:
    author = block.get("author_label") or "unknown"
    created = block.get("created_at") or ""
    header = f"author={author}"
    if created:
        header += f" | created={created}"
    content = block.get("content_text", "")
    return f"{header}\n{content}".strip()


def _format_followup(block: dict[str, Any], indent: int) -> list[str]:
    prefix = "  " * indent + "- "
    lines = []
    author = block.get("author_label") or "unknown"
    created = block.get("created_at") or ""
    header_bits = [f"type={block.get('type', '')}", f"author={author}"]
    if created:
        header_bits.append(f"created={created}")
    lines.append(prefix + " | ".join(bit for bit in header_bits if bit))
    if block.get("subject"):
        lines.append("  " * (indent + 1) + f"subject: {block['subject']}")
    if block.get("content_text"):
        lines.append("  " * (indent + 1) + block["content_text"])
    for child in block.get("children", []):
        lines.extend(_format_followup(child, indent + 1))
    return lines
