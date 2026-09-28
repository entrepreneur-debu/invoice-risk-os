"""SSRF-protected fetching of invoice documents from user-supplied URLs.

Threats handled:
- Private, loopback, link-local (incl. cloud metadata 169.254.169.254), CGNAT, multicast,
  reserved and IPv4-mapped/6to4-embedded private addresses: blocked.
- DNS rebinding / TOCTOU: we resolve once, validate every address, then connect to the
  validated IP (TLS still verified against the hostname via SNI + hostname check).
- Redirects: followed manually, at most N, each hop fully re-validated.
- Protocol smuggling: only http(s); http only when explicitly allowed; allow-listed ports;
  credentials in URLs rejected.
- Resource exhaustion: connect/read timeouts, an overall deadline, streamed size cap.
"""

import ipaddress
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlsplit

import urllib3
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from app.core.errors import InvalidInput

Resolver = Callable[[str, int], list[str]]

USER_AGENT = "InvoiceRiskOS-Importer/1.0"
_CHUNK = 64 * 1024


def default_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def is_public_address(raw: str) -> bool:
    try:
        address = ipaddress.ip_address(raw.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        embedded = address.ipv4_mapped or address.sixtofour
        if embedded is not None:
            address = embedded
        elif address.teredo is not None:
            return False
    return bool(
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


@dataclass(frozen=True)
class FetchPolicy:
    max_bytes: int
    timeout_seconds: float
    max_redirects: int
    allow_http: bool
    allowed_ports: tuple[int, ...]
    # Tests only: permits loopback so redirect/size logic can be exercised locally.
    allow_private_addresses: bool = False


@dataclass(frozen=True)
class FetchedDocument:
    data: bytes
    content_type: str | None
    host: str
    filename_hint: str | None


@dataclass(frozen=True)
class _Target:
    scheme: str
    host: str
    port: int
    path: str
    host_header: str


def _parse(url: str, policy: FetchPolicy) -> _Target:
    if len(url) > 2048:
        raise InvalidInput("URL is too long", code="url_invalid")
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as exc:
        raise InvalidInput("URL is not valid", code="url_invalid") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("https", "http") or (scheme == "http" and not policy.allow_http):
        raise InvalidInput("Only https:// URLs can be imported", code="url_scheme_not_allowed")
    if parts.username or parts.password:
        raise InvalidInput("URLs with embedded credentials are not allowed", code="url_invalid")
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise InvalidInput("URL has no host", code="url_invalid")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InvalidInput("URL host is not valid", code="url_invalid") from exc
    port = port or (443 if scheme == "https" else 80)
    if port not in policy.allowed_ports:
        raise InvalidInput("URL port is not allowed", code="url_port_not_allowed")
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    default_port = port == (443 if scheme == "https" else 80)
    host_header = host if default_port else f"{host}:{port}"
    return _Target(scheme, host, port, path, host_header)


def _resolve_public(target: _Target, policy: FetchPolicy, resolver: Resolver) -> str:
    try:
        addresses = resolver(target.host, target.port)
    except (OSError, UnicodeError) as exc:
        raise InvalidInput("URL host could not be resolved", code="url_resolution_failed") from exc
    if not addresses:
        raise InvalidInput("URL host could not be resolved", code="url_resolution_failed")
    if not policy.allow_private_addresses and not all(is_public_address(a) for a in addresses):
        # Reject if ANY address is non-public, so mixed DNS answers cannot be abused.
        raise InvalidInput(
            "URL points to a private or reserved network address", code="url_blocked_address"
        )
    return addresses[0]


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover - certifi ships with our dependencies
        return ssl.create_default_context()


def _filename_from(target: _Target, disposition: str | None) -> str | None:
    if disposition and "filename=" in disposition:
        return disposition.split("filename=", 1)[1].strip().strip('"')[:255] or None
    last = unquote(target.path.split("?", 1)[0].rsplit("/", 1)[-1])
    return last[:255] or None


def fetch_document(
    url: str, policy: FetchPolicy, resolver: Resolver = default_resolver
) -> FetchedDocument:
    deadline = time.monotonic() + policy.timeout_seconds
    current = url
    for _hop in range(policy.max_redirects + 1):
        target = _parse(current, policy)
        ip = _resolve_public(target, policy, resolver)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise InvalidInput("URL import timed out", code="url_timeout")
        timeout = urllib3.Timeout(connect=min(5.0, remaining), read=remaining)
        pool: urllib3.HTTPConnectionPool
        if target.scheme == "https":
            pool = urllib3.HTTPSConnectionPool(
                ip,
                target.port,
                timeout=timeout,
                retries=False,
                maxsize=1,
                server_hostname=target.host,
                assert_hostname=target.host,
                ssl_context=_ssl_context(),
            )
        else:
            pool = urllib3.HTTPConnectionPool(
                ip, target.port, timeout=timeout, retries=False, maxsize=1
            )
        try:
            response = pool.urlopen(
                "GET",
                target.path,
                headers={
                    "Host": target.host_header,
                    "User-Agent": USER_AGENT,
                    "Accept": "application/pdf,image/png,image/jpeg",
                },
                redirect=False,
                preload_content=False,
                retries=False,
            )
        except (Urllib3HTTPError, OSError) as exc:
            if "timed out" in str(exc).lower():
                raise InvalidInput("URL import timed out", code="url_timeout") from exc
            raise InvalidInput("The URL could not be fetched", code="url_fetch_failed") from exc

        try:
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise InvalidInput("Redirect without a location", code="url_fetch_failed")
                current = urljoin(current, location)
                continue
            if response.status != 200:
                raise InvalidInput(
                    f"The URL returned HTTP {response.status}", code="url_fetch_failed"
                )
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > policy.max_bytes:
                raise InvalidInput("The document is too large", code="url_response_too_large")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.stream(_CHUNK):
                size += len(chunk)
                if size > policy.max_bytes:
                    raise InvalidInput("The document is too large", code="url_response_too_large")
                if time.monotonic() > deadline:
                    raise InvalidInput("URL import timed out", code="url_timeout")
                chunks.append(chunk)
            return FetchedDocument(
                data=b"".join(chunks),
                content_type=response.headers.get("Content-Type"),
                host=target.host,
                filename_hint=_filename_from(target, response.headers.get("Content-Disposition")),
            )
        except (Urllib3HTTPError, OSError) as exc:
            if "timed out" in str(exc).lower():
                raise InvalidInput("URL import timed out", code="url_timeout") from exc
            raise InvalidInput("The URL could not be fetched", code="url_fetch_failed") from exc
        finally:
            # Close (not release) so partially read connections are never reused or leaked.
            response.close()
            conn = getattr(response, "connection", None)
            if conn is not None:
                conn.close()
            pool.close()
    raise InvalidInput("Too many redirects", code="url_too_many_redirects")
