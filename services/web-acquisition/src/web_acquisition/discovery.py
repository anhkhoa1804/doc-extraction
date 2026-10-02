"""Bounded HTML discovery only: no JS, secondary fetching, or document parsing."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import ClassVar


@dataclass(frozen=True)
class Link:
    url: str
    method: str


class LinkParser(HTMLParser):
    ATTRIBUTES: ClassVar[dict[str, str]] = {
        "a": "href",
        "link": "href",
        "img": "src",
        "script": "src",
        "iframe": "src",
        "object": "data",
        "embed": "src",
    }

    def __init__(self, max_links: int):
        super().__init__(convert_charrefs=True)
        self.max_links = max_links
        self.links: list[Link] = []
        self.canonical: str | None = None
        self.truncated = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = self.ATTRIBUTES.get(tag)
        values = dict(attrs)
        if tag == "link" and "canonical" in (values.get("rel") or "").lower().split():
            self.canonical = values.get("href")
        if attr and values.get(attr):
            if len(self.links) >= self.max_links:
                self.truncated = True
                return
            self.links.append(Link(str(values[attr]), "html_" + tag))
