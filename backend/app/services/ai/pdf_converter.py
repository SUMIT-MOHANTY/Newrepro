"""
PDF Conversion Service
Converts various file types to PDF using xhtml2pdf (pure-Python, no system deps).
Supported: PDF (passthrough), HTML/HTM, TXT, MD, CSV, DOCX, XLSX, PPTX, Images
"""

import io
import os
from pathlib import Path


# ── Public API ──────────────────────────────────────────────────────────────

def convert_to_pdf(file_path: str, original_filename: str, file_type: str = "") -> bytes:
    """
    Convert any supported file type to PDF bytes.
    Always returns bytes. Falls back to a simple error-page PDF on failure.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    # Try LibreOffice first for Office files (docx, xlsx, xls, pptx, ppt, etc.)
    if ext in (".docx", ".xlsx", ".xls", ".pptx", ".ppt"):
        try:
            return _convert_via_libreoffice(path, ext)
        except Exception as lo_err:
            print(f"[pdf_converter] LibreOffice conversion skipped/failed: {lo_err}. Falling back to Python libraries.")

    try:
        if ext == ".pdf":
            return path.read_bytes()
        elif ext in (".html", ".htm"):
            return _html_to_pdf(_read(path), base_path=str(path.parent))
        elif ext == ".md":
            return _html_to_pdf(_markdown_to_html(_read(path), original_filename))
        elif ext == ".csv":
            return _html_to_pdf(_csv_to_html(_read(path), original_filename))
        elif ext in (".txt", ".log", ".json", ".xml", ".yml", ".yaml"):
            return _html_to_pdf(_text_to_html(_read(path), original_filename))
        elif ext in (".docx",):
            return _docx_to_pdf(path, original_filename)
        elif ext in (".xlsx", ".xls"):
            return _excel_to_pdf(path, original_filename)
        elif ext in (".pptx", ".ppt"):
            return _pptx_to_pdf(path, original_filename)
        elif ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"):
            return _image_to_pdf(path, original_filename)
        else:
            # Try as text, fall back to error page
            try:
                return _html_to_pdf(_text_to_html(_read(path), original_filename))
            except Exception:
                return _error_pdf(original_filename, "This file type cannot be converted to PDF.")
    except Exception as e:
        print(f"[pdf_converter] Error converting {original_filename}: {e}")
        return _error_pdf(original_filename, f"Conversion error: {e}")


# ── Core HTML → PDF ─────────────────────────────────────────────────────────

def _html_to_pdf(html: str, base_path: str = "") -> bytes:
    from xhtml2pdf import pisa
    buf = io.BytesIO()

    def fetch_resource(uri, rel):
        """
        Resource policy:
          - Fonts (Google Fonts, CDN .woff/.woff2/.ttf/.otf/.eot) → allowed (fetch from internet)
          - Any other external URL (Bootstrap CSS, JS, API calls, etc.) → blocked (return None)
          - Local relative paths → resolved against base_path
        """
        is_external = uri.startswith("http://") or uri.startswith("https://")

        if is_external:
            # Allow only font file URLs
            FONT_EXTENSIONS = (".woff", ".woff2", ".ttf", ".otf", ".eot")
            FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")

            lower_uri = uri.lower()
            is_font_file = any(lower_uri.split("?")[0].endswith(ext) for ext in FONT_EXTENSIONS)
            is_font_api = any(host in lower_uri for host in FONT_HOSTS)

            if is_font_file or is_font_api:
                return uri  # Let xhtml2pdf fetch the font

            return None  # Block everything else (CSS CDNs, JS, API calls, etc.)

        # Local relative path — resolve against the HTML file's directory
        if base_path and not os.path.isabs(uri):
            full = os.path.join(base_path, uri)
            if os.path.exists(full):
                return full

        return None  # Unknown — skip silently

    result = pisa.CreatePDF(
        html,
        dest=buf,
        link_callback=fetch_resource
    )
    if result.err:
        raise RuntimeError(f"xhtml2pdf error: {result.err}")
    return buf.getvalue()


# ── File readers ─────────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ── HTML templates ───────────────────────────────────────────────────────────

_BASE_STYLE = """
    @page { margin: 2cm; }
    body { font-family: Helvetica, Arial, sans-serif; font-size: 11pt; color: #111; line-height: 1.6; }
    h1 { font-size: 18pt; color: #4f46e5; border-bottom: 1px solid #e5e7eb; padding-bottom: 6pt; }
    h2 { font-size: 14pt; color: #374151; }
    h3 { font-size: 12pt; color: #6b7280; }
    pre { font-size: 8pt; background: #f4f4f4; padding: 8pt; border-radius: 4pt; white-space: pre-wrap; word-break: break-all; }
    code { font-size: 9pt; background: #f4f4f4; padding: 1pt 3pt; }
    table { width: 100%; border-collapse: collapse; margin: 8pt 0; }
    th { background: #4f46e5; color: white; padding: 5pt 8pt; font-size: 9pt; text-align: left; }
    td { padding: 4pt 8pt; font-size: 9pt; border: 0.5pt solid #d1d5db; }
    tr:nth-child(even) td { background: #f9fafb; }
    img { max-width: 100%; }
"""

def _wrap_html(title: str, body: str, extra_style: str = "") -> str:
    import html as html_lib
    safe_title = html_lib.escape(title)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{safe_title}</title>
<style>{_BASE_STYLE}{extra_style}</style>
</head><body>
<h1>{safe_title}</h1>
{body}
</body></html>"""


def _text_to_html(content: str, filename: str) -> str:
    import html as html_lib
    escaped = html_lib.escape(content)
    return _wrap_html(filename, f"<pre>{escaped}</pre>")


def _markdown_to_html(content: str, filename: str) -> str:
    try:
        import markdown
        body = markdown.markdown(content, extensions=["tables", "fenced_code"])
    except ImportError:
        import html as html_lib
        body = f"<pre>{html_lib.escape(content)}</pre>"
    return _wrap_html(filename, body)


def _csv_to_html(content: str, filename: str) -> str:
    import csv, html as html_lib
    rows = list(csv.reader(io.StringIO(content)))
    if not rows:
        return _wrap_html(filename, "<p><em>Empty file</em></p>")

    header = rows[0]
    body_rows = rows[1:]

    th_html = "".join(f"<th>{html_lib.escape(str(c))}</th>" for c in header)
    td_html = ""
    for row in body_rows:
        cells = "".join(f"<td>{html_lib.escape(str(c))}</td>" for c in row)
        td_html += f"<tr>{cells}</tr>"

    table = f"<table><thead><tr>{th_html}</tr></thead><tbody>{td_html}</tbody></table>"
    return _wrap_html(filename, table)


# ── Document converters ───────────────────────────────────────────────────────

def _docx_to_pdf(path: Path, filename: str) -> bytes:
    import html as html_lib
    try:
        from docx import Document
        doc = Document(str(path))
        body = ""
        for para in doc.paragraphs:
            style = (para.style.name or "").lower()
            text = html_lib.escape(para.text) if para.text.strip() else ""
            if "heading 1" in style:
                body += f"<h1>{text}</h1>"
            elif "heading 2" in style:
                body += f"<h2>{text}</h2>"
            elif "heading 3" in style:
                body += f"<h3>{text}</h3>"
            elif text:
                body += f"<p>{text}</p>"
            else:
                body += "<br/>"

        for table in doc.tables:
            rows_html = ""
            for i, row in enumerate(table.rows):
                tag = "th" if i == 0 else "td"
                cells = "".join(
                    f"<{tag}>{html_lib.escape(cell.text)}</{tag}>" for cell in row.cells
                )
                rows_html += f"<tr>{cells}</tr>"
            body += f"<table><tbody>{rows_html}</tbody></table>"

    except Exception as e:
        body = f"<p style='color:red'>Could not parse DOCX: {html_lib.escape(str(e))}</p>"

    return _html_to_pdf(_wrap_html(filename, body))


def _excel_to_pdf(path: Path, filename: str) -> bytes:
    import html as html_lib
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        body = ""
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue
            header = rows[0]
            th_html = "".join(f"<th>{html_lib.escape(str(c) if c is not None else '')}</th>" for c in header)
            td_html = ""
            for row in rows[1:]:
                cells = "".join(f"<td>{html_lib.escape(str(c) if c is not None else '')}</td>" for c in row)
                td_html += f"<tr>{cells}</tr>"
            body += f"<h2>{html_lib.escape(sheet_name)}</h2>"
            body += f"<table><thead><tr>{th_html}</tr></thead><tbody>{td_html}</tbody></table>"
    except ImportError:
        body = "<p style='color:red'>openpyxl not installed.</p>"
    except Exception as e:
        body = f"<p style='color:red'>Could not parse Excel: {html_lib.escape(str(e))}</p>"

    extra = "@page { size: A4 landscape; margin: 1.5cm; }"
    return _html_to_pdf(_wrap_html(filename, body, extra))


def _pptx_to_pdf(path: Path, filename: str) -> bytes:
    import html as html_lib
    try:
        from pptx import Presentation
        prs = Presentation(str(path))
        body = ""
        for i, slide in enumerate(prs.slides, 1):
            texts = [
                html_lib.escape(shape.text.strip())
                for shape in slide.shapes
                if hasattr(shape, "text") and shape.text.strip()
            ]
            content = "<br/>".join(texts) if texts else "<em>Empty slide</em>"
            body += f"""<div style="border:1pt solid #e5e7eb; border-radius:4pt; padding:16pt; margin-bottom:12pt; page-break-after:always">
                <p style="font-size:8pt;color:#9ca3af;margin:0 0 8pt">Slide {i}</p>
                <p style="font-size:13pt">{content}</p>
            </div>"""
    except ImportError:
        body = "<p style='color:red'>python-pptx not installed.</p>"
    except Exception as e:
        body = f"<p style='color:red'>Could not parse PPTX: {html_lib.escape(str(e))}</p>"

    return _html_to_pdf(_wrap_html(filename, body))


def _image_to_pdf(path: Path, filename: str) -> bytes:
    """Embed an image into a PDF page via reportlab."""
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader

    buf = io.BytesIO()
    img_reader = ImageReader(str(path))
    img_w, img_h = img_reader.getSize()

    page_w, page_h = A4
    margin = 40
    avail_w = page_w - 2 * margin
    avail_h = page_h - 2 * margin

    ratio = min(avail_w / img_w, avail_h / img_h)
    draw_w = img_w * ratio
    draw_h = img_h * ratio
    x = margin + (avail_w - draw_w) / 2
    y = margin + (avail_h - draw_h) / 2

    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.drawImage(str(path), x, y, draw_w, draw_h, preserveAspectRatio=True)
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(margin, margin / 2, filename)
    c.save()
    return buf.getvalue()


# ── Error page PDF ────────────────────────────────────────────────────────────

def _error_pdf(filename: str, message: str) -> bytes:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    pw, ph = A4
    c.setFont("Helvetica-Bold", 16)
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.drawCentredString(pw / 2, ph / 2 + 20, filename)
    c.setFont("Helvetica", 12)
    c.setFillColorRGB(0.6, 0.2, 0.2)
    c.drawCentredString(pw / 2, ph / 2 - 10, message)
    c.save()
    return buf.getvalue()


# ── Production LibreOffice Headless PDF Conversion Pipeline ───────────────────

def _find_soffice_binary() -> str:
    """
    Search standard system paths for LibreOffice soffice executable.
    Returns path to binary if found, or empty string.
    """
    import shutil
    import platform
    
    # 1. Check if already on system PATH
    soffice_path = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice_path:
        return soffice_path

    # 2. Check platform specific locations
    system = platform.system()
    if system == "Darwin": # macOS
        candidates = [
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            "/opt/homebrew/bin/soffice",
            "/usr/local/bin/soffice",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
    elif system == "Windows":
        candidates = [
            r"C:\\Program Files\\LibreOffice\\program\\soffice.exe",
            r"C:\\Program Files (x86)\\LibreOffice\\program\\soffice.exe",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
    elif system == "Linux":
        candidates = [
            "/usr/bin/soffice",
            "/usr/bin/libreoffice",
            "/usr/local/bin/soffice",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
                
    return ""


def _convert_via_libreoffice(file_path: Path, ext: str) -> bytes:
    """
    Convert a file (docx, xlsx, pptx, etc.) to PDF using headless LibreOffice.
    """
    import subprocess
    import tempfile
    
    soffice = _find_soffice_binary()
    if not soffice:
        raise RuntimeError("LibreOffice soffice binary not found on this system.")

    with tempfile.TemporaryDirectory() as temp_dir:
        # LibreOffice convert-to command:
        # soffice --headless --convert-to pdf --outdir <temp_dir> <file_path>
        cmd = [
            soffice,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", temp_dir,
            str(file_path)
        ]
        
        # Run conversion subprocess with 30s timeout
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            raise RuntimeError(f"LibreOffice failed with code {res.returncode}: {res.stderr}")
            
        # Locate the output pdf file in temp_dir
        # Input filename is file_path.name, output will be file_path.stem + ".pdf"
        output_pdf_name = file_path.stem + ".pdf"
        output_pdf_path = Path(temp_dir) / output_pdf_name
        
        # Fallback in case of weird naming
        if not output_pdf_path.exists():
            pdfs = list(Path(temp_dir).glob("*.pdf"))
            if pdfs:
                output_pdf_path = pdfs[0]
            else:
                raise FileNotFoundError("LibreOffice did not produce a PDF output file.")
                
        return output_pdf_path.read_bytes()
