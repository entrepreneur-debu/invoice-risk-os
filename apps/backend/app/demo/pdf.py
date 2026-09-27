"""Minimal text PDF writer (no dependencies). Produces real text-layer PDFs for demos/tests."""

from dataclasses import dataclass


def _escape(text: str) -> str:
    safe = text.encode("latin-1", "replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_pdf(lines: list[str], font_size: int = 10) -> bytes:
    content_lines = [f"BT /F1 {font_size} Tf 50 800 Td {font_size + 4} TL"]
    for line in lines:
        content_lines.append(f"({_escape(line)}) Tj T*")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


@dataclass(frozen=True)
class DemoLine:
    description: str
    quantity: str
    unit_price: str
    tax_rate: str
    amount: str


def invoice_pdf(
    *,
    vendor_name: str,
    vendor_gstin: str | None,
    buyer_gstin: str | None,
    invoice_number: str,
    invoice_date: str,
    due_date: str | None,
    po_number: str | None,
    lines: list[DemoLine],
    subtotal: str,
    cgst: str | None,
    sgst: str | None,
    igst: str | None,
    total: str,
    account_number: str | None = None,
    ifsc: str | None = None,
    extra_lines: list[str] | None = None,
) -> bytes:
    text = [f"Supplier Name: {vendor_name}"]
    if vendor_gstin:
        text.append(f"GSTIN: {vendor_gstin}")
    text += ["TAX INVOICE", f"Invoice No: {invoice_number}", f"Invoice Date: {invoice_date}"]
    if due_date:
        text.append(f"Due Date: {due_date}")
    if buyer_gstin:
        text.append(f"Buyer GSTIN: {buyer_gstin}")
    if po_number:
        text.append(f"PO Number: {po_number}")
    text += ["", "Description   Qty   Unit Price   GST   Amount"]
    text += [
        f"{ln.description}   {ln.quantity}   {ln.unit_price}   {ln.tax_rate}%   {ln.amount}"
        for ln in lines
    ]
    text += ["", f"Subtotal: {subtotal}"]
    if cgst:
        text.append(f"CGST: {cgst}")
    if sgst:
        text.append(f"SGST: {sgst}")
    if igst:
        text.append(f"IGST: {igst}")
    text.append(f"Grand Total: {total}")
    if account_number:
        text += ["", "Bank details", f"A/C No: {account_number}", f"IFSC: {ifsc}"]
    text += extra_lines or []
    return text_pdf(text)
