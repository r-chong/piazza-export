from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from piazza_rescue.normalize import attach_files_to_search_doc, normalize_post
from piazza_rescue.pdf import discover_attachment_candidates
from piazza_rescue.search import build_search_db, search_archive
from piazza_rescue.utils import append_jsonl
from piazza_rescue.view import format_post_for_display, load_post_from_archive


SAMPLE_POST = {
    "id": "abc123",
    "nr": 296,
    "type": "question",
    "status": "active",
    "folders": ["hw9"],
    "unique_views": 85,
    "history": [
        {
            "subject": "stereographic projection Section 7.3",
            "content": "<p>Did we cover stereographic projection in class?</p>",
            "created": "2026-03-25T10:00:00Z",
            "name": "Anonymous Mouse",
        }
    ],
    "i_answer": {
        "id": "i1",
        "name": "Jane Gao",
        "history": [
            {
                "content": "<p>Yes it is covered in class to relate the Platonic solids to the Platonic embeddings.</p>",
                "created": "2026-04-01T12:00:00Z",
            }
        ],
    },
    "children": [
        {
            "id": "f1",
            "type": "followup",
            "name": "Anonymous Mouse",
            "history": [
                {
                    "subject": "Would we ever need to actually use this theorem?",
                    "content": "<p>So far, the only thing I have seen stereographic projection be used for is any face can be drawn as an outer face.</p>",
                    "created": "2026-04-02T12:00:00Z",
                }
            ],
        }
    ],
    "attachments": [
        {
            "name": "lecture_notes_week9.pdf",
            "url": "https://files.example.com/week9.pdf",
            "type": "application/pdf",
        }
    ],
}


class NormalizeTests(unittest.TestCase):
    def test_normalize_post(self) -> None:
        doc = normalize_post(SAMPLE_POST, "example123456")
        self.assertEqual(doc["post_number"], "296")
        self.assertIn("assignment", doc["labels"])
        self.assertIn("stereographic projection", doc["search_text"])
        self.assertIn("@296_f1", doc["permalink_tokens"])

    def test_discover_attachment_candidates(self) -> None:
        candidates = discover_attachment_candidates(SAMPLE_POST)
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].likely_pdf)

    def test_build_search_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = Path(tmpdir)
            doc = normalize_post(SAMPLE_POST, "example123456")
            doc = attach_files_to_search_doc(
                doc,
                [
                    {
                        "filename": "lecture_notes_week9.pdf",
                        "url": "https://files.example.com/week9.pdf",
                        "is_pdf_downloaded": True,
                    }
                ],
            )
            append_jsonl(archive_dir / "search_docs.jsonl", doc)
            append_jsonl(
                archive_dir / "pdf_docs.jsonl",
                {
                    "local_path": "attachments/296/lecture_notes_week9.pdf",
                    "post_id": "296",
                    "filename": "lecture_notes_week9.pdf",
                    "sha256": "abc",
                    "text_length": 42,
                    "text": "midterm 1 review notes",
                },
            )
            db_path = build_search_db(archive_dir)
            self.assertTrue(db_path.exists())
            with sqlite3.connect(db_path) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
                self.assertIn("posts", tables)
                self.assertIn("post_fts", tables)
            post_results = search_archive(db_path, "stereographic", limit=5)
            pdf_results = search_archive(db_path, "midterm 1", limit=5, source="pdf")
            pdf_listing = search_archive(db_path, "", limit=5, has_pdf=True)
            loaded_doc, attachments = load_post_from_archive(archive_dir, "296")
            rendered = format_post_for_display(loaded_doc, attachments)
            self.assertTrue(post_results)
            self.assertTrue(pdf_results)
            self.assertTrue(pdf_listing)
            self.assertEqual(loaded_doc["post_number"], "296")
            self.assertIn("Post 296", rendered)


if __name__ == "__main__":
    unittest.main()
