from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .utils import first_nonempty, html_to_text, listify


ASSIGNMENT_RE = re.compile(r"\b(hw\d+|homework|assignment|pset|problem set)\b", re.IGNORECASE)
MIDTERM_1_RE = re.compile(r"\b(midterm[\s_-]*1|mt[\s_-]*1|term test[\s_-]*1)\b", re.IGNORECASE)
MIDTERM_2_RE = re.compile(r"\b(midterm[\s_-]*2|mt[\s_-]*2|term test[\s_-]*2)\b", re.IGNORECASE)
FINAL_RE = re.compile(r"\b(final exam|final)\b", re.IGNORECASE)
LECTURE_NOTES_RE = re.compile(r"\b(lecture notes|lecture|slides?)\b", re.IGNORECASE)
TUTORIAL_RE = re.compile(r"\b(tutorial|worksheet)\b", re.IGNORECASE)
LOGISTICS_RE = re.compile(r"\b(deadline|office hours|schedule|syllabus|exam room|location|when is|where is|policy)\b", re.IGNORECASE)


@dataclass
class ThreadBlock:
    block_id: str
    subject: str
    content_text: str
    author_label: str
    created_at: str
    updated_at: str
    block_type: str
    children: list["ThreadBlock"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.block_id,
            "subject": self.subject,
            "content_text": self.content_text,
            "author_label": self.author_label,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "type": self.block_type,
            "children": [child.as_dict() for child in self.children],
        }


def normalize_post(post: dict[str, Any], network_id: str) -> dict[str, Any]:
    subject = _extract_subject(post)
    body_text = _extract_content_text(post)
    folders = [str(item) for item in listify(post.get("folders")) if item]
    tags = folders[:]
    student_answer = _extract_answer(post.get("s_answer"))
    instructor_answer = _extract_answer(post.get("i_answer"))
    followups = [_extract_block(child, "followup") for child in listify(post.get("children")) if isinstance(child, dict)]
    authors = sorted({label for label in _collect_author_labels(post, followups, student_answer, instructor_answer) if label})
    permalink_tokens = sorted(set(_collect_permalink_tokens(post, followups)))

    thread_text_parts = []
    for item in followups:
        thread_text_parts.extend(_flatten_block_text(item))

    attachment_names = []
    attachment_urls = []
    labels = _derive_labels(
        "\n".join(
            [
                subject,
                body_text,
                student_answer["content_text"],
                instructor_answer["content_text"],
                " ".join(folders),
                " ".join(thread_text_parts),
            ]
        )
    )

    resolved = _is_resolved(post)

    search_text = "\n\n".join(
        part
        for part in [
            subject,
            body_text,
            student_answer["content_text"],
            instructor_answer["content_text"],
            "\n".join(thread_text_parts),
            " ".join(folders),
        ]
        if part
    )

    return {
        "network_id": network_id,
        "post_id": str(first_nonempty(post.get("id"), post.get("cid"), post.get("nr"), "")),
        "post_number": str(first_nonempty(post.get("nr"), post.get("id"), "")),
        "subject": subject,
        "body_text": body_text,
        "post_type": str(first_nonempty(post.get("type"), "")),
        "folders": folders,
        "tags": tags,
        "status": str(first_nonempty(post.get("status"), "")),
        "resolved": resolved,
        "created_at": str(first_nonempty(post.get("created"), _latest_history(post).get("created"), "")),
        "updated_at": str(first_nonempty(post.get("updated"), _latest_history(post).get("updated"), "")),
        "view_count": _extract_view_count(post),
        "author_labels": authors,
        "permalink_tokens": permalink_tokens,
        "student_answer": student_answer,
        "instructor_answer": instructor_answer,
        "followups": [item.as_dict() for item in followups],
        "followup_text": "\n".join(thread_text_parts),
        "attachment_names": attachment_names,
        "attachment_urls": attachment_urls,
        "has_pdf": False,
        "labels": labels,
        "search_text": search_text,
    }


def attach_files_to_search_doc(search_doc: dict[str, Any], attachments: list[dict[str, Any]]) -> dict[str, Any]:
    attachment_names = sorted({item.get("filename", "") for item in attachments if item.get("filename")})
    attachment_urls = sorted({item.get("url", "") for item in attachments if item.get("url")})
    labels = set(search_doc.get("labels", []))
    if any("lecture" in name.lower() or "notes" in name.lower() for name in attachment_names):
        labels.add("lecture_notes")
    updated = dict(search_doc)
    updated["attachment_names"] = attachment_names
    updated["attachment_urls"] = attachment_urls
    updated["has_pdf"] = any(item.get("is_pdf_downloaded") for item in attachments)
    updated["labels"] = sorted(labels)
    updated["search_text"] = "\n\n".join(
        part
        for part in [
            search_doc.get("search_text", ""),
            " ".join(attachment_names),
        ]
        if part
    )
    return updated


def _latest_history(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    history = node.get("history")
    if isinstance(history, list) and history:
        last = history[-1]
        if isinstance(last, dict):
            return last
    return {}


def _extract_subject(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    history = _latest_history(node)
    return html_to_text(first_nonempty(history.get("subject"), node.get("subject"), ""))


def _extract_content_text(node: Any) -> str:
    if not isinstance(node, dict):
        return html_to_text(node)
    history = _latest_history(node)
    return html_to_text(first_nonempty(history.get("content"), node.get("content"), history.get("subject"), node.get("subject"), ""))


def _extract_author_label(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    history = _latest_history(node)
    for key in ["name", "display_name", "anon_screen_name", "anon_name", "uid"]:
        value = first_nonempty(node.get(key), history.get(key))
        if value:
            return str(value)
    return ""


def _extract_answer(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {
            "id": "",
            "subject": "",
            "content_text": "",
            "author_label": "",
            "created_at": "",
            "updated_at": "",
        }
    history = _latest_history(node)
    return {
        "id": str(first_nonempty(node.get("id"), "")),
        "subject": html_to_text(first_nonempty(history.get("subject"), node.get("subject"), "")),
        "content_text": _extract_content_text(node),
        "author_label": _extract_author_label(node),
        "created_at": str(first_nonempty(node.get("created"), history.get("created"), "")),
        "updated_at": str(first_nonempty(node.get("updated"), history.get("updated"), "")),
    }


def _extract_block(node: dict[str, Any], block_type: str) -> ThreadBlock:
    history = _latest_history(node)
    child_items = listify(node.get("children")) + listify(node.get("feedback"))
    children = [_extract_block(child, str(first_nonempty(child.get("type"), "reply"))) for child in child_items if isinstance(child, dict)]
    return ThreadBlock(
        block_id=str(first_nonempty(node.get("id"), node.get("cid"), "")),
        subject=html_to_text(first_nonempty(history.get("subject"), node.get("subject"), "")),
        content_text=_extract_content_text(node),
        author_label=_extract_author_label(node),
        created_at=str(first_nonempty(node.get("created"), history.get("created"), "")),
        updated_at=str(first_nonempty(node.get("updated"), history.get("updated"), "")),
        block_type=block_type,
        children=children,
    )


def _flatten_block_text(block: ThreadBlock) -> list[str]:
    current = [block.subject, block.content_text]
    for child in block.children:
        current.extend(_flatten_block_text(child))
    return [item for item in current if item]


def _collect_author_labels(
    post: dict[str, Any],
    followups: list[ThreadBlock],
    student_answer: dict[str, Any],
    instructor_answer: dict[str, Any],
) -> list[str]:
    labels = [_extract_author_label(post), student_answer.get("author_label", ""), instructor_answer.get("author_label", "")]
    for item in followups:
        labels.extend(_block_authors(item))
    return labels


def _block_authors(block: ThreadBlock) -> list[str]:
    labels = [block.author_label]
    for child in block.children:
        labels.extend(_block_authors(child))
    return labels


def _collect_permalink_tokens(post: dict[str, Any], followups: list[ThreadBlock]) -> list[str]:
    tokens = []
    post_number = first_nonempty(post.get("nr"), post.get("id"))
    if post_number:
        tokens.append(f"@{post_number}")
    for index, block in enumerate(followups, start=1):
        if post_number:
            tokens.append(f"@{post_number}_f{index}")
        if block.block_id:
            tokens.append(block.block_id)
    return tokens


def _derive_labels(text: str) -> list[str]:
    labels = set()
    if ASSIGNMENT_RE.search(text):
        labels.add("assignment")
    if MIDTERM_1_RE.search(text):
        labels.update({"midterm_1", "exam"})
    if MIDTERM_2_RE.search(text):
        labels.update({"midterm_2", "exam"})
    if FINAL_RE.search(text):
        labels.update({"final", "exam"})
    if LECTURE_NOTES_RE.search(text):
        labels.add("lecture_notes")
    if TUTORIAL_RE.search(text):
        labels.add("tutorial")
    if LOGISTICS_RE.search(text):
        labels.add("logistics")
    return sorted(labels)


def _is_resolved(post: dict[str, Any]) -> bool:
    status = str(first_nonempty(post.get("status"), "")).lower()
    if status in {"resolved", "done"}:
        return True
    if isinstance(post.get("resolved"), bool):
        return post["resolved"]
    return False


def _extract_view_count(post: dict[str, Any]) -> int | None:
    for key in ["unique_views", "num_views", "views", "view_count"]:
        value = post.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None
