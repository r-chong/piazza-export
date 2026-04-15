from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .utils import ensure_directory, iter_jsonl, slugify
from .view import resolve_archive_dir


STYLESHEET = """
:root {
  color-scheme: light;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: sans-serif;
  line-height: 1.45;
  color: #1f2933;
  background: #f6f8fb;
}

a {
  color: #0b5bd3;
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

.page {
  max-width: 1040px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.site-header {
  margin-bottom: 24px;
}

.site-title {
  margin: 0 0 6px;
  font-size: 28px;
}

.site-subtitle {
  color: #52606d;
  margin: 0;
}

.toolbar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin: 20px 0 12px;
  padding: 16px;
  background: #ffffff;
  border: 1px solid #d9e2ec;
  border-radius: 10px;
}

.toolbar label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: #334e68;
  margin-bottom: 4px;
}

.toolbar input,
.toolbar select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #cbd2d9;
  border-radius: 8px;
  background: #ffffff;
}

.toolbar .checkbox-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 21px;
}

.results-meta,
.archive-meta,
.post-meta,
.section-subtitle,
.followup-meta,
.nav-row {
  color: #52606d;
  font-size: 14px;
}

.results-meta,
.archive-heading,
.nav-row {
  margin: 0 0 14px;
}

.archive-group {
  margin-top: 28px;
}

.archive-group:first-of-type {
  margin-top: 0;
}

.archive-heading h2 {
  margin: 0 0 4px;
  font-size: 22px;
}

.sitemap-list,
.post-shell,
.answer-shell,
.thread-shell {
  background: #ffffff;
  border: 1px solid #d9e2ec;
  border-radius: 10px;
}

.sitemap-list {
  overflow: hidden;
}

.sitemap-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
  padding: 11px 14px;
  background: #ffffff;
  color: #102a43;
  border-top: 1px solid #e4e7eb;
  white-space: nowrap;
}

.sitemap-row:first-child {
  border-top: none;
}

.sitemap-row:hover {
  background: #f0f4f8;
  text-decoration: none;
}

.row-prefix {
  flex: 0 0 auto;
  color: #52606d;
  font-size: 13px;
  font-weight: 700;
}

.row-title {
  flex: 0 1 auto;
  max-width: 30rem;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
  color: #102a43;
}

.row-description {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #52606d;
}

.row-description::before {
  content: "-";
  margin-right: 10px;
  color: #9aa5b1;
}

.post-shell {
  padding: 20px 22px;
}

.post-title-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.post-title-row h1,
.answer-shell h2,
.thread-shell h2 {
  margin: 0;
  font-size: 20px;
}

.body-block,
.section-body {
  margin-top: 16px;
}

.body-block p,
.section-body p,
.followup-body p {
  margin: 0 0 12px;
  white-space: pre-wrap;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.chip {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #243b53;
  font-size: 12px;
  border: 1px solid #d9e2ec;
}

.chip.status {
  background: #fff7d6;
}

.chip.label {
  background: #e6fffa;
}

.answer-shell,
.thread-shell {
  margin-top: 16px;
  padding: 16px 18px;
}

.followup-list {
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
}

.followup {
  border-top: 1px solid #e4e7eb;
  padding: 14px 0 0;
  margin-top: 14px;
}

.followup:first-child {
  border-top: none;
  padding-top: 0;
  margin-top: 0;
}

.nested-followups {
  margin-left: 18px;
  margin-top: 12px;
}

.attachments {
  margin-top: 16px;
}

.attachments ul {
  margin: 10px 0 0;
  padding-left: 18px;
}

.attachments li {
  margin-bottom: 8px;
}

.empty-state {
  margin-top: 16px;
  padding: 18px;
  background: #ffffff;
  border: 1px solid #d9e2ec;
  border-radius: 10px;
  color: #52606d;
}

.hidden {
  display: none !important;
}

@media (max-width: 720px) {
  .sitemap-row {
    gap: 8px;
    padding: 10px 12px;
  }

  .row-title {
    max-width: 45vw;
  }
}
"""


@dataclass
class RenderedPostPage:
    post_ref: str
    post_id: str
    title: str
    description: str
    path: Path
    post_type: str
    folders: list[str]
    labels: list[str]
    has_pdf: bool
    search_blob: str


@dataclass
class RenderedArchive:
    archive_dir: Path
    browser_dir: Path
    title: str
    directory_name: str
    posts: list[RenderedPostPage]


def render_html_browser(path: Path, output_dir: str = "browser") -> Path:
    return build_archive_browser(path, output_dir=output_dir).browser_dir


def build_archive_browser(path: Path, output_dir: str = "browser") -> RenderedArchive:
    archive_dir = resolve_archive_dir(path)
    browser_dir = _resolve_output_dir(archive_dir, output_dir)
    if browser_dir.exists():
        shutil.rmtree(browser_dir)

    assets_dir = ensure_directory(browser_dir / "assets")
    posts_dir = ensure_directory(browser_dir / "posts")
    (assets_dir / "styles.css").write_text(STYLESHEET.strip() + "\n", encoding="utf-8")

    class_info = _load_class_info(archive_dir)
    post_docs = list(iter_jsonl(archive_dir / "search_docs.jsonl"))
    post_docs.sort(key=_post_sort_key, reverse=True)
    attachments_by_post = _load_local_attachments(archive_dir)

    rendered_posts: list[RenderedPostPage] = []
    for post in post_docs:
        page_path = posts_dir / f"{_post_slug(post)}.html"
        attachments = attachments_by_post.get(_post_ref(post), []) or attachments_by_post.get(_clean_text(post.get("post_id")), [])
        page_path.write_text(
            _render_post_page(archive_dir, page_path, post, attachments, class_info),
            encoding="utf-8",
        )
        rendered_posts.append(
            RenderedPostPage(
                post_ref=_post_ref(post),
                post_id=_clean_text(post.get("post_id")),
                title=_clean_text(post.get("subject")) or "(untitled)",
                description=_description_text(post),
                path=page_path,
                post_type=_clean_text(post.get("post_type")),
                folders=list(post.get("folders", [])),
                labels=list(post.get("labels", [])),
                has_pdf=bool(post.get("has_pdf")),
                search_blob=_search_blob(post),
            )
        )

    rendered_archive = RenderedArchive(
        archive_dir=archive_dir,
        browser_dir=browser_dir,
        title=_archive_title(class_info),
        directory_name=archive_dir.name,
        posts=rendered_posts,
    )

    (browser_dir / "index.html").write_text(
        _render_archive_index(rendered_archive),
        encoding="utf-8",
    )
    return rendered_archive


def discover_archives(root: Path) -> list[Path]:
    archive_root = Path(root)
    if archive_root.is_file():
        archive_root = archive_root.parent
    if not archive_root.exists():
        raise FileNotFoundError(f"Archive root does not exist: {archive_root}")
    return [
        child
        for child in sorted(archive_root.iterdir())
        if child.is_dir() and (child / "search_docs.jsonl").exists()
    ]


def render_html_all(root: Path, output_dir: str = "browser", sitemap_name: str = "index.html") -> Path:
    archive_root = Path(root)
    rendered_archives = [build_archive_browser(path, output_dir=output_dir) for path in discover_archives(archive_root)]
    assets_dir = ensure_directory(archive_root / "assets")
    (assets_dir / "styles.css").write_text(STYLESHEET.strip() + "\n", encoding="utf-8")
    sitemap_path = archive_root / sitemap_name
    sitemap_path.write_text(
        _render_master_sitemap(archive_root, rendered_archives),
        encoding="utf-8",
    )
    return sitemap_path


def _resolve_output_dir(archive_dir: Path, output_dir: str) -> Path:
    candidate = Path(output_dir)
    if candidate.is_absolute():
        return candidate
    return archive_dir / candidate


def _load_class_info(archive_dir: Path) -> dict[str, Any]:
    class_path = archive_dir / "class.json"
    if not class_path.exists():
        return {}
    payload = json.loads(class_path.read_text(encoding="utf-8"))
    return payload.get("network", {})


def _load_local_attachments(archive_dir: Path) -> dict[str, list[dict[str, Any]]]:
    manifest_path = archive_dir / "attachments_manifest.jsonl"
    attachments_by_post: dict[str, list[dict[str, Any]]] = {}
    if not manifest_path.exists():
        return attachments_by_post

    for row in iter_jsonl(manifest_path):
        local_path = row.get("local_path")
        if not local_path:
            continue
        target = archive_dir / local_path
        if not target.exists():
            continue
        key = _clean_text(row.get("post_id"))
        attachments_by_post.setdefault(key, []).append(row)

    for rows in attachments_by_post.values():
        rows.sort(key=lambda item: (_best_attachment_name(item, archive_dir / str(item.get("local_path", ""))), str(item.get("local_path", ""))))
    return attachments_by_post


def _render_archive_index(archive: RenderedArchive) -> str:
    folders = sorted({folder for post in archive.posts for folder in post.folders})
    labels = sorted({label for post in archive.posts for label in post.labels})
    rows = "".join(_render_archive_row(archive.browser_dir, post) for post in archive.posts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(archive.title)} | Archive Browser</title>
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body>
  <div class="page">
    <header class="site-header">
      <h1 class="site-title">{escape(archive.title)}</h1>
      <p class="site-subtitle">Local read-only Piazza archive browser</p>
    </header>

    <section class="toolbar" aria-label="Post filters">
      <div>
        <label for="search-input">Search</label>
        <input id="search-input" type="search" placeholder="title, description, folder, label">
      </div>
      <div>
        <label for="folder-filter">Folder</label>
        <select id="folder-filter">
          <option value="">All folders</option>
          {''.join(f'<option value="{escape(folder)}">{escape(folder)}</option>' for folder in folders)}
        </select>
      </div>
      <div>
        <label for="label-filter">Label</label>
        <select id="label-filter">
          <option value="">All labels</option>
          {''.join(f'<option value="{escape(label)}">{escape(label)}</option>' for label in labels)}
        </select>
      </div>
      <div>
        <label for="type-filter">Post Type</label>
        <select id="type-filter">
          <option value="">All types</option>
          <option value="note">note</option>
          <option value="question">question</option>
        </select>
      </div>
      <div class="checkbox-row">
        <input id="pdf-filter" type="checkbox">
        <label for="pdf-filter">Only posts with local PDFs</label>
      </div>
    </section>

    <p class="results-meta"><span id="visible-count">{len(archive.posts)}</span> of {len(archive.posts)} posts shown</p>

    <main class="sitemap-list" id="post-list">
      {rows or '<div class="empty-state">No posts were available in this archive.</div>'}
    </main>
  </div>

  <script>
  (() => {{
    const searchInput = document.getElementById("search-input");
    const folderFilter = document.getElementById("folder-filter");
    const labelFilter = document.getElementById("label-filter");
    const typeFilter = document.getElementById("type-filter");
    const pdfFilter = document.getElementById("pdf-filter");
    const rows = Array.from(document.querySelectorAll(".sitemap-row"));
    const countEl = document.getElementById("visible-count");

    function applyFilters() {{
      const query = searchInput.value.trim().toLowerCase();
      const folder = folderFilter.value;
      const label = labelFilter.value;
      const type = typeFilter.value;
      const pdfOnly = pdfFilter.checked;
      let visible = 0;

      for (const row of rows) {{
        const haystack = row.dataset.search || "";
        const folders = (row.dataset.folders || "").split(" ").filter(Boolean);
        const labels = (row.dataset.labels || "").split(" ").filter(Boolean);
        const postType = row.dataset.type || "";
        const hasPdf = row.dataset.hasPdf === "true";
        const matches =
          (!query || haystack.includes(query)) &&
          (!folder || folders.includes(folder)) &&
          (!label || labels.includes(label)) &&
          (!type || postType === type) &&
          (!pdfOnly || hasPdf);
        row.classList.toggle("hidden", !matches);
        if (matches) {{
          visible += 1;
        }}
      }}

      countEl.textContent = String(visible);
    }}

    searchInput.addEventListener("input", applyFilters);
    folderFilter.addEventListener("change", applyFilters);
    labelFilter.addEventListener("change", applyFilters);
    typeFilter.addEventListener("change", applyFilters);
    pdfFilter.addEventListener("change", applyFilters);
  }})();
  </script>
</body>
</html>
"""


def _render_master_sitemap(archive_root: Path, archives: list[RenderedArchive]) -> str:
    groups = []
    for archive in archives:
        index_href = os.path.relpath(archive.browser_dir / "index.html", archive_root).replace(os.sep, "/")
        rows = "".join(
            _render_sitemap_row(
                os.path.relpath(post.path, archive_root).replace(os.sep, "/"),
                post,
            )
            for post in archive.posts
        )
        groups.append(
            f"""
    <section class="archive-group">
      <header class="archive-heading">
        <h2><a href="{escape(index_href)}">{escape(archive.title)}</a></h2>
        <p class="archive-meta">{escape(archive.directory_name)} | {len(archive.posts)} posts</p>
      </header>
      <div class="sitemap-list">
        {rows or '<div class="empty-state">No posts were available in this archive.</div>'}
      </div>
    </section>
"""
        )

    body = "".join(groups) if groups else '<div class="empty-state">No archive directories with search_docs.jsonl were found.</div>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Piazza Archive Sitemap</title>
  <link rel="stylesheet" href="assets/styles.css">
</head>
<body>
  <div class="page">
    <header class="site-header">
      <h1 class="site-title">Piazza Archive Sitemap</h1>
      <p class="site-subtitle">Direct links to every generated post page across all local archives</p>
    </header>
    {body}
  </div>
</body>
</html>
"""


def _render_archive_row(browser_dir: Path, post: RenderedPostPage) -> str:
    href = os.path.relpath(post.path, browser_dir).replace(os.sep, "/")
    return _render_sitemap_row(
        href,
        post,
        search_blob=post.search_blob,
        folders=post.folders,
        labels=post.labels,
        post_type=post.post_type,
        has_pdf=post.has_pdf,
    )


def _render_sitemap_row(
    href: str,
    post: RenderedPostPage,
    search_blob: str | None = None,
    folders: list[str] | None = None,
    labels: list[str] | None = None,
    post_type: str | None = None,
    has_pdf: bool | None = None,
) -> str:
    data_attrs = ""
    if search_blob is not None:
        data_attrs = (
            f' data-search="{escape(search_blob, quote=True)}"'
            f' data-folders="{escape(" ".join(folders or []), quote=True)}"'
            f' data-labels="{escape(" ".join(labels or []), quote=True)}"'
            f' data-type="{escape(post_type or "", quote=True)}"'
            f' data-has-pdf="{str(bool(has_pdf)).lower()}"'
        )

    description_html = f'<span class="row-description">{escape(post.description)}</span>' if post.description else ""
    return (
        f'<a class="sitemap-row" href="{escape(href)}"{data_attrs}>'
        f'<span class="row-prefix">#{escape(post.post_ref)}</span>'
        f'<span class="row-title">{escape(post.title)}</span>'
        f'{description_html}'
        f"</a>"
    )


def _render_post_page(
    archive_dir: Path,
    page_path: Path,
    post: dict[str, Any],
    attachments: list[dict[str, Any]],
    class_info: dict[str, Any],
) -> str:
    number = _post_ref(post)
    subject = _clean_text(post.get("subject")) or "(untitled)"
    network_id = _clean_text(post.get("network_id"))
    body_html = _paragraphs(post.get("body_text", ""))
    student_html = _render_answer_section("Students' Answer", post.get("student_answer", {}))
    instructor_html = _render_answer_section("Instructors' Answer", post.get("instructor_answer", {}))
    followups_html = _render_followups_section(post.get("followups", []))
    attachment_html = _render_attachment_section(archive_dir, page_path, attachments)

    meta_bits = []
    if _clean_text(post.get("post_type")):
        meta_bits.append(f'<span class="chip">{escape(_clean_text(post.get("post_type")))}</span>')
    meta_bits.extend(f'<span class="chip">{escape(folder)}</span>' for folder in post.get("folders", []))
    meta_bits.extend(f'<span class="chip label">{escape(label)}</span>' for label in post.get("labels", []))
    if _clean_text(post.get("status")):
        meta_bits.append(f'<span class="chip status">{escape(_clean_text(post.get("status")))}</span>')
    if post.get("has_pdf"):
        meta_bits.append('<span class="chip">PDF</span>')

    detail_bits = []
    for label, value in [
        ("Created", post.get("created_at")),
        ("Updated", post.get("updated_at")),
        ("Views", post.get("view_count")),
        ("Resolved", post.get("resolved")),
    ]:
        cleaned = _clean_text(value)
        if cleaned:
            detail_bits.append(f"{label}: {escape(cleaned)}")

    piazza_url = f"https://piazza.com/class/{network_id}/post/{number}" if network_id and number else ""
    post_type = _clean_text(post.get("post_type")) or "post"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Post {escape(number)} | {escape(subject)}</title>
  <link rel="stylesheet" href="../assets/styles.css">
</head>
<body>
  <div class="page">
    <nav class="nav-row"><a href="../index.html">Back to archive index</a></nav>

    <article class="post-shell">
      <header>
        <div class="post-title-row">
          <span class="row-prefix">{escape(post_type)} @{escape(number)}</span>
          <h1>{escape(subject)}</h1>
        </div>
        {f'<div class="chip-row">{"".join(meta_bits)}</div>' if meta_bits else ''}
        {f'<p class="post-meta">{" | ".join(detail_bits)}</p>' if detail_bits else ''}
        {f'<p class="post-meta"><a href="{escape(piazza_url)}">Open original Piazza post</a></p>' if piazza_url else ''}
      </header>

      <section class="body-block">
        {body_html}
      </section>
    </article>

    {student_html}
    {instructor_html}
    {followups_html}
    {attachment_html}

    <p class="nav-row"><a href="../index.html">Back to archive index</a></p>
  </div>
</body>
</html>
"""


def _render_answer_section(title: str, answer: dict[str, Any]) -> str:
    content = _clean_text(answer.get("content_text"))
    if not content:
        return ""
    subtitle_bits = []
    if _clean_text(answer.get("author_label")):
        subtitle_bits.append(f"Updated by {escape(_clean_text(answer.get('author_label')))}")
    if _clean_text(answer.get("created_at")):
        subtitle_bits.append(escape(_clean_text(answer.get("created_at"))))
    subtitle = " | ".join(subtitle_bits)
    return f"""
      <section class="answer-shell">
        <h2>{escape(title)}</h2>
        {f'<p class="section-subtitle">{subtitle}</p>' if subtitle else ''}
        <div class="section-body">{_paragraphs(content)}</div>
      </section>
    """


def _render_followups_section(followups: list[dict[str, Any]]) -> str:
    if not followups:
        return ""
    items = "".join(_render_followup_item(item) for item in followups)
    count = len(followups)
    return f"""
      <section class="thread-shell">
        <h2>{count} Followup Discussion{'s' if count != 1 else ''}</h2>
        <ul class="followup-list">{items}</ul>
      </section>
    """


def _render_followup_item(block: dict[str, Any]) -> str:
    meta_bits = []
    if _clean_text(block.get("type")):
        meta_bits.append(escape(_clean_text(block.get("type"))))
    if _clean_text(block.get("author_label")):
        meta_bits.append(escape(_clean_text(block.get("author_label"))))
    if _clean_text(block.get("created_at")):
        meta_bits.append(escape(_clean_text(block.get("created_at"))))
    subject = _clean_text(block.get("subject"))
    body = _paragraphs(block.get("content_text", ""))
    children = block.get("children", [])
    nested = ""
    if children:
        nested = f'<div class="nested-followups"><ul class="followup-list">{"".join(_render_followup_item(child) for child in children)}</ul></div>'
    return f"""
      <li class="followup">
        {f'<p class="followup-meta">{" | ".join(meta_bits)}</p>' if meta_bits else ''}
        {f'<div class="followup-body"><p><strong>{escape(subject)}</strong></p></div>' if subject else ''}
        {f'<div class="followup-body">{body}</div>' if body else ''}
        {nested}
      </li>
    """


def _render_attachment_section(archive_dir: Path, page_path: Path, attachments: list[dict[str, Any]]) -> str:
    items = []
    for attachment in attachments:
        local_path = attachment.get("local_path")
        if not local_path:
            continue
        target = archive_dir / local_path
        if not target.exists():
            continue
        href = os.path.relpath(target, page_path.parent).replace(os.sep, "/")
        filename = _best_attachment_name(attachment, target)
        items.append(f'<li><a href="{escape(href)}">{escape(filename)}</a></li>')
    if not items:
        return ""
    return f"""
      <section class="answer-shell attachments">
        <h2>Attachments</h2>
        <ul>{''.join(items)}</ul>
      </section>
    """


def _archive_title(class_info: dict[str, Any]) -> str:
    for key in ["my_name", "name", "course_number", "id"]:
        value = _clean_text(class_info.get(key))
        if value:
            return value
    return "Piazza Archive"


def _post_ref(post: dict[str, Any]) -> str:
    return _clean_text(post.get("post_number")) or _clean_text(post.get("post_id"))


def _post_slug(post: dict[str, Any]) -> str:
    return slugify(_post_ref(post), fallback="post")


def _post_sort_key(post: dict[str, Any]) -> tuple[int, str]:
    ref = _post_ref(post)
    if ref.isdigit():
        return (1, f"{int(ref):09d}")
    return (0, ref)


def _description_text(post: dict[str, Any]) -> str:
    for value in [
        post.get("body_text"),
        post.get("student_answer", {}).get("content_text"),
        post.get("instructor_answer", {}).get("content_text"),
        post.get("followup_text"),
    ]:
        cleaned = _clean_text(value)
        if cleaned:
            return cleaned
    return ""


def _search_blob(post: dict[str, Any]) -> str:
    return " ".join(
        cleaned
        for cleaned in [
            _clean_text(post.get("subject")).lower(),
            _description_text(post).lower(),
            " ".join(_clean_text(folder).lower() for folder in post.get("folders", [])),
            " ".join(_clean_text(label).lower() for label in post.get("labels", [])),
            " ".join(_clean_text(name).lower() for name in post.get("attachment_names", [])),
        ]
        if cleaned
    )


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text == "None":
        return ""
    return text


def _paragraphs(text: Any) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    paragraphs = [part.strip() for part in cleaned.split("\n") if part.strip()]
    if not paragraphs:
        paragraphs = [cleaned]
    return "".join(f"<p>{escape(part)}</p>" for part in paragraphs)


def _best_attachment_name(attachment: dict[str, Any], target: Path) -> str:
    filename = _clean_text(attachment.get("filename"))
    if filename and filename.lower() not in {"s3", "file", "download"}:
        return filename
    url = _clean_text(attachment.get("url"))
    if url:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        prefix_values = query.get("prefix", [])
        if prefix_values:
            candidate = unquote(prefix_values[0]).rstrip("/").rsplit("/", 1)[-1]
            if candidate:
                return candidate
        candidate = unquote(parsed.path.rstrip("/").rsplit("/", 1)[-1])
        if candidate and candidate.lower() not in {"s3", "redirect"}:
            return candidate
    return target.name
