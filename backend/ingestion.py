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
    # Generate unique filename to avoid conflicts
    ext = os.path.splitext(filename)[1]
    unique_filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    return file_path

async def process_document(file_path: str) -> dict:
    """
    Process a document using Docling and extract its content.
    Supports: PDF, DOCX, PPTX, HTML, Images, and more.
    """
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import DocumentConverter, PdfFormatOption, WordFormatOption, ImageFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions  # Keep PdfPipe for PDF
        
        # Configure pipeline with OCR and Table Structure enabled
        # We DISABLE the local VLM (picture description) because we will use the external multimodal model (e.g. Kimi) instead.
        # This is much faster and avoids local GPU/MPS issues.
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.do_picture_description = False  # Disable slow local VLM
        pipeline_options.generate_picture_images = True  # Enable raw image extraction
        pipeline_options.images_scale = 2.0 # Improve image resolution
        pipeline_options.ocr_options.force_full_page_ocr = True # Force OCR on all pages to ensure visual text is not skipped
        
        # Slicing high-height PDFs for perfect OCR layout resolution
        temp_pdf_path = None
        ingest_file_path = file_path
        if file_path.lower().endswith(".pdf"):
            try:
                import pypdfium2 as pdfium
                doc = pdfium.PdfDocument(file_path)
                has_tall_page = False
                for page in doc:
                    w, h = page.get_size()
                    if h > 2000.0:
                        has_tall_page = True
                        break
                
                if has_tall_page:
                    print("Detected extremely tall page in PDF. Slicing vertically to optimize OCR extraction...")
                    dest_doc = pdfium.PdfDocument.new()
                    slice_height = 1500.0  # standard segment height in points
                    
                    for page_idx in range(len(doc)):
                        page = doc[page_idx]
                        w, h = page.get_size()
                        if h > 2000.0:
                            num_slices = int(h // slice_height) + (1 if h % slice_height > 0 else 0)
                            dest_doc.import_pages(doc, [page_idx] * num_slices)
                            start_idx = len(dest_doc) - num_slices
                            for s in range(num_slices):
                                new_page = dest_doc[start_idx + s]
                                bottom = max(0.0, h - (s + 1) * slice_height)
                                top = h - s * slice_height
                                new_page.set_mediabox(0, bottom, w, top)
                        else:
                            dest_doc.import_pages(doc, [page_idx])
                    
                    # Generate temporary sliced PDF filename
                    import uuid
                    temp_pdf_path = os.path.join(os.path.dirname(file_path), f"temp_{uuid.uuid4().hex}.pdf")
                    dest_doc.save(temp_pdf_path)
                    dest_doc.close()
                    doc.close()
                    ingest_file_path = temp_pdf_path
                    print(f"Successfully saved vertically sliced PDF: {temp_pdf_path}")
                else:
                    doc.close()
            except Exception as slice_err:
                print(f"Warning: PDF vertical slicing optimization failed: {slice_err}")

        # Configure converter with specific options for PDF, DOCX, and IMAGES
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
                InputFormat.DOCX: WordFormatOption(pipeline_options=pipeline_options),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline_options)
            }
        )
        
        result = converter.convert(ingest_file_path)
        
        # Export content
        markdown_content = result.document.export_to_markdown()

        # Cleanup temporary sliced PDF file if it was created
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            try:
                os.remove(temp_pdf_path)
                print(f"Removed temporary sliced PDF: {temp_pdf_path}")
            except Exception as clean_err:
                print(f"Warning: Failed to remove temporary sliced PDF: {clean_err}")

        # Cleanup OCR spelling mistakes and add image descriptions using AI
        try:
            import llm_gateway
            import json
            import re
            
            # 1. Fast in-memory regex correction for common OCR typos
            typo_fixes = {
                r"\bAfrico\b": "Africa",
                r"\bThe Americos\b": "The Americas",
                r"\bOceonia\b": "Oceania",
                r"\bFamlly\b": "Family",
                r"\bAtlventure\b": "Adventure",
                r"\bPaeked\b": "Packed",
                r"\bLeleurely\b": "Leisurely",
                r"\bCroup\b": "Group",
                r"\bTous\b": "Tours",
            }
            for typo_pattern, correction in typo_fixes.items():
                markdown_content = re.sub(typo_pattern, correction, markdown_content, flags=re.IGNORECASE)
            
            # 2. Extract image descriptions via AI and replace placeholders
            num_placeholders = markdown_content.count("<!-- image -->")
            if num_placeholders > 0:
                system_prompt = (
                    "You are a helpful document layout analyzer.\n"
                    f"The provided text contains exactly {num_placeholders} occurrences of the image placeholder `<!-- image -->`.\n"
                    "Your task is to analyze the surrounding text context for each placeholder and write a brief, descriptive label (e.g. 'SOTC Travel Brand Logo', 'Swiss Alps Hiking Adventure Card', 'Trending Tours Illustration') that explains what that image represents.\n\n"
                    f"You must return a JSON array containing exactly {num_placeholders} strings representing these descriptions in order.\n"
                    "Do not return any introductory text, markdown formatting, or formatting other than a raw JSON array of strings."
                )
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Here is the document content:\n\n{markdown_content}"}
                ]
                
                ai_response = await llm_gateway.call_llm_and_extract(messages, timeout=60.0)
                
                # Strip out any markdown json code blocks (e.g. ```json ... ```)
                ai_response_clean = re.sub(r"```json\s*", "", ai_response, flags=re.IGNORECASE)
                ai_response_clean = re.sub(r"```\s*$", "", ai_response_clean, flags=re.IGNORECASE).strip()
                
                try:
                    descriptions = json.loads(ai_response_clean)
                    if isinstance(descriptions, list) and len(descriptions) == num_placeholders:
                        # Replace occurrences one-by-one in order
                        for desc in descriptions:
                            markdown_content = markdown_content.replace("<!-- image -->", f"(Image: {desc})", 1)
                        print(f"Successfully described {num_placeholders} image placeholders via AI.")
                except Exception as json_err:
                    print(f"Warning: Failed to parse AI image descriptions JSON: {json_err}. Input response: {ai_response}")
        except Exception as ocr_err:
            print(f"Warning: AI post-processing of parsed document failed: {ocr_err}")
        
        # Extract and save images specifically for multimodal analysis
        extracted_images = []
        # Create an images subdirectory if it doesn't exist
        images_dir = os.path.join(os.path.dirname(file_path), "images")
        os.makedirs(images_dir, exist_ok=True)

        # DEBUG: Inspect what attributes the page has
        if len(result.document.pages) > 0:
            first_page = list(result.document.pages.values())[0]
            print(f"DEBUG: Page attributes: {dir(first_page)}")

        # Try document-level pictures first (if available)
        if hasattr(result.document, 'pictures') and result.document.pictures:
             print(f"DEBUG: Found {len(result.document.pictures)} pictures at DOCUMENT level.")
             for i, picture in enumerate(result.document.pictures):
                if hasattr(picture, 'image') and picture.image:
                     print(f"DEBUG: Picture has image of type: {type(picture.image)}")
                     print(f"DEBUG: Image attributes: {dir(picture.image)}")
                     image_filename = f"{os.path.basename(file_path)}_doc_img{i}.png"
                     image_save_path = os.path.join(images_dir, image_filename)
                     try:
                        # Try to save if it's a PIL image
                        if hasattr(picture.image, 'save'):
                            picture.image.save(image_save_path, format="PNG")
                            extracted_images.append(image_save_path)
                            print(f"Extracted and saved document-level image: {image_save_path}")
                        # Fallback for ImageRef or URI
                        elif hasattr(picture.image, 'uri'):
                             pass
                        else:
                             print(f"Warning: Image object has no save method and no URI.")
                     except Exception as e:
                        print(f"Warning: Failed to save doc image: {e}")

        # Custom fallback for DOCX: Extract images directly from the ZIP structure
        # This is 100% reliable even if Docling fails to load them.
        if file_path.lower().endswith(".docx"):
            print("DEBUG: Attempting manual image extraction from DOCX via zipfile...")
            try:
                import zipfile
                with zipfile.ZipFile(file_path, 'r') as z:
                    # List all files in word/media/
                    media_files = [f for f in z.namelist() if f.startswith('word/media/') and f != 'word/media/']
                    print(f"DEBUG: Found {len(media_files)} media files in DOCX.")
                    
                    for media in media_files:
                        # Extract the file
                        # We rename it to be unique
                        original_name = os.path.basename(media)
                        new_name = f"{os.path.basename(file_path)}_{original_name}"
                        target_path = os.path.join(images_dir, new_name)
                        
                        with z.open(media) as source, open(target_path, "wb") as target:
                            target.write(source.read())
                        
                        # Only add supported image formats to the list for AI analysis
                        # AI models (and browsers) typically support PNG, JPEG, GIF, WEBP.
                        # EMF/WMF are vector formats often used in Word but not supported by Vision APIs.
                        ext = os.path.splitext(original_name)[1].lower()
                        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                            extracted_images.append(target_path)
                            print(f"Extracted and saved DOCX image (manual): {target_path}")
                        else:
                            print(f"Warning: Skipped unsupported image format for AI: {target_path} ({ext})")
            except Exception as zip_err:
                print(f"Warning: Manual DOCX extraction failed: {zip_err}")

        # Iterate through pages and pictures to save them (Standard Docling path)
        print(f"DEBUG: Document has {len(result.document.pages)} pages.")
        for page_no, page in result.document.pages.items():
            if hasattr(page, 'pictures') and page.pictures:
                print(f"DEBUG: Page {page_no} has {len(page.pictures)} pictures.")
                for i, picture in enumerate(page.pictures):
                    # Check if the picture has an image attached (it should if generate_picture_images=True)
                    if hasattr(picture, 'image') and picture.image:
                        image_filename = f"{os.path.basename(file_path)}_p{page_no}_img{i}.png"
                        image_save_path = os.path.join(images_dir, image_filename)
                        try:
                            # Save the PIL image
                            picture.image.save(image_save_path, format="PNG")
                            extracted_images.append(image_save_path)
                            print(f"Extracted and saved image: {image_save_path}")
                        except Exception as img_err:
                            print(f"Warning: Failed to save extracted image: {img_err}")
                    else:
                        print(f"DEBUG: Picture {i} on page {page_no} has NO image data (picture.image is None).")
            else:
                print(f"DEBUG: Page {page_no} has no pictures attribute or it is empty.")

        # Get document metadata
        doc = result.document
        html_content = result.document.export_to_html()
        if not html_content:
             print("DEBUG: HTML Content is EMPTY!")
        else:
             print(f"DEBUG: Generated HTML content length: {len(html_content)}")
             print(f"DEBUG: HTML Start: {html_content[:100]}")
        
        # Determine number of pages
        num_pages = 0
        if hasattr(doc, 'pages'):
            num_pages = len(doc.pages)
        elif hasattr(doc, 'num_pages'):
            np = getattr(doc, 'num_pages')
            num_pages = np() if callable(np) else np

        return {
            "status": "success",
            "markdown": markdown_content,
            "html": html_content,
            "num_pages": num_pages,
            "file_path": file_path,
            "images": extracted_images  # specific list of image paths for the AI
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "file_path": file_path,
            "images": []
        }


def cleanup_file(file_path: str) -> bool:
    """Remove a processed file."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception:
        return False
