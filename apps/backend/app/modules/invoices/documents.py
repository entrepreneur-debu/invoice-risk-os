"""Validation of untrusted invoice documents.

Accepted types (explicit allow-list): PDF, PNG, JPEG. Checks, in order:
size, filename, extension, magic bytes, declared content type, structural parse
(pypdf / Pillow), encryption, active content (JavaScript, launch actions, embedded
files), page/pixel limits. Uploaded files are never executed or rendered server-side
beyond text extraction, and are stored under a generated key, not their filename.
"""

import hashlib
import io
import logging
import re
import unicodedata
import warnings
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.errors import InvalidInput

logger = logging.getLogger(__name__)

MAX_PDF_PAGES = 50
MAX_IMAGE_PIXELS = 40_000_000
MAX_TEXT_CHARS = 100_000


@dataclass(frozen=True)
class DocumentType:
    content_type: str
    extension: str
    extensions: frozenset[str]


PDF = DocumentType("application/pdf", "pdf", frozenset({".pdf"}))
PNG = DocumentType("image/png", "png", frozenset({".png"}))
JPEG = DocumentType("image/jpeg", "jpg", frozenset({".jpg", ".jpeg"}))
ACCEPTED_TYPES = (PDF, PNG, JPEG)
ACCEPTED_EXTENSIONS = sorted(ext for t in ACCEPTED_TYPES for ext in t.extensions)

_ACTIVE_PDF_CONTENT = (
    b"/JavaScript",
    b"/JS ",
    b"/JS(",
    b"/Launch",
    b"/EmbeddedFile",
    b"/RichMedia",
)
_GENERIC_TYPES = {"", "application/octet-stream", "binary/octet-stream"}


@dataclass(frozen=True)
class ValidatedDocument:
    data: bytes
    content_type: str
    extension: str
    safe_filename: str
    sha256: str
    size_bytes: int
    page_count: int | None
    text: str | None  # text layer (PDF only); untrusted


def safe_filename(raw: str | None, fallback_extension: str) -> str:
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    name = re.sub(r"\.{2,}", ".", name)
    if not name:
        name = f"document.{fallback_extension}"
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, fallback_extension
    return f"{stem[:100] or 'document'}.{ext[:10].lower()}"


def _sniff(data: bytes) -> DocumentType | None:
    if data.startswith(b"%PDF-"):
        return PDF
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    return None


def _extension_of(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def validate_document(
    data: bytes, filename: str | None, declared_type: str | None, max_bytes: int
) -> ValidatedDocument:
    if not data:
        raise InvalidInput("The file is empty", code="empty_file")
    if len(data) > max_bytes:
        raise InvalidInput(
            f"File exceeds the {max_bytes // 1_048_576} MB limit", code="file_too_large"
        )
    doc_type = _sniff(data)
    if doc_type is None:
        raise InvalidInput(
            f"Unsupported file type. Accepted: {', '.join(ACCEPTED_EXTENSIONS)}",
            code="unsupported_file_type",
        )
    extension = _extension_of(filename)
    if extension and extension not in doc_type.extensions:
        raise InvalidInput(
            "File extension does not match the file contents", code="extension_mismatch"
        )
    declared = (declared_type or "").split(";")[0].strip().lower()
    if (
        declared not in _GENERIC_TYPES
        and declared != doc_type.content_type
        and not (doc_type is JPEG and declared == "image/jpg")
    ):
        raise InvalidInput(
            "Declared content type does not match the file contents", code="content_type_mismatch"
        )

    page_count: int | None = None
    text: str | None = None
    if doc_type is PDF:
        page_count, text = _inspect_pdf(data)
    else:
        _inspect_image(data)

    return ValidatedDocument(
        data=data,
        content_type=doc_type.content_type,
        extension=doc_type.extension,
        safe_filename=safe_filename(filename, doc_type.extension),
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        page_count=page_count,
        text=text,
    )


def _inspect_pdf(data: bytes) -> tuple[int, str | None]:
    if any(marker in data for marker in _ACTIVE_PDF_CONTENT):
        raise InvalidInput(
            "PDFs with scripts, launch actions or embedded files are not accepted",
            code="pdf_active_content",
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            reader = PdfReader(io.BytesIO(data), strict=False)
            if reader.is_encrypted:
                raise InvalidInput("Password-protected PDFs are not accepted", code="pdf_encrypted")
            page_count = len(reader.pages)
            if page_count == 0:
                raise InvalidInput("The PDF has no pages", code="malformed_file")
            if page_count > MAX_PDF_PAGES:
                raise InvalidInput(
                    f"PDFs are limited to {MAX_PDF_PAGES} pages", code="too_many_pages"
                )
            chunks: list[str] = []
            size = 0
            for page in reader.pages:
                chunk = page.extract_text() or ""
                chunks.append(chunk)
                size += len(chunk)
                if size >= MAX_TEXT_CHARS:
                    break
    except InvalidInput:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise InvalidInput(
            "The PDF could not be read (malformed file)", code="malformed_file"
        ) from exc
    text = "\n".join(chunks)[:MAX_TEXT_CHARS].strip()
    return page_count, text or None


def _inspect_image(data: bytes) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise InvalidInput("Image dimensions are too large", code="image_too_large")
            image.verify()
    except InvalidInput:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
    ) as exc:
        raise InvalidInput(
            "The image could not be read (malformed file)", code="malformed_file"
        ) from exc


def storage_key(
    organization_id: object, invoice_id: object, document_id: object, extension: str
) -> str:
    """Tenant-prefixed, generated key. User-supplied names never reach storage paths."""
    return f"org/{organization_id}/invoices/{invoice_id}/{document_id}.{extension}"
