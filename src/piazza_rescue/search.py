from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .utils import iter_jsonl


def build_search_db(archive_dir: Path) -> Path:
    db_path = archive_dir / "search.db"
    if db_path.exists():
        db_path.unlink()
    connection = sqlite3.connect(db_path)
    try:
        _create_schema(connection)
        _load_posts(connection, archive_dir / "search_docs.jsonl")
        pdf_docs_path = archive_dir / "pdf_docs.jsonl"
        if pdf_docs_path.exists():
            _load_pdf_docs(connection, pdf_docs_path)
        connection.commit()
    finally:
        connection.close()
    return db_path


def search_archive(
    db_path: Path,
    query: str,
    limit: int = 10,
    label: str | None = None,
    folder: str | None = None,
    has_pdf: bool = False,
    source: str = "post",
) -> list[dict[str, Any]]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        if source == "pdf":
            if not query.strip():
                sql = """
                    SELECT
                        post_id,
                        '' AS subject,
                        filename,
                        local_path,
                        0.0 AS score
                    FROM pdf_docs
                    ORDER BY post_id, filename
                    LIMIT ?
                """
                rows = connection.execute(sql, (limit,)).fetchall()
                return [dict(row) for row in rows]
            sql = """
                SELECT
                    pdf_docs.post_id,
                    '' AS subject,
                    pdf_docs.filename,
                    pdf_docs.local_path,
                    bm25(pdf_fts) AS score
                FROM pdf_fts
                JOIN pdf_docs ON pdf_docs.rowid = pdf_fts.rowid
                WHERE pdf_fts MATCH ?
                ORDER BY score
                LIMIT ?
            """
            rows = connection.execute(sql, (query, limit)).fetchall()
            return [dict(row) for row in rows]
        use_fts = bool(query.strip())
        conditions = []
        params: list[Any] = []
        from_clause = "posts"
        if use_fts:
            from_clause = "post_fts JOIN posts ON posts.rowid = post_fts.rowid"
            conditions.append("post_fts MATCH ?")
            params.append(query)
        if label:
            conditions.append("EXISTS (SELECT 1 FROM json_each(posts.labels_json) WHERE value = ?)")
            params.append(label)
        if folder:
            conditions.append("EXISTS (SELECT 1 FROM json_each(posts.folders_json) WHERE value = ?)")
            params.append(folder)
        if has_pdf:
            conditions.append("posts.has_pdf = 1")
        params.append(limit)
        sql = f"""
            SELECT
                posts.post_id,
                posts.post_number,
                posts.subject,
                posts.post_type,
                posts.has_pdf,
                posts.labels_json,
                posts.folders_json,
                {('bm25(post_fts)' if use_fts else '0.0')} AS score
            FROM {from_clause}
            {('WHERE ' + ' AND '.join(conditions)) if conditions else ''}
            ORDER BY {('score' if use_fts else 'posts.post_number + 0')}
            LIMIT ?
        """
        rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE posts (
            post_id TEXT PRIMARY KEY,
            post_number TEXT,
            subject TEXT,
            body_text TEXT,
            post_type TEXT,
            status TEXT,
            resolved INTEGER,
            created_at TEXT,
            updated_at TEXT,
            view_count INTEGER,
            folders_json TEXT,
            labels_json TEXT,
            author_labels_json TEXT,
            has_pdf INTEGER,
            attachment_names_json TEXT,
            permalink_tokens_json TEXT
        );

        CREATE VIRTUAL TABLE post_fts USING fts5(
            post_id UNINDEXED,
            subject,
            body_text,
            student_answer_text,
            instructor_answer_text,
            followup_text,
            tags,
            attachment_names,
            labels,
            search_text,
            tokenize = 'unicode61'
        );

        CREATE INDEX posts_resolved_idx ON posts(resolved);
        CREATE INDEX posts_has_pdf_idx ON posts(has_pdf);

        CREATE TABLE pdf_docs (
            local_path TEXT PRIMARY KEY,
            post_id TEXT,
            filename TEXT,
            sha256 TEXT,
            text_length INTEGER,
            error TEXT
        );

        CREATE VIRTUAL TABLE pdf_fts USING fts5(
            local_path UNINDEXED,
            post_id UNINDEXED,
            filename,
            text,
            tokenize = 'unicode61'
        );
        """
    )


def _load_posts(connection: sqlite3.Connection, search_docs_path: Path) -> None:
    for row in iter_jsonl(search_docs_path):
        connection.execute(
            """
            INSERT INTO posts (
                post_id, post_number, subject, body_text, post_type, status, resolved,
                created_at, updated_at, view_count, folders_json, labels_json,
                author_labels_json, has_pdf, attachment_names_json, permalink_tokens_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("post_id", ""),
                row.get("post_number", ""),
                row.get("subject", ""),
                row.get("body_text", ""),
                row.get("post_type", ""),
                row.get("status", ""),
                1 if row.get("resolved") else 0,
                row.get("created_at", ""),
                row.get("updated_at", ""),
                row.get("view_count"),
                json.dumps(row.get("folders", [])),
                json.dumps(row.get("labels", [])),
                json.dumps(row.get("author_labels", [])),
                1 if row.get("has_pdf") else 0,
                json.dumps(row.get("attachment_names", [])),
                json.dumps(row.get("permalink_tokens", [])),
            ),
        )
        connection.execute(
            """
            INSERT INTO post_fts (
                post_id, subject, body_text, student_answer_text, instructor_answer_text,
                followup_text, tags, attachment_names, labels, search_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("post_id", ""),
                row.get("subject", ""),
                row.get("body_text", ""),
                row.get("student_answer", {}).get("content_text", ""),
                row.get("instructor_answer", {}).get("content_text", ""),
                row.get("followup_text", ""),
                " ".join(row.get("folders", [])),
                " ".join(row.get("attachment_names", [])),
                " ".join(row.get("labels", [])),
                row.get("search_text", ""),
            ),
        )


def _load_pdf_docs(connection: sqlite3.Connection, pdf_docs_path: Path) -> None:
    for row in iter_jsonl(pdf_docs_path):
        connection.execute(
            """
            INSERT INTO pdf_docs (local_path, post_id, filename, sha256, text_length, error)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("local_path", ""),
                row.get("post_id", ""),
                row.get("filename", ""),
                row.get("sha256", ""),
                row.get("text_length", 0),
                row.get("error", ""),
            ),
        )
        connection.execute(
            """
            INSERT INTO pdf_fts (local_path, post_id, filename, text)
            VALUES (?, ?, ?, ?)
            """,
            (
                row.get("local_path", ""),
                row.get("post_id", ""),
                row.get("filename", ""),
                row.get("text", ""),
            ),
        )
