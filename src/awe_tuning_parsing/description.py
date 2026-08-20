"""Turn a Shopify product's body_html into plain text via selectolax."""
from __future__ import annotations

from selectolax.parser import HTMLParser


def html_to_text(body_html: str) -> str:
    if not body_html:
        return ""
    tree = HTMLParser(body_html)
    for tag in tree.css("script, style"):
        tag.decompose()
    text = tree.body.text(separator="\n", strip=True) if tree.body else tree.text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)
