from __future__ import annotations

import argparse
import json
from pathlib import Path

from .archive import ArchiveConfig, run_archive
from .auth import SUPPORTED_BROWSERS, build_piazza_client, load_cookies
from .render_html import render_html_all, render_html_browser
from .search import search_archive
from .view import format_post_for_display, load_post_from_archive


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="piazza-rescue", description="Archive Piazza posts with cookie auth and local search.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    archive_parser = subparsers.add_parser("archive", help="Export a Piazza class.")
    archive_parser.add_argument("network_id", help="Piazza network id, for example example123456")
    archive_parser.add_argument("--output-root", default="archive", help="Directory where archive runs are created")
    archive_parser.add_argument("--preflight-post", help="Fetch this post first to validate visibility")
    archive_parser.add_argument("--cookie-file", help="Path to cookie JSON/text file")
    archive_parser.add_argument("--cookie-string", help="Inline Cookie header value")
    archive_parser.add_argument("--browser", choices=sorted(SUPPORTED_BROWSERS), help="Read Piazza cookies directly from a browser profile")
    archive_parser.add_argument("--sleep", type=float, default=1.0, help="Delay between post fetches")
    archive_parser.add_argument("--limit", type=int, help="Limit the number of posts fetched")
    archive_parser.add_argument("--download-pdfs", dest="download_pdfs", action="store_true", default=True, help="Download PDF attachments")
    archive_parser.add_argument("--no-download-pdfs", dest="download_pdfs", action="store_false", help="Skip PDF downloads")
    archive_parser.add_argument("--extract-pdf-text", dest="extract_pdf_text", action="store_true", default=True, help="Run pdftotext on downloaded PDFs")
    archive_parser.add_argument("--no-extract-pdf-text", dest="extract_pdf_text", action="store_false", help="Skip pdftotext extraction")
    archive_parser.add_argument("--build-search-db", dest="build_search_db", action="store_true", default=True, help="Build search.db")
    archive_parser.add_argument("--no-build-search-db", dest="build_search_db", action="store_false", help="Skip search.db creation")

    search_parser = subparsers.add_parser("search", help="Search an existing archive.")
    search_parser.add_argument("db_path", help="Path to search.db")
    search_parser.add_argument("query", help="Full-text search query")
    search_parser.add_argument("--limit", type=int, default=10, help="Maximum results to return")
    search_parser.add_argument("--label", help="Filter posts by derived label")
    search_parser.add_argument("--folder", help="Filter posts by folder/tag")
    search_parser.add_argument("--has-pdf", action="store_true", help="Only return posts with downloaded PDFs")
    search_parser.add_argument("--source", choices=["post", "pdf"], default="post", help="Search post text or extracted PDF text")

    show_parser = subparsers.add_parser("show", help="Display a single archived post.")
    show_parser.add_argument("archive_path", help="Archive directory or path to search.db inside the archive")
    show_parser.add_argument("post_ref", help="Post number, post id, or permalink token like 327 or @327_f1")
    show_parser.add_argument("--json", action="store_true", help="Print the normalized post JSON instead of formatted text")

    render_parser = subparsers.add_parser("render-html", help="Generate a static HTML browser for an archive.")
    render_parser.add_argument("archive_path", help="Archive directory or path to search.db inside the archive")
    render_parser.add_argument("--output-dir", default="browser", help="Output directory name, relative to the archive by default")

    render_all_parser = subparsers.add_parser("render-html-all", help="Generate static HTML browsers for every archive and a master sitemap.")
    render_all_parser.add_argument("archive_root", help="Root directory containing archive subdirectories")
    render_all_parser.add_argument("--output-dir", default="browser", help="Per-archive browser directory name")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "archive":
        cookies = load_cookies(cookie_file=args.cookie_file, cookie_string=args.cookie_string, browser=args.browser)
        piazza, rpc = build_piazza_client(cookies)
        archive_dir = run_archive(
            ArchiveConfig(
                network_id=args.network_id,
                output_root=Path(args.output_root),
                preflight_post=args.preflight_post,
                sleep_seconds=args.sleep,
                limit=args.limit,
                download_pdfs=args.download_pdfs,
                extract_pdf_text=args.extract_pdf_text,
                build_search_db=args.build_search_db,
            ),
            piazza=piazza,
            rpc=rpc,
        )
        print(json.dumps({"archive_dir": str(archive_dir)}, indent=2))
        return

    if args.command == "show":
        post, attachments = load_post_from_archive(Path(args.archive_path), args.post_ref)
        if args.json:
            print(json.dumps({"post": post, "attachments": attachments}, indent=2))
        else:
            print(format_post_for_display(post, attachments))
        return

    if args.command == "render-html":
        browser_dir = render_html_browser(Path(args.archive_path), output_dir=args.output_dir)
        print(json.dumps({"browser_dir": str(browser_dir)}, indent=2))
        return

    if args.command == "render-html-all":
        sitemap_path = render_html_all(Path(args.archive_root), output_dir=args.output_dir)
        print(json.dumps({"sitemap_path": str(sitemap_path)}, indent=2))
        return

    results = search_archive(
        Path(args.db_path),
        args.query,
        limit=args.limit,
        label=args.label,
        folder=args.folder,
        has_pdf=args.has_pdf,
        source=args.source,
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
