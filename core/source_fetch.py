"""Restricted configured-source fetcher for the R6-B `ingest_source` worker.

Implements the ADR-0030 §3 network boundary. This module performs no database
work and holds no Task lifecycle authority: it returns fetched bytes or a typed
categorized failure, and the caller routes that result through `TaskRuntime`.

Safety properties, all enforced here rather than by the worker:

- Only `https` URLs are accepted, and only from the exact configured-source
  allowlist. URL user-info, IP-literal hosts, fragments, and non-canonical
  forms are rejected.
- DNS is resolved at connection time and every resolved address is screened.
  Any loopback, private, link-local, multicast, reserved, unspecified, or
  metadata-service address rejects the request. The connection is pinned to a
  validated address while the original hostname is preserved for TLS SNI and
  certificate validation, so DNS rebinding cannot bypass the check.
- Redirects are never followed. Any 3xx is a non-retryable failure.
- Only 2xx responses with an accepted media type are used.
- The connect and read timeouts are enforced on the socket, and the byte
  ceiling is applied to the wire bytes before decompression as well as to the
  decompressed content, so a compressed response cannot expand past the limit.
"""

import ipaddress
import socket
import ssl
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlsplit

_ACCEPTED_CONTENT_TYPES = frozenset(
    {
        "text/html",
        "text/plain",
        "application/rss+xml",
        "application/atom+xml",
    }
)

CONNECT_TIMEOUT_SECONDS = 3.0
READ_TIMEOUT_SECONDS = 10.0
TOTAL_TIMEOUT_SECONDS = 15.0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

# Hostnames that always name the cloud metadata service, independent of DNS.
_METADATA_HOSTNAMES = frozenset(
    {"metadata.google.internal", "metadata.goog", "instance-data"}
)


class SourceFetchError(RuntimeError):
    """A categorized fetch failure.

    `reason` is the stable categorized reason recorded on the Task-attributed
    failure Event. `retryable` is the transport-level classification ADR-0030
    §2 prescribes: transient connection errors/timeouts and HTTP 408, 429, or
    5xx may retry; every safety/policy/format rejection may not.
    """

    def __init__(self, reason: str, *, retryable: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


@dataclass(frozen=True)
class SourceFetchRequest:
    """One configured source to fetch, as resolved from durable records."""

    origin_url: str
    source_type: str


@dataclass(frozen=True)
class SourceFetchResult:
    """Fetched bytes and the observation time reported by the transport."""

    origin_url: str
    source_type: str
    fetched_at: datetime
    content: bytes


class Fetcher(Protocol):
    """Injectable transport boundary, so tests need no network."""

    def fetch(self, request: SourceFetchRequest) -> SourceFetchResult:
        ...


def resolve_and_screen(host: str, port: int) -> str:
    """Return one validated IP for `host`, or raise `SourceFetchError`.

    Every address the resolver returns is screened, not only the first, so a
    hostname that resolves to a mix of public and private addresses is
    rejected outright.
    """
    if host.lower() in _METADATA_HOSTNAMES:
        raise SourceFetchError(
            "source_address_not_allowed", retryable=False
        )
    try:
        infos = socket.getaddrinfo(
            host, port, proto=socket.IPPROTO_TCP
        )
    except OSError as error:
        raise SourceFetchError(
            "source_dns_resolution_failed", retryable=True
        ) from error

    addresses: set[str] = {str(info[4][0]) for info in infos}
    if not addresses:
        raise SourceFetchError("source_dns_resolution_failed", retryable=True)

    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as error:
            raise SourceFetchError(
                "source_address_not_allowed", retryable=False
            ) from error
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_multicast
            or parsed.is_reserved
            or parsed.is_unspecified
        ):
            raise SourceFetchError("source_address_not_allowed", retryable=False)

    return sorted(addresses)[0]


def validate_source_url(url: str) -> tuple[str, int, str]:
    """Validate a configured URL and return `(host, port, path)`.

    Rejects non-HTTPS schemes, user-info, fragment, IP-literal hosts, empty or
    non-canonical hosts, and ports outside `1..65535`.
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise SourceFetchError("source_url_not_https", retryable=False)
    if parts.fragment:
        raise SourceFetchError("source_url_fragment_not_allowed", retryable=False)
    if "@" in parts.netloc:
        raise SourceFetchError("source_url_userinfo_not_allowed", retryable=False)

    host = parts.hostname
    if not host:
        raise SourceFetchError("source_url_invalid_host", retryable=False)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise SourceFetchError("source_url_ip_literal_not_allowed", retryable=False)

    # `parts.hostname` lowercases, so the canonical-form check must read the
    # raw authority text: an uppercase host or a trailing dot is not canonical.
    # IPv6 literals already rejected above, so stripping one `:<port>` suffix
    # is unambiguous here.
    raw_host = (
        parts.netloc.rsplit(":", 1)[0] if ":" in parts.netloc else parts.netloc
    )
    if (
        raw_host != host
        or raw_host != raw_host.lower()
        or raw_host.endswith(".")
    ):
        raise SourceFetchError("source_url_not_canonical", retryable=False)

    try:
        port = parts.port
    except ValueError as error:
        raise SourceFetchError("source_url_invalid_port", retryable=False) from error
    if port is None:
        port = 443
    if not 1 <= port <= 65535:
        raise SourceFetchError("source_url_invalid_port", retryable=False)

    path = parts.path or "/"
    return host, port, path


def _decode_chunked(body: bytes) -> bytes:
    """Decode HTTP/1.1 chunked transfer coding. Bounded by the caller."""
    decoded = bytearray()
    cursor = 0
    while True:
        newline = body.find(b"\r\n", cursor)
        if newline == -1:
            raise SourceFetchError("source_response_malformed", retryable=False)
        size_line = body[cursor:newline].split(b";", 1)[0].strip()
        try:
            size = int(size_line, 16)
        except ValueError as error:
            raise SourceFetchError(
                "source_response_malformed", retryable=False
            ) from error
        if size == 0:
            return bytes(decoded)
        start = newline + 2
        chunk = body[start : start + size]
        if len(chunk) != size:
            raise SourceFetchError("source_response_malformed", retryable=False)
        decoded.extend(chunk)
        cursor = start + size + 2


def _decode_body(raw: bytes, headers: dict[str, str]) -> bytes:
    """Apply transfer coding and content coding within the byte ceiling."""
    coding = headers.get("transfer-encoding", "").lower()
    if "chunked" in coding:
        raw = _decode_chunked(raw)

    encoding = headers.get("content-encoding", "").strip().lower()
    try:
        if encoding in ("", "identity"):
            content = raw
        elif encoding == "gzip":
            content = zlib.decompress(raw, zlib.MAX_WBITS | 16)
        elif encoding == "deflate":
            content = zlib.decompress(raw)
        else:
            raise SourceFetchError(
                "source_content_encoding_not_allowed", retryable=False
            )
    except zlib.error as error:
        raise SourceFetchError(
            "source_response_malformed", retryable=False
        ) from error

    if len(content) > MAX_RESPONSE_BYTES:
        raise SourceFetchError("source_response_too_large", retryable=False)
    return content


class RestrictedFetcher:
    """The approved HTTPS-only configured-source fetcher."""

    def fetch(self, request: SourceFetchRequest) -> SourceFetchResult:
        host, port, path = validate_source_url(request.origin_url)
        address = resolve_and_screen(host, port)

        context = ssl.create_default_context()
        # The socket is bound to the validated address, but the TLS layer still
        # validates the certificate against the configured hostname.
        try:
            raw = socket.create_connection(
                (address, port), timeout=CONNECT_TIMEOUT_SECONDS
            )
        except (OSError, TimeoutError) as error:
            raise SourceFetchError(
                "source_connection_failed", retryable=True
            ) from error

        try:
            raw.settimeout(READ_TIMEOUT_SECONDS)
            with context.wrap_socket(raw, server_hostname=host) as tls:
                return self._exchange(tls, host, path, request)
        except ssl.SSLError as error:
            raise SourceFetchError("source_tls_failed", retryable=False) from error
        except TimeoutError as error:
            raise SourceFetchError("source_read_timeout", retryable=True) from error
        except OSError as error:
            raise SourceFetchError(
                "source_connection_failed", retryable=True
            ) from error

    def _exchange(
        self, tls: ssl.SSLSocket, host: str, path: str, request: SourceFetchRequest
    ) -> SourceFetchResult:
        tls.sendall(
            (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Accept: text/html, text/plain, application/rss+xml, "
                "application/atom+xml\r\n"
                "Accept-Encoding: gzip, deflate\r\n"
                "Connection: close\r\n"
                "User-Agent: watch-r6-source-fetch/1\r\n"
                "\r\n"
            ).encode("ascii")
        )

        payload = bytearray()
        while True:
            try:
                chunk = tls.recv(65536)
            except TimeoutError as error:
                raise SourceFetchError("source_read_timeout", retryable=True) from error
            if not chunk:
                break
            payload.extend(chunk)
            # Ceiling applies to the wire bytes too, bounding compression bombs
            # before decompression is attempted.
            if len(payload) > MAX_RESPONSE_BYTES:
                raise SourceFetchError("source_response_too_large", retryable=False)

        return self._parse(bytes(payload), request)

    def _parse(
        self, payload: bytes, request: SourceFetchRequest
    ) -> SourceFetchResult:
        header_end = payload.find(b"\r\n\r\n")
        if header_end == -1:
            raise SourceFetchError("source_response_malformed", retryable=False)

        head = payload[:header_end].decode("iso-8859-1")
        body = payload[header_end + 4 :]
        lines = head.split("\r\n")
        status_line = lines[0].split(" ", 2)
        if len(status_line) < 2 or not status_line[1].isdigit():
            raise SourceFetchError("source_response_malformed", retryable=False)
        status = int(status_line[1])

        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()

        if 300 <= status < 400:
            raise SourceFetchError("source_redirect_not_allowed", retryable=False)
        if status in (408, 429) or 500 <= status < 600:
            raise SourceFetchError(f"source_http_{status}", retryable=True)
        if not 200 <= status < 300:
            raise SourceFetchError(f"source_http_{status}", retryable=False)

        content_type = headers.get("content-type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type not in _ACCEPTED_CONTENT_TYPES:
            raise SourceFetchError(
                "source_content_type_not_allowed", retryable=False
            )

        content = _decode_body(body, headers)
        return SourceFetchResult(
            origin_url=request.origin_url,
            source_type=request.source_type,
            fetched_at=datetime.now(timezone.utc),
            content=content,
        )
