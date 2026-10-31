"""Clean the rich text (HTML from the Quill editor) in reviews and comments.

Only the formatting the editor offers survives: paragraphs, line breaks, bold,
italic, underline, strike-through, lists, quotes and http(s) links. Every other
tag is dropped but its text kept; script and style contents are dropped too.
Text without any tags is plain text (older posts and API clients) and is
stored unchanged; the pages escape it when they show it.
"""

import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

ALLOWED_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "s", "ol", "ul", "li", "blockquote", "a"}
VOID_TAGS = {"br"}
DROPPED_CONTENT_TAGS = {"script", "style", "template", "iframe", "object", "textarea", "title"}
LIST_STYLES = {"bullet", "ordered"}
TAG_PATTERN = re.compile(r"<[a-z][\s\S]*>", re.IGNORECASE)


def is_html(value: str) -> bool:
    return bool(TAG_PATTERN.search(value))


def _safe_url(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    parts = urlsplit(value)
    return value if parts.scheme in ("http", "https") and parts.netloc else None


class _Cleaner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.text: list[str] = []
        self.open_tags: list[str] = []
        self.dropping = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROPPED_CONTENT_TAGS:
            self.dropping += 1
            return
        if self.dropping or tag not in ALLOWED_TAGS:
            return
        # Like a browser, a new list item or paragraph ends an unclosed one.
        if tag in ("li", "p") and self.open_tags and self.open_tags[-1] == tag:
            self.handle_endtag(tag)
        if tag in ("p", "li", "blockquote"):
            self.text.append("\n")
        attributes = dict(attrs)
        extra = ""
        if tag == "a":
            url = _safe_url(attributes.get("href"))
            if url:
                extra = f' href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer nofollow"'
        elif tag == "li" and attributes.get("data-list") in LIST_STYLES:
            extra = f' data-list="{attributes["data-list"]}"'
        self.output.append(f"<{tag}{extra}>")
        if tag in VOID_TAGS:
            self.text.append("\n")
        else:
            self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS and tag in self.open_tags and not self.dropping:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in DROPPED_CONTENT_TAGS:
            self.dropping = max(0, self.dropping - 1)
            return
        if self.dropping or tag not in self.open_tags:
            return
        # Close anything left open inside this tag, so the output always nests.
        while self.open_tags:
            current = self.open_tags.pop()
            self.output.append(f"</{current}>")
            if current == tag:
                break
        if tag in ("p", "li", "blockquote"):
            self.text.append("\n")

    def handle_data(self, data):
        if self.dropping:
            return
        self.output.append(html.escape(data, quote=False))
        self.text.append(data)

    def result(self) -> tuple[str, str]:
        self.output.extend(f"</{tag}>" for tag in reversed(self.open_tags))
        return "".join(self.output), "".join(self.text)


def clean(value: str) -> tuple[str, str]:
    """Return (stored value, its plain text). Plain text input is returned as is."""
    if not is_html(value):
        return value, value
    cleaner = _Cleaner()
    cleaner.feed(value)
    cleaner.close()
    cleaned, text = cleaner.result()
    return cleaned, text.strip()


def plain_text(value: str) -> str:
    return clean(value)[1]
