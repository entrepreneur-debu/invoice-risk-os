"""SSRF protections for invoice URL import."""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.core.errors import InvalidInput
from app.modules.invoices import url_import
from app.modules.invoices.url_import import FetchPolicy, fetch_document, is_public_address

PDF_BODY = b"%PDF-1.4 small body"


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.3.4",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "224.0.0.1",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "2002:0a00:0001::1",
        "240.0.0.1",
        "not-an-ip",
    ],
)
def test_private_and_special_addresses_are_not_public(address: str) -> None:
    assert not is_public_address(address)


@pytest.mark.parametrize("address", ["93.184.216.34", "8.8.8.8", "2606:4700:4700::1111"])
def test_public_addresses(address: str) -> None:
    assert is_public_address(address)


def policy(port: int, **overrides: object) -> FetchPolicy:
    values: dict[str, object] = dict(
        max_bytes=1000,
        timeout_seconds=5,
        max_redirects=2,
        allow_http=True,
        allowed_ports=(port, 443),
    )
    values.update(overrides)
    return FetchPolicy(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("ftp://example.com/x.pdf", "url_scheme_not_allowed"),
        ("file:///etc/passwd", "url_scheme_not_allowed"),
        ("gopher://example.com/", "url_scheme_not_allowed"),
        ("https://user:pass@example.com/x.pdf", "url_invalid"),
        ("https://example.com:22/x.pdf", "url_port_not_allowed"),
        ("https:///nohost", "url_invalid"),
    ],
)
def test_rejects_unsafe_urls_before_connecting(url: str, code: str) -> None:
    with pytest.raises(InvalidInput) as exc_info:
        fetch_document(url, policy(8080, allow_http=False), resolver=lambda h, p: ["93.184.216.34"])
    assert exc_info.value.code == code


def test_http_rejected_unless_allowed() -> None:
    with pytest.raises(InvalidInput) as exc_info:
        fetch_document(
            "http://example.com/x.pdf",
            policy(80, allow_http=False),
            resolver=lambda h, p: ["93.184.216.34"],
        )
    assert exc_info.value.code == "url_scheme_not_allowed"


@pytest.mark.parametrize(
    "answers", [["127.0.0.1"], ["169.254.169.254"], ["93.184.216.34", "10.0.0.1"], ["::1"]]
)
def test_blocks_hosts_resolving_to_private_addresses(answers: list[str]) -> None:
    with pytest.raises(InvalidInput) as exc_info:
        fetch_document("https://metadata.test/latest", policy(443), resolver=lambda h, p: answers)
    assert exc_info.value.code == "url_blocked_address"


def test_unresolvable_host() -> None:
    def resolver(host: str, port: int) -> list[str]:
        raise OSError("nxdomain")

    with pytest.raises(InvalidInput) as exc_info:
        fetch_document("https://nope.test/x.pdf", policy(443), resolver=resolver)
    assert exc_info.value.code == "url_resolution_failed"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        routes = {
            "/ok.pdf": (200, {"Content-Type": "application/pdf"}, PDF_BODY),
            "/big.pdf": (200, {"Content-Type": "application/pdf"}, b"x" * 5000),
            "/redirect": (302, {"Location": "/ok.pdf"}, b""),
            "/loop": (302, {"Location": "/loop"}, b""),
            "/to-internal": (302, {"Location": "http://internal.test/admin"}, b""),
            "/missing": (404, {}, b""),
        }
        status, headers, body = routes.get(self.path, (404, {}, b""))
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    # Treat only our loopback test server as "public"; every other private range stays blocked.
    real = url_import.is_public_address
    monkeypatch.setattr(url_import, "is_public_address", lambda ip: ip == "127.0.0.1" or real(ip))
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def resolver(host: str, port: int) -> list[str]:
    return {"files.test": ["127.0.0.1"], "internal.test": ["10.0.0.5"]}[host]


def test_fetches_document_and_follows_safe_redirect(server: int) -> None:
    result = fetch_document(f"http://files.test:{server}/redirect", policy(server), resolver)
    assert result.data == PDF_BODY
    assert result.host == "files.test"
    assert result.filename_hint == "ok.pdf"


def test_redirect_to_internal_address_is_revalidated_and_blocked(server: int) -> None:
    with pytest.raises(InvalidInput) as exc_info:
        fetch_document(
            f"http://files.test:{server}/to-internal",
            policy(server, allowed_ports=(server, 80)),
            resolver,
        )
    assert exc_info.value.code == "url_blocked_address"


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/big.pdf", "url_response_too_large"),
        ("/loop", "url_too_many_redirects"),
        ("/missing", "url_fetch_failed"),
    ],
)
def test_limits_and_failures(server: int, path: str, code: str) -> None:
    with pytest.raises(InvalidInput) as exc_info:
        fetch_document(f"http://files.test:{server}{path}", policy(server), resolver)
    assert exc_info.value.code == code
