#%%
"""Convert a rendered standalone dashboard page into a publishable body fragment.

Dashboard renderers write complete HTML documents, which is right for local
viewing. Publishing a page as a hosted artifact needs the same content without
the document wrapper: no doctype, ``<html>``, ``<head>``, or ``<body>`` tags,
with the stylesheet inlined ahead of the content.

Doing that conversion by hand is error-prone — it is easy to drop a ``<style>``
block or leave relative links that resolve to nothing once the page is served on
its own. This module does it once, in one place, so every renderer can emit a
publishable twin next to its normal output.

The conversion is structural only. It never edits the page's data, values, or
tables.
"""

from __future__ import annotations

from pathlib import Path
import re


BODY_SUFFIX = "_body.html"

_HEAD_PATTERN = re.compile(r"<head[^>]*>(.*?)</head>", re.IGNORECASE | re.DOTALL)
_BODY_PATTERN = re.compile(r"<body[^>]*>(.*)</body>", re.IGNORECASE | re.DOTALL)
_STYLE_PATTERN = re.compile(r"<style[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
# Relative links to sibling pages. A published fragment has no siblings, so these
# would 404. Absolute links (http:, mailto:) and in-page anchors (#) still work.
_LOCAL_LINK_PATTERN = re.compile(
    r'<a\s+href="(?!https?:|mailto:|#)[^"]*\.html[^"]*"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


def build_body_fragment(
    document: str,
    *,
    title: str | None = None,
    banner_html: str = "",
    neutralize_local_links: bool = True,
) -> str:
    """Return ``document`` as a body fragment suitable for artifact publishing.

    ``title`` overrides the document's own title. ``banner_html`` is inserted
    ahead of the content, which is where a provenance or staleness warning
    belongs on a snapshot. Relative links to sibling ``.html`` pages become plain
    text unless ``neutralize_local_links`` is False.
    """
    head_match = _HEAD_PATTERN.search(document)
    head = head_match.group(1) if head_match else ""
    body_match = _BODY_PATTERN.search(document)
    body = body_match.group(1) if body_match else document
    styles = "\n".join(_STYLE_PATTERN.findall(head))
    if title is None:
        title_match = _TITLE_PATTERN.search(head)
        title = title_match.group(1).strip() if title_match else ""
    if neutralize_local_links:
        body = _LOCAL_LINK_PATTERN.sub(r'<span class="unlinked">\1</span>', body)
    parts = [f"<title>{title}</title>"] if title else []
    if styles:
        parts.append(styles)
    if banner_html:
        parts.append(banner_html)
    parts.append(body)
    return "\n".join(parts)


def write_body_fragment(
    page_path: Path | str,
    *,
    title: str | None = None,
    banner_html: str = "",
    neutralize_local_links: bool = True,
) -> Path:
    """Write ``<page>_body.html`` beside a rendered page and return its path."""
    page_path = Path(page_path)
    document = page_path.read_text(encoding="utf-8")
    fragment = build_body_fragment(
        document,
        title=title,
        banner_html=banner_html,
        neutralize_local_links=neutralize_local_links,
    )
    fragment_path = page_path.with_name(page_path.stem + BODY_SUFFIX)
    fragment_path.write_text(fragment, encoding="utf-8")
    return fragment_path


def provenance_banner_html(message: str, *, tone: str = "warning") -> str:
    """Build a banner recording where a published snapshot came from.

    A published page outlives the run that produced it. Without a banner, a
    snapshot of superseded artifacts reads as current.
    """
    palette = {
        "warning": ("#f6e4e2", "#9b2c2c", "#5f2321"),
        "info": ("#e6ebf3", "#3c5a80", "#243447"),
    }
    background, border, text = palette.get(tone, palette["warning"])
    return (
        f'<div style="background:{background};border-left:4px solid {border};'
        'padding:12px 16px;margin:0 0 16px;font-size:13.5px;line-height:1.5;'
        f'color:{text}">{message}</div>'
    )


#%%
