import base64
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from truth_guardian.web.app import create_app
from truth_guardian.web.documents import extract, split
from truth_guardian.web.engine import ROOT
from truth_guardian.web.examples import ExampleStore


def pdf_with(text: str) -> bytes:
    """A one-page PDF with one line of text, written by hand (objects plus a cross-reference table)."""
    stream = f"BT /F1 12 Tf 72 712 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for i, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def docx_with(paragraphs: list[str]) -> bytes:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>')
    return out.getvalue()


def test_text_html_word_and_pdf_are_read():
    assert extract("notes.txt", "Anne Frank died in 1945.\r\n\r\n\r\nShe was 15.".encode()).text == "Anne Frank died in 1945.\n\nShe was 15."
    html = extract("page.html", b"<html><script>var x=1</script><p>Anne Frank died in 1945.</p><p>She was 15.</p></html>")
    assert html.text == "Anne Frank died in 1945.\n\nShe was 15."
    word = extract("report.docx", docx_with(["Anne Frank died in 1945.", "She was 15."]))
    assert word.kind == "docx" and word.text == "Anne Frank died in 1945.\nShe was 15."
    pdf = extract("paper.pdf", pdf_with("Anne Frank died in 1945."))
    assert pdf.kind == "pdf" and pdf.pages == 1 and "Anne Frank died in 1945." in pdf.text


def test_unusable_files_are_explained():
    with pytest.raises(ValueError, match="not supported"):
        extract("photo.png", b"\x89PNG")
    with pytest.raises(ValueError, match="not a valid Word document"):
        extract("fake.docx", b"not a zip")
    with pytest.raises(ValueError, match="no text"):
        extract("empty.txt", b"   \n ")


def test_long_text_is_split_at_paragraphs_then_sentences():
    text = "First paragraph sentence one. Sentence two.\n\nSecond paragraph is here."
    assert split(text, 60) == ["First paragraph sentence one. Sentence two.", "Second paragraph is here."]
    assert all(len(p) <= 30 for p in split("Alpha beta gamma. Delta epsilon zeta. Eta theta iota kappa.", 30))
    assert split("short", 100) == ["short"]


def test_documents_endpoint_returns_parts_that_fit_a_source():
    with TestClient(create_app(store=ExampleStore(ROOT), load=False)) as client:
        body = {"name": "paper.pdf", "data": base64.b64encode(pdf_with("Anne Frank died in 1945.")).decode()}
        found = client.post("/api/documents", json=body).json()
        assert found["kind"] == "pdf" and found["pages"] == 1 and found["parts"][0].startswith("Anne Frank")
        bad = client.post("/api/documents", json={"name": "x.png", "data": base64.b64encode(b"x").decode()})
        assert bad.status_code == 422 and "not supported" in bad.json()["detail"]
        assert client.post("/api/documents", json={"name": "x.txt", "data": "%%%"}).status_code == 422
        assert ".pdf" in client.get("/api/documents").json()["types"]
