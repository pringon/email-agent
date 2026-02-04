"""MIME body parsing utilities for Gmail messages."""

import base64
import re
from html.parser import HTMLParser
from typing import Optional


def decode_base64(data: str) -> str:
    """Decode Gmail's URL-safe base64 encoded data.

    Gmail uses URL-safe base64 encoding (RFC 4648) which replaces
    '+' with '-' and '/' with '_'.

    Args:
        data: Base64url encoded string

    Returns:
        Decoded UTF-8 string
    """
    # Add padding if necessary (base64 requires length divisible by 4)
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding

    decoded_bytes = base64.urlsafe_b64decode(data)
    return decoded_bytes.decode("utf-8", errors="replace")


def extract_body(payload: dict) -> tuple[str, Optional[str]]:
    """Extract plain text and HTML body from Gmail message payload.

    Gmail messages can have various structures:
    - Simple: body.data directly in payload
    - Multipart: parts array with different MIME types
    - Nested multipart: parts containing more parts

    Args:
        payload: Gmail message payload dictionary

    Returns:
        Tuple of (plain_text_body, html_body). HTML may be None.
    """
    plain_text = ""
    html_body = None

    def extract_from_parts(parts: list) -> None:
        nonlocal plain_text, html_body

        for part in parts:
            mime_type = part.get("mimeType", "")
            body_data = part.get("body", {}).get("data")

            if mime_type == "text/plain" and body_data and not plain_text:
                plain_text = decode_base64(body_data)
            elif mime_type == "text/html" and body_data and not html_body:
                html_body = decode_base64(body_data)
            elif mime_type.startswith("multipart/"):
                # Recursively handle nested multipart
                nested_parts = part.get("parts", [])
                if nested_parts:
                    extract_from_parts(nested_parts)

    # Check for simple message (body directly in payload)
    body_data = payload.get("body", {}).get("data")
    mime_type = payload.get("mimeType", "")

    if body_data:
        decoded = decode_base64(body_data)
        if mime_type == "text/html":
            html_body = decoded
        else:
            plain_text = decoded
    elif "parts" in payload:
        extract_from_parts(payload["parts"])

    # Fallback: convert HTML to plain text if no plain text found
    if not plain_text and html_body:
        plain_text = html_to_plain_text(html_body)

    return plain_text, html_body


def extract_email_address(header_value: str) -> tuple[str, str]:
    """Parse email header to extract display name and email address.

    Handles formats like:
    - "John Doe <john@example.com>"
    - "<john@example.com>"
    - "john@example.com"

    Args:
        header_value: Raw From/To header value

    Returns:
        Tuple of (display_name, email_address). Display name may equal
        email address if no name is present.
    """
    # Pattern: "Name <email>" or "<email>"
    match = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>$', header_value.strip())
    if match:
        name = match.group(1).strip()
        email = match.group(2).strip()
        return (name if name else email, email)

    # Plain email address
    email = header_value.strip()
    return (email, email)


class _HTMLTextExtractor(HTMLParser):
    """Simple HTML parser that extracts visible text content."""

    def __init__(self):
        super().__init__()
        self._text_parts: list[str] = []
        self._skip_tags = {"script", "style", "head", "title", "meta"}
        self._current_skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() in self._skip_tags:
            self._current_skip = True
        # Add line breaks for block elements
        if tag.lower() in {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._skip_tags:
            self._current_skip = False

    def handle_data(self, data: str) -> None:
        if not self._current_skip:
            self._text_parts.append(data)

    def get_text(self) -> str:
        text = "".join(self._text_parts)
        # Normalize whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n", "\n\n", text)
        return text.strip()


def html_to_plain_text(html: str) -> str:
    """Convert HTML to plain text by stripping tags.

    Args:
        html: HTML content

    Returns:
        Plain text with basic formatting preserved
    """
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html)
        return parser.get_text()
    except Exception:
        # Fallback: crude tag stripping
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
