"""Uploaded documents are untrusted: type, size, structure and active content checks."""

import io

import pytest
from PIL import Image

from app.core.errors import InvalidInput
from app.demo.pdf import text_pdf
from app.modules.invoices.documents import safe_filename, storage_key, validate_document

LIMIT = 1_000_000
PDF = text_pdf(["Invoice No: INV-1", "Grand Total: 100.00"])


def png_bytes(size: tuple[int, int] = (10, 10)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def code_of(
    data: bytes, filename: str | None = "x.pdf", declared: str | None = None, limit: int = LIMIT
) -> str:
    with pytest.raises(InvalidInput) as exc_info:
        validate_document(data, filename, declared, limit)
    return exc_info.value.code


def test_valid_pdf_is_accepted_with_text_layer_and_hash() -> None:
    result = validate_document(PDF, "Invoice March.pdf", "application/pdf", LIMIT)
    assert result.content_type == "application/pdf"
    assert result.page_count == 1
    assert result.text and "INV-1" in result.text
    assert len(result.sha256) == 64


def test_valid_png_is_accepted() -> None:
    result = validate_document(png_bytes(), "scan.png", "image/png", LIMIT)
    assert result.content_type == "image/png" and result.text is None


@pytest.mark.parametrize(
    ("data", "filename", "declared", "code"),
    [
        (b"", "x.pdf", None, "empty_file"),
        (b"MZ\x90\x00 executable", "invoice.pdf", None, "unsupported_file_type"),
        (b"<html><script>alert(1)</script>", "invoice.html", "text/html", "unsupported_file_type"),
        (PDF, "invoice.exe", None, "extension_mismatch"),
        (PDF, "invoice.png", None, "extension_mismatch"),
        (PDF, "invoice.pdf", "image/png", "content_type_mismatch"),
        (b"%PDF-1.4\n garbage that is not a pdf", "x.pdf", None, "malformed_file"),
        (b"\x89PNG\r\n\x1a\n not really", "x.png", None, "malformed_file"),
    ],
)
def test_rejects_invalid_documents(
    data: bytes, filename: str, declared: str | None, code: str
) -> None:
    assert code_of(data, filename, declared) == code


def test_rejects_oversized_files() -> None:
    assert code_of(PDF, limit=10) == "file_too_large"


def test_rejects_pdfs_with_active_content() -> None:
    malicious = PDF.replace(
        b"/Type /Catalog", b"/Type /Catalog /OpenAction << /S /JavaScript /JS (app.alert(1)) >>"
    )
    assert code_of(malicious) == "pdf_active_content"


def test_rejects_decompression_bomb_images() -> None:
    assert code_of(png_bytes((7000, 7000)), "big.png") == "image_too_large"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd.pdf"),
        ("C:\\Windows\\evil.pdf", "evil.pdf"),
        ("in<voice>|;rm -rf.pdf", "in_voice_rm -rf.pdf"),
        ("", "document.pdf"),
        ("..", "document.pdf"),
        ("a" * 300 + ".pdf", "a" * 100 + ".pdf"),
    ],
)
def test_filenames_are_sanitised(raw: str, expected: str) -> None:
    assert safe_filename(raw, "pdf") == expected


def test_storage_keys_never_contain_user_input() -> None:
    assert storage_key("org1", "inv1", "doc1", "pdf") == "org/org1/invoices/inv1/doc1.pdf"
