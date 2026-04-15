from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from requests import Session

from .utils import append_jsonl, ensure_directory, extract_html_links, extract_urls, normalize_url, slugify


ATTACHMENT_HINTS = ("attach", "asset", "doc", "document", "file", "files", "resource", "upload")
COMMON_FILE_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".txt",
    ".zip",
}


@dataclass
class AttachmentCandidate:
    url: str
    filename: str
    mime_type: str
    source_path: str
    source_text: str
    likely_attachment: bool
    likely_pdf: bool

    def to_manifest(self, post_id: str) -> dict[str, Any]:
        return {
            "post_id": post_id,
            "url": self.url,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "source_path": self.source_path,
            "source_text": self.source_text,
            "likely_attachment": self.likely_attachment,
            "likely_pdf": self.likely_pdf,
        }


def discover_attachment_candidates(post: dict[str, Any]) -> list[AttachmentCandidate]:
    seen: dict[str, AttachmentCandidate] = {}
    _walk_object(post, [], None, seen)
    return list(seen.values())


def download_pdfs(
    session: Session,
    archive_dir: Path,
    post_id: str,
    candidates: list[AttachmentCandidate],
    attachments_manifest_path: Path,
    url_cache: dict[str, dict[str, Any]],
    hash_cache: dict[str, str],
) -> list[dict[str, Any]]:
    post_dir = ensure_directory(archive_dir / "attachments" / slugify(post_id or "post"))
    records: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        record = candidate.to_manifest(post_id)
        record["is_pdf_downloaded"] = False
        if candidate.url in url_cache:
            cached = dict(url_cache[candidate.url])
            cached.update(record)
            cached["download_status"] = "reused_by_url"
            append_jsonl(attachments_manifest_path, cached)
            records.append(cached)
            continue
        if not candidate.likely_pdf:
            record["download_status"] = "skipped_non_pdf"
            append_jsonl(attachments_manifest_path, record)
            records.append(record)
            continue
        try:
            response = session.get(candidate.url, stream=True, timeout=60)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            filename = _resolve_filename(candidate, response.headers.get("Content-Disposition", ""), post_id, index)
            temp_path = post_dir / f".{filename}.part"
            sha256 = hashlib.sha256()
            with temp_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    sha256.update(chunk)
                    handle.write(chunk)
            file_hash = sha256.hexdigest()
            if not _looks_like_pdf(temp_path, content_type, filename):
                temp_path.unlink(missing_ok=True)
                record["download_status"] = "skipped_non_pdf_response"
                record["content_type"] = content_type
                append_jsonl(attachments_manifest_path, record)
                records.append(record)
                continue
            final_path = post_dir / filename
            if file_hash in hash_cache:
                temp_path.unlink(missing_ok=True)
                final_path = archive_dir / hash_cache[file_hash]
                status = "reused_by_hash"
            else:
                final_path = _dedupe_target_path(final_path)
                temp_path.replace(final_path)
                hash_cache[file_hash] = os.path.relpath(final_path, archive_dir)
                status = "downloaded"
            record.update(
                {
                    "download_status": status,
                    "is_pdf_downloaded": True,
                    "content_type": content_type,
                    "sha256": file_hash,
                    "local_path": os.path.relpath(final_path, archive_dir),
                }
            )
            url_cache[candidate.url] = dict(record)
        except Exception as exc:
            record["download_status"] = "failed"
            record["error"] = str(exc)
        append_jsonl(attachments_manifest_path, record)
        records.append(record)
    return records


def extract_pdf_texts(
    archive_dir: Path,
    attachments: list[dict[str, Any]],
    pdf_docs_path: Path,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for attachment in attachments:
        local_path = attachment.get("local_path")
        if not local_path or local_path in seen_paths:
            continue
        seen_paths.add(local_path)
        file_path = archive_dir / local_path
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", "-enc", "UTF-8", str(file_path), "-"],
                capture_output=True,
                text=True,
                check=True,
            )
            text = result.stdout.strip()
            record = {
                "post_id": attachment.get("post_id", ""),
                "filename": attachment.get("filename", ""),
                "local_path": local_path,
                "sha256": attachment.get("sha256", ""),
                "text": text,
                "text_length": len(text),
            }
        except Exception as exc:
            record = {
                "post_id": attachment.get("post_id", ""),
                "filename": attachment.get("filename", ""),
                "local_path": local_path,
                "sha256": attachment.get("sha256", ""),
                "text": "",
                "text_length": 0,
                "error": str(exc),
            }
        append_jsonl(pdf_docs_path, record)
        records.append(record)
    return records


def _walk_object(
    node: Any,
    path: list[str],
    parent: dict[str, Any] | None,
    seen: dict[str, AttachmentCandidate],
) -> None:
    if isinstance(node, dict):
        metadata = _extract_metadata(node)
        for key, value in node.items():
            _walk_object(value, path + [str(key)], node, seen)
        for key, value in node.items():
            if key.lower() in {"url", "href", "src", "download_url", "file_url"} and isinstance(value, str):
                _maybe_add_candidate(value, path + [str(key)], node, metadata, seen)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _walk_object(item, path + [str(index)], parent, seen)
    elif isinstance(node, str):
        source_path = ".".join(path)
        for url, link_text in extract_html_links(node):
            _maybe_add_candidate(url, path, parent, {"source_text": link_text}, seen)
        for url in extract_urls(node):
            _maybe_add_candidate(url, path, parent, {"source_text": node[:120]}, seen)


def _extract_metadata(node: dict[str, Any]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for key in ["filename", "file_name", "name", "title"]:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            metadata["filename"] = value.strip()
            break
    for key in ["mime", "mime_type", "content_type", "type"]:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            metadata["mime_type"] = value.strip()
            break
    return metadata


def _maybe_add_candidate(
    raw_url: str,
    path: list[str],
    parent: dict[str, Any] | None,
    metadata: dict[str, str],
    seen: dict[str, AttachmentCandidate],
) -> None:
    url = normalize_url(raw_url)
    if not url:
        return
    path_text = ".".join(path).lower()
    filename = metadata.get("filename") or _filename_from_url(url)
    mime_type = metadata.get("mime_type", "")
    source_text = metadata.get("source_text", "")
    likely_attachment = bool(
        filename
        or mime_type
        or any(hint in path_text for hint in ATTACHMENT_HINTS)
        or _url_extension(url) in COMMON_FILE_EXTENSIONS
    )
    if not likely_attachment:
        return
    candidate = AttachmentCandidate(
        url=url,
        filename=filename,
        mime_type=mime_type,
        source_path=path_text,
        source_text=source_text,
        likely_attachment=True,
        likely_pdf=_looks_like_pdf_hint(filename, mime_type, url),
    )
    existing = seen.get(candidate.url)
    if existing is None:
        seen[candidate.url] = candidate
        return
    seen[candidate.url] = AttachmentCandidate(
        url=candidate.url,
        filename=_prefer_richer(existing.filename, candidate.filename),
        mime_type=_prefer_richer(existing.mime_type, candidate.mime_type),
        source_path=_prefer_richer(existing.source_path, candidate.source_path),
        source_text=_prefer_richer(existing.source_text, candidate.source_text),
        likely_attachment=existing.likely_attachment or candidate.likely_attachment,
        likely_pdf=existing.likely_pdf or candidate.likely_pdf,
    )


def _filename_from_url(url: str) -> str:
    path = unquote(urlparse(url).path)
    return path.rsplit("/", 1)[-1]


def _url_extension(url: str) -> str:
    path = unquote(urlparse(url).path).lower()
    match = re.search(r"(\.[a-z0-9]{1,8})$", path)
    return match.group(1) if match else ""


def _looks_like_pdf_hint(filename: str, mime_type: str, url: str) -> bool:
    return ".pdf" in filename.lower() or "pdf" in mime_type.lower() or ".pdf" in url.lower()


def _looks_like_pdf(path: Path, content_type: str, filename: str) -> bool:
    if "pdf" in content_type.lower() or filename.lower().endswith(".pdf"):
        return True
    with path.open("rb") as handle:
        return handle.read(5) == b"%PDF-"


def _resolve_filename(candidate: AttachmentCandidate, content_disposition: str, post_id: str, index: int) -> str:
    if "filename=" in content_disposition:
        part = content_disposition.split("filename=", 1)[1].strip().strip("\"'")
        return _ensure_pdf_extension(slugify(part, fallback=f"{post_id}-{index}.pdf"))
    if candidate.filename:
        return _ensure_pdf_extension(slugify(candidate.filename, fallback=f"{post_id}-{index}.pdf"))
    return f"{slugify(post_id or 'post')}-{index}.pdf"


def _ensure_pdf_extension(filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        return filename
    return f"{filename}.pdf"


def _dedupe_target_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = path.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _prefer_richer(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    return right if len(right) > len(left) else left
