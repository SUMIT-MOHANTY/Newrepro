import os
import uuid
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True  # Allow loading truncated images to fix Pillow errors
from typing import Optional

# Configure upload directory
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_uploaded_file(file_content: bytes, filename: str) -> str:
    """Save uploaded file and return the path."""
    ext = os.path.splitext(filename)[1]
    unique_filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    return file_path


async def process_document_with_ai(file_path: str) -> dict:
    """
    Process a document directly using Multimodal AI Vision models.
    Extracts text, tables, wireframes, flowcharts, and architecture diagrams directly into Markdown context.
    """
    import base64
    import zipfile
    import re
    from app.integrations.llm import llm_gateway

    images_dir = os.path.join(os.path.dirname(file_path), "images")
    os.makedirs(images_dir, exist_ok=True)

    ext = os.path.splitext(file_path)[1].lower()
    file_basename = os.path.basename(file_path)

    extracted_images = []
    num_pages = 1

    # ----------------------------------------------------
    # 1. Standalone Images (.png, .jpg, .jpeg, .webp, .bmp, .tiff, .gif)
    # ----------------------------------------------------
    if ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif"]:
        saved_img_name = f"{uuid.uuid4().hex}_{file_basename}"
        saved_img_path = os.path.join(images_dir, saved_img_name)
        try:
            with open(file_path, "rb") as f_in, open(saved_img_path, "wb") as f_out:
                f_out.write(f_in.read())
            extracted_images.append(saved_img_path)
        except Exception as e:
            print(f"Warning: Could not copy image to images_dir: {e}")
            saved_img_path = file_path
            extracted_images.append(file_path)

        # Read Base64 for Vision API
        with open(saved_img_path, "rb") as img_f:
            b64_data = base64.b64encode(img_f.read()).decode("utf-8")

        prompt = (
            "You are an expert technical document and visual layout analyst.\n"
            "Analyze the provided image (which may be a software requirement document screenshot, UI wireframe, architecture diagram, flowchart, or data table).\n"
            "Extract all text, table structures, user workflow steps, component descriptions, and technical specifications.\n"
            "Output the content as clean, comprehensive, semantically structured Markdown suitable for software requirement analysis."
        )

        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Document Image: {file_basename}\n\nPlease analyze and extract full requirements Markdown:"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_data}"}}
                ]
            }
        ]

        try:
            ai_markdown = await llm_gateway.call_llm_and_extract(messages, timeout=60.0, purpose="Document Ingestion & OCR")
            if not ai_markdown or not ai_markdown.strip():
                ai_markdown = f"# Image Document: {file_basename}\n\n(No textual content recognized in image)"
        except Exception as ai_err:
            print(f"Warning: AI vision extraction failed for image: {ai_err}")
            ai_markdown = f"# Image Document: {file_basename}\n\n(Image requirement document attached for multimodal analysis)"

        return {
            "status": "success",
            "markdown": ai_markdown,
            "html": "",
            "num_pages": 1,
            "file_path": file_path,
            "images": extracted_images
        }

    # ----------------------------------------------------
    # 2. PDF Documents (.pdf)
    # ----------------------------------------------------
    elif ext == ".pdf":
        page_images = []
        raw_pdf_text = ""
        num_pages = 1

        try:
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            num_pages = len(doc)
            
            for page_idx in range(min(num_pages, 10)):  # Process up to 10 pages for multimodal vision
                page = doc[page_idx]
                raw_pdf_text += page.get_text() + "\n\n"
                
                # Render page to high-res image
                pix = page.get_pixmap(dpi=150)
                img_name = f"{uuid.uuid4().hex}_p{page_idx+1}.png"
                img_path = os.path.join(images_dir, img_name)
                pix.save(img_path)
                page_images.append(img_path)
                extracted_images.append(img_path)
            doc.close()
        except Exception as pdf_err:
            print(f"Warning: PyMuPDF extraction failed: {pdf_err}")

        content_blocks = [
            {
                "type": "text",
                "text": f"Document: {file_basename}\nTotal Pages: {num_pages}\n\nExtracted Raw Text:\n{raw_pdf_text[:10000]}\n\nAttached Page Images for Visual Analysis:"
            }
        ]

        for img_path in page_images[:5]:  # Send up to 5 visual pages
            try:
                with open(img_path, "rb") as img_f:
                    b64 = base64.b64encode(img_f.read()).decode("utf-8")
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}
                    })
            except Exception as b64_err:
                print(f"Warning: Failed to encode PDF page image: {b64_err}")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert software requirement and technical specification document analyzer.\n"
                    "Extract and organize all requirements, functional specifications, data models, tables, and visual diagram descriptions into clean Markdown."
                )
            },
            {"role": "user", "content": content_blocks}
        ]

        try:
            ai_markdown = await llm_gateway.call_llm_and_extract(messages, timeout=90.0, purpose="Document Ingestion & OCR")
        except Exception as ai_err:
            print(f"Warning: AI PDF extraction failed: {ai_err}")
            ai_markdown = raw_pdf_text or f"# Document: {file_basename}\n\n(Extracted PDF pages attached as images)"

        return {
            "status": "success",
            "markdown": ai_markdown,
            "html": "",
            "num_pages": num_pages,
            "file_path": file_path,
            "images": extracted_images
        }

    # ----------------------------------------------------
    # 3. Word Documents (.docx)
    # ----------------------------------------------------
    elif ext == ".docx":
        # Extract embedded images directly from Word ZIP structure
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                media_files = [f for f in z.namelist() if f.startswith('word/media/') and f != 'word/media/']
                for media in media_files:
                    orig_name = os.path.basename(media)
                    target_name = f"{uuid.uuid4().hex}_{orig_name}"
                    target_path = os.path.join(images_dir, target_name)
                    with z.open(media) as source, open(target_path, "wb") as target:
                        target.write(source.read())
                    media_ext = os.path.splitext(orig_name)[1].lower()
                    if media_ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                        extracted_images.append(target_path)
        except Exception as zip_err:
            print(f"Warning: Failed to extract embedded images from DOCX: {zip_err}")

        # Extract text & tables
        raw_docx_text = ""
        try:
            import docx
            doc = docx.Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            
            table_texts = []
            for t in doc.tables:
                row_strings = []
                for row in t.rows:
                    row_data = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                    row_strings.append(" | ".join(row_data))
                if row_strings:
                    table_texts.append("\n".join(row_strings))
            
            raw_docx_text = "\n\n".join(paragraphs)
            if table_texts:
                raw_docx_text += "\n\n--- TABLES ---\n\n" + "\n\n".join(table_texts)
        except Exception as docx_err:
            print(f"Warning: python-docx text extraction failed: {docx_err}. Falling back to zipfile document.xml")
            try:
                with zipfile.ZipFile(file_path, 'r') as z:
                    xml_content = z.read('word/document.xml').decode('utf-8', errors='ignore')
                    raw_docx_text = re.sub(r'<[^>]+>', ' ', xml_content)
                    raw_docx_text = re.sub(r'\s+', ' ', raw_docx_text).strip()
            except Exception as xml_err:
                print(f"Warning: DOCX XML extraction failed: {xml_err}")

        content_blocks = [
            {
                "type": "text",
                "text": f"Document: {file_basename}\n\nDOCX Content:\n{raw_docx_text[:15000]}"
            }
        ]

        # Attach extracted embedded images if available
        for img_path in extracted_images[:5]:
            try:
                with open(img_path, "rb") as img_f:
                    b64 = base64.b64encode(img_f.read()).decode("utf-8")
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}
                    })
            except Exception as b64_err:
                print(f"Warning: Failed to encode DOCX image for AI: {b64_err}")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a technical document analyst.\n"
                    "Convert the provided DOCX content and embedded diagrams into structured Markdown with clear headings, bullet points, and table structures."
                )
            },
            {"role": "user", "content": content_blocks}
        ]

        try:
            ai_markdown = await llm_gateway.call_llm_and_extract(messages, timeout=60.0, purpose="Document Ingestion & OCR")
        except Exception as ai_err:
            print(f"Warning: AI DOCX structuring failed: {ai_err}")
            ai_markdown = raw_docx_text or f"# Document: {file_basename}\n\n(Extracted DOCX content)"

        return {
            "status": "success",
            "markdown": ai_markdown,
            "html": "",
            "num_pages": 1,
            "file_path": file_path,
            "images": extracted_images
        }

    # ----------------------------------------------------
    # 4. Text / Markdown / HTML / Other Files
    # ----------------------------------------------------
    else:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as read_err:
            content = f"Error reading file {file_basename}: {read_err}"

        messages = [
            {
                "role": "system",
                "content": "Structure and format the following document text into clean, semantically organized Markdown for requirement analysis."
            },
            {"role": "user", "content": f"Document: {file_basename}\n\nContent:\n{content[:15000]}"}
        ]

        try:
            ai_markdown = await llm_gateway.call_llm_and_extract(messages, timeout=30.0, purpose="Document Ingestion & OCR")
        except Exception:
            ai_markdown = content

        return {
            "status": "success",
            "markdown": ai_markdown,
            "html": "",
            "num_pages": 1,
            "file_path": file_path,
            "images": []
        }


async def process_document(file_path: str) -> dict:
    """
    Process a document using Direct AI Multimodal Extraction.
    Supports: PDF, DOCX, PPTX, HTML, Images, and more.
    """
    print(f"Using Direct AI Multimodal Vision extraction for: {file_path}")
    return await process_document_with_ai(file_path)


def cleanup_file(file_path: str) -> bool:
    """Remove a processed file."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception:
        return False
