from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from piazza_api.exceptions import RequestError
from piazza_api.piazza import Piazza
from piazza_api.rpc import PiazzaRPC

from .normalize import attach_files_to_search_doc, normalize_post
from .pdf import discover_attachment_candidates, download_pdfs, extract_pdf_texts
from .search import build_search_db
from .utils import append_jsonl, ensure_directory, iso_utc, stamp_for_path, utc_now, write_json


@dataclass
class ArchiveConfig:
    network_id: str
    output_root: Path
    preflight_post: str | None = None
    sleep_seconds: float = 1.0
    limit: int | None = None
    download_pdfs: bool = True
    extract_pdf_text: bool = True
    build_search_db: bool = True


def run_archive(config: ArchiveConfig, piazza: Piazza, rpc: PiazzaRPC) -> Path:
    started_at = utc_now()
    archive_dir = ensure_directory(config.output_root / f"{config.network_id}-{stamp_for_path(started_at)}")
    posts_path = archive_dir / "posts.jsonl"
    search_docs_path = archive_dir / "search_docs.jsonl"
    failures_path = archive_dir / "failures.jsonl"
    attachments_manifest_path = archive_dir / "attachments_manifest.jsonl"
    pdf_docs_path = archive_dir / "pdf_docs.jsonl"
    posts_path.touch()
    search_docs_path.touch()
    failures_path.touch()

    status = piazza.get_user_status()
    profile = piazza.get_user_profile()
    class_info = _extract_class_info(status, config.network_id)
    write_json(archive_dir / "class.json", {"network": class_info, "profile_id": profile.get("user_id"), "exported_at": iso_utc()})

    network = piazza.network(config.network_id)

    preflight_post = None
    if config.preflight_post:
        print(f"Preflight: fetching post {config.preflight_post}")
        preflight_post = network.get_post(config.preflight_post)
        write_json(archive_dir / "preflight_post.json", preflight_post)

    try:
        stats = network.get_statistics()
        write_json(archive_dir / "stats.json", stats)
    except Exception as exc:
        append_jsonl(
            failures_path,
            {"kind": "stats", "network_id": config.network_id, "error": str(exc), "at": iso_utc()},
        )

    print("Fetching feed snapshot")
    feed = network.get_feed(limit=999999, offset=0)
    write_json(archive_dir / "feed.json", feed)
    feed_ids = [str(item["id"]) for item in feed.get("feed", []) if isinstance(item, dict) and item.get("id") is not None]
    if config.limit is not None:
        feed_ids = feed_ids[: config.limit]

    fetched = 0
    failures = 0
    attachment_records: list[dict[str, Any]] = []
    url_cache: dict[str, dict[str, Any]] = {}
    hash_cache: dict[str, str] = {}
    preflight_key = str(config.preflight_post) if config.preflight_post is not None else None

    for index, cid in enumerate(feed_ids, start=1):
        try:
            if preflight_post is not None and preflight_key == cid:
                post = preflight_post
            else:
                post = network.get_post(cid)
            append_jsonl(posts_path, post)
            search_doc = normalize_post(post, config.network_id)
            candidates = discover_attachment_candidates(post)
            post_id = search_doc.get("post_number") or search_doc.get("post_id") or cid
            if config.download_pdfs:
                post_attachments = download_pdfs(
                    session=rpc.session,
                    archive_dir=archive_dir,
                    post_id=str(post_id),
                    candidates=candidates,
                    attachments_manifest_path=attachments_manifest_path,
                    url_cache=url_cache,
                    hash_cache=hash_cache,
                )
            else:
                post_attachments = []
                for candidate in candidates:
                    record = candidate.to_manifest(str(post_id))
                    record["download_status"] = "metadata_only"
                    record["is_pdf_downloaded"] = False
                    append_jsonl(attachments_manifest_path, record)
                    post_attachments.append(record)
            attachment_records.extend(post_attachments)
            search_doc = attach_files_to_search_doc(search_doc, post_attachments)
            append_jsonl(search_docs_path, search_doc)
            fetched += 1
            print(f"Fetched {index}/{len(feed_ids)} posts", flush=True)
        except RequestError as exc:
            failures += 1
            append_jsonl(
                failures_path,
                {"kind": "post", "post_id": cid, "error": str(exc), "at": iso_utc()},
            )
        except Exception as exc:
            failures += 1
            append_jsonl(
                failures_path,
                {"kind": "post", "post_id": cid, "error": str(exc), "at": iso_utc()},
            )
        if config.sleep_seconds > 0 and index < len(feed_ids):
            import time

            time.sleep(config.sleep_seconds)

    pdf_records: list[dict[str, Any]] = []
    if config.extract_pdf_text and config.download_pdfs:
        print("Extracting PDF text with pdftotext")
        pdf_docs_path.touch()
        pdf_records = extract_pdf_texts(archive_dir, attachment_records, pdf_docs_path)

    search_db_path = None
    if config.build_search_db:
        print("Building SQLite FTS index")
        search_db_path = build_search_db(archive_dir)

    manifest = {
        "network_id": config.network_id,
        "started_at": iso_utc(started_at),
        "finished_at": iso_utc(),
        "archive_dir": os.fspath(archive_dir),
        "auth_mode": "cookies",
        "feed_count": len(feed_ids),
        "posts_fetched": fetched,
        "post_failures": failures,
        "attachments_discovered": len(attachment_records),
        "pdfs_downloaded": sum(1 for item in attachment_records if item.get("is_pdf_downloaded")),
        "pdf_text_docs": len(pdf_records),
        "search_db": os.path.relpath(search_db_path, archive_dir) if search_db_path else None,
        "preflight_post": config.preflight_post,
    }
    write_json(archive_dir / "manifest.json", manifest)
    return archive_dir


def _extract_class_info(status: dict[str, Any], network_id: str) -> dict[str, Any]:
    for network in status.get("networks", []):
        if str(network.get("id")) == str(network_id):
            return network
    return {"id": network_id}
