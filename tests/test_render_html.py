from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from piazza_rescue.normalize import attach_files_to_search_doc, normalize_post
from piazza_rescue.render_html import discover_archives, render_html_all, render_html_browser
from piazza_rescue.utils import append_jsonl, write_json


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
}


class RenderHtmlTests(unittest.TestCase):
    def test_render_html_browser_outputs_index_and_post_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = Path(tmpdir)
            doc = normalize_post(SAMPLE_POST, "example123456")
            doc["student_answer"] = {
                "id": "s1",
                "subject": "",
                "content_text": "Student wiki answer text",
                "author_label": "Anonymous Mouse",
                "created_at": "2026-04-01T09:00:00Z",
                "updated_at": "",
            }
            doc = attach_files_to_search_doc(
                doc,
                [
                    {
                        "filename": "lecture_notes_week9.pdf",
                        "url": "https://files.example.com/week9.pdf",
                        "local_path": "attachments/296/lecture_notes_week9.pdf",
                        "is_pdf_downloaded": True,
                    }
                ],
            )
            append_jsonl(archive_dir / "search_docs.jsonl", doc)
            write_json(
                archive_dir / "class.json",
                {"network": {"my_name": "Example Course", "id": "example123456"}},
            )
            attachment_dir = archive_dir / "attachments" / "296"
            attachment_dir.mkdir(parents=True)
            (attachment_dir / "lecture_notes_week9.pdf").write_bytes(b"%PDF-1.4\n")
            append_jsonl(
                archive_dir / "attachments_manifest.jsonl",
                {
                    "post_id": "296",
                    "filename": "lecture_notes_week9.pdf",
                    "local_path": "attachments/296/lecture_notes_week9.pdf",
                    "download_status": "downloaded",
                },
            )

            browser_dir = render_html_browser(archive_dir)
            index_html = (browser_dir / "index.html").read_text(encoding="utf-8")
            post_html = (browser_dir / "posts" / "296.html").read_text(encoding="utf-8")

            self.assertIn("Local read-only Piazza archive browser", index_html)
            self.assertIn("stereographic projection Section 7.3", index_html)
            self.assertIn('class="sitemap-row"', index_html)
            self.assertIn('href="posts/296.html"', index_html)
            self.assertIn("Did we cover stereographic projection in class?", index_html)
            self.assertNotIn("Did we cover stereographic projection in class?…", index_html)
            self.assertIn("Students&#x27; Answer", post_html)
            self.assertIn("Instructors&#x27; Answer", post_html)
            self.assertIn("Followup Discussion", post_html)
            self.assertIn("lecture_notes_week9.pdf", post_html)
            self.assertIn("../../attachments/296/lecture_notes_week9.pdf", post_html)

    def test_render_html_omits_non_local_attachment_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = Path(tmpdir)
            doc = normalize_post(SAMPLE_POST, "example123456")
            doc = attach_files_to_search_doc(
                doc,
                [
                    {
                        "filename": "remote_only.pdf",
                        "url": "https://files.example.com/remote_only.pdf",
                        "is_pdf_downloaded": False,
                    }
                ],
            )
            append_jsonl(archive_dir / "search_docs.jsonl", doc)
            write_json(
                archive_dir / "class.json",
                {"network": {"my_name": "Example Course", "id": "example123456"}},
            )
            append_jsonl(
                archive_dir / "attachments_manifest.jsonl",
                {
                    "post_id": "296",
                    "filename": "remote_only.pdf",
                    "url": "https://files.example.com/remote_only.pdf",
                    "download_status": "skipped_non_pdf",
                },
            )

            browser_dir = render_html_browser(archive_dir)
            post_html = (browser_dir / "posts" / "296.html").read_text(encoding="utf-8")

            self.assertNotIn("Attachments</h2>", post_html)
            self.assertNotIn("remote_only.pdf", post_html)

    def test_render_html_all_creates_master_sitemap(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_root = Path(tmpdir) / "archive"
            archive_root.mkdir()
            archive_a = archive_root / "course-a-20260415T000000Z"
            archive_b = archive_root / "course-b-20260416T000000Z"
            archive_a.mkdir()
            archive_b.mkdir()

            doc_a = normalize_post(SAMPLE_POST, "example123456")
            doc_b = normalize_post(
                {
                    **SAMPLE_POST,
                    "id": "def456",
                    "nr": 297,
                    "history": [
                        {
                            "subject": "final review question",
                            "content": "<p>Can someone clarify the final review sheet?</p>",
                            "created": "2026-04-03T10:00:00Z",
                            "name": "Anonymous Molecule",
                        }
                    ],
                },
                "example123456",
            )

            append_jsonl(archive_a / "search_docs.jsonl", doc_a)
            append_jsonl(archive_b / "search_docs.jsonl", doc_b)
            write_json(archive_a / "class.json", {"network": {"my_name": "Course A", "id": "example123456"}})
            write_json(archive_b / "class.json", {"network": {"my_name": "Course B", "id": "example123456"}})

            self.assertEqual(discover_archives(archive_root), [archive_a, archive_b])

            sitemap_path = render_html_all(archive_root)
            sitemap_html = sitemap_path.read_text(encoding="utf-8")

            self.assertTrue((archive_a / "browser" / "index.html").exists())
            self.assertTrue((archive_b / "browser" / "index.html").exists())
            self.assertIn("Piazza Archive Sitemap", sitemap_html)
            self.assertIn("Course A", sitemap_html)
            self.assertIn("Course B", sitemap_html)
            self.assertIn('href="course-a-20260415T000000Z/browser/posts/296.html"', sitemap_html)
            self.assertIn('href="course-b-20260416T000000Z/browser/posts/297.html"', sitemap_html)
            self.assertIn("Can someone clarify the final review sheet?", sitemap_html)


if __name__ == "__main__":
    unittest.main()
