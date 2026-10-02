"""Explicit URL identity rules; query ordering/slash collapsing are opt-in."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import unicodedata
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

from .models import AcquisitionError

_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_PERCENT = re.compile(r"%([0-9a-fA-F]{2})")


def origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def url_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def display_url(url: str) -> str:
    """Queries are execution-only; persistent provenance keeps a URL digest."""
    try:
        parts = urlsplit(url)
        host = parts.netloc.rsplit("@", 1)[-1]
        query = "[redacted]" if parts.query else ""
        return urlunsplit((parts.scheme, host, parts.path, query, ""))
    except ValueError:
        return "[invalid-url]"


def _encoding(value: str, safe: str) -> str:
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise AcquisitionError("invalid_percent_encoding")

    def replace(match: re.Match[str]) -> str:
        char = chr(int(match.group(1), 16))
        return char if char in _UNRESERVED else "%" + match.group(1).upper()

    return quote(_PERCENT.sub(replace, value), safe=safe + "%")


def _dot_segments(path: str) -> str:
    # RFC 3986 remove-dot-segments, retaining duplicate separators.
    output = ""
    while path:
        if path.startswith("../"):
            path = path[3:]
        elif path.startswith("./"):
            path = path[2:]
        elif path.startswith("/./") or path == "/.":
            path = "/" + path[3:]
        elif path.startswith("/../") or path == "/..":
            path = "/" + path[4:]
            output = output.rsplit("/", 1)[0]
        elif path in (".", ".."):
            path = ""
        else:
            end = path.find("/", 1 if path.startswith("/") else 0)
            if end < 0:
                end = len(path)
            output += path[:end]
            path = path[end:]
    return output or "/"


def normalize(
    url: str,
    base: str | None = None,
    *,
    query_mode: str = "preserve",
    collapse_slashes: bool = False,
    max_length: int = 4096,
) -> str:
    if (
        len(url) > max_length
        or any(unicodedata.category(c).startswith("C") for c in url)
        or "\\" in url
    ):
        raise AcquisitionError("invalid_url")
    try:
        parts = urlsplit(urljoin(base, url) if base else url)
        if parts.scheme.lower() not in ("http", "https"):
            raise AcquisitionError("unsupported_scheme")
        if parts.username is not None or parts.password is not None:
            raise AcquisitionError("userinfo_forbidden")
        host = parts.hostname
        if not host or "%" in host:
            raise AcquisitionError("invalid_host")
        host = host.rstrip(".").lower()
        try:
            address = ipaddress.ip_address(host)
            host = address.compressed
        except ValueError:
            if all(re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", part) for part in host.split(".")):
                raise AcquisitionError("noncanonical_ip")
            host = host.encode("idna").decode("ascii")
            if len(host) > 253 or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.split(".")
            ):
                raise AcquisitionError("invalid_host")
        scheme = parts.scheme.lower()
        port = parts.port
        if port is not None and not 1 <= port <= 65535:
            raise AcquisitionError("invalid_port")
        authority = f"[{host}]" if ":" in host else host
        if port and port != (443 if scheme == "https" else 80):
            authority += f":{port}"
        path = _dot_segments(_encoding(parts.path or "/", "/:@!$&'()*+,;="))
        if re.search(r"%2[fF]|%5[cC]", path):
            raise AcquisitionError("ambiguous_path_separator")
        if collapse_slashes:
            path = re.sub("/+", "/", path)
        query = _encoding(parts.query, "/?:@!$&'()*+,;=[]")
        if query_mode == "sort":
            query = urlencode(sorted(parse_qsl(query, keep_blank_values=True)))
        elif query_mode == "drop":
            query = ""
        result = urlunsplit((scheme, authority, path, query, ""))
        if len(result) > max_length:
            raise AcquisitionError("url_length_limit")
        return result
    except (ValueError, UnicodeError) as exc:
        raise AcquisitionError("invalid_url") from exc
