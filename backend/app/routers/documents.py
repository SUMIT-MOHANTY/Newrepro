"""
DSuite BRD Analyzer - Domain Router: Documents Ingestion & Sharing
Auto-extracted enterprise clean architecture domain router.
"""

import asyncio
import base64
import concurrent.futures
import hashlib
import html as html_lib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import httpx
import requests
from fastapi import (
    APIRouter, Depends, File, Form, Header, HTTPException, Query,
    Request, Response, UploadFile, WebSocket, WebSocketDisconnect, status
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from app.core import security as auth
import models
import schemas
from app.core.config import settings
from app.core.database import SessionLocal, engine, get_db

import ingestion
from app.core.middleware import is_major_action
from app.routers.helpers import _normalized_text, _org_user_ids_subquery
from app.services.ai import ai_service, ai_service_chunked


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents & Sharing"])

# --- Extracted Block (Lines 762-928) ---
class URLIngestRequest(BaseModel):
    url: str = Field(..., description="Public website URL to fetch")


class _RequirementPageParser(HTMLParser):
    """
    Lightweight HTML parser for extracting readable requirement-like content
    without external dependencies.
    """

    _HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    _BLOCK_TAGS = {"p", "li", "section", "article", "div", "blockquote", "td", "th"}
    _IGNORE_TAGS = {"script", "style", "noscript", "svg", "canvas", "iframe"}

    def __init__(self) -> None:
        super().__init__()
        self.in_ignored_depth = 0
        self.in_title = False
        self.current_tag: Optional[str] = None
        self.current_text_parts: List[str] = []
        self.title_parts: List[str] = []
        self.headings: List[str] = []
        self.paragraphs: List[str] = []
        self.list_items: List[str] = []

    def handle_starttag(self, tag: str, attrs):
        tag_l = tag.lower()
        if tag_l in self._IGNORE_TAGS:
            self.in_ignored_depth += 1
            return
        if self.in_ignored_depth > 0:
            return
        if tag_l == "title":
            self.in_title = True
            return
        if tag_l in self._HEADING_TAGS or tag_l in self._BLOCK_TAGS:
            self.current_tag = tag_l
            self.current_text_parts = []

    def handle_endtag(self, tag: str):
        tag_l = tag.lower()
        if tag_l in self._IGNORE_TAGS and self.in_ignored_depth > 0:
            self.in_ignored_depth -= 1
            return
        if self.in_ignored_depth > 0:
            return
        if tag_l == "title":
            self.in_title = False
            return
        if self.current_tag == tag_l:
            text = " ".join(self.current_text_parts).strip()
            text = re.sub(r"\s+", " ", text)
            if text:
                if tag_l in self._HEADING_TAGS:
                    self.headings.append(text)
                elif tag_l == "li":
                    self.list_items.append(text)
                else:
                    self.paragraphs.append(text)
            self.current_tag = None
            self.current_text_parts = []

    def handle_data(self, data: str):
        if self.in_ignored_depth > 0:
            return
        clean = re.sub(r"\s+", " ", data or "").strip()
        if not clean:
            return
        if self.in_title:
            self.title_parts.append(clean)
        if self.current_tag:
            self.current_text_parts.append(clean)

    def to_requirement_markdown(self, source_url: str, max_lines: int = None) -> Dict[str, Any]:
        page_title = re.sub(r"\s+", " ", " ".join(self.title_parts).strip())
        heading_lines = [f"## {h}" for h in self.headings]
        paragraph_lines = self.paragraphs
        bullet_lines = [f"- {item}" for item in self.list_items]

        lines: List[str] = []
        if page_title:
            lines.append(f"# Extracted Requirements - {page_title}")
        else:
            lines.append("# Extracted Requirements")
        lines.append(f"Source URL: {source_url}")
        lines.append("")
        lines.append("The following requirements were generated from webpage content.")
        lines.append("Review and edit before final analysis.")
        lines.append("")
        lines.append("## Candidate Requirements")

        if not heading_lines and not paragraph_lines and not bullet_lines:
            lines.append("- No readable requirement content was detected on this page.")
        else:
            lines.extend(heading_lines)
            if heading_lines and (paragraph_lines or bullet_lines):
                lines.append("")
            lines.extend(bullet_lines)
            if paragraph_lines:
                lines.append("")
                lines.extend(paragraph_lines)

        # Only truncate if max_lines is explicitly set
        if max_lines is not None and len(lines) > max_lines:
            lines = lines[:max_lines]
            lines.append("")
            lines.append("... (truncated)")

        markdown = "\n".join(lines).strip()
        summary = {
            "title": page_title or None,
            "headings_found": len(self.headings),
            "paragraphs_found": len(self.paragraphs),
            "list_items_found": len(self.list_items),
        }
        return {"markdown": markdown, "summary": summary}


def _normalize_and_validate_public_url(raw_url: str) -> str:
    candidate = str(raw_url or "").strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="URL is required.")

    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only http/https URLs are allowed.")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL hostname.")

    blocked_hostnames = {
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "host.docker.internal",
        "metadata.google.internal",
    }
    if hostname in blocked_hostnames or hostname.endswith(".local"):
        raise HTTPException(status_code=400, detail="Local/internal URLs are not allowed.")

    try:
        host_ip = ipaddress.ip_address(hostname)
        if host_ip.is_loopback or host_ip.is_private or host_ip.is_link_local or host_ip.is_multicast or host_ip.is_reserved:
            raise HTTPException(status_code=400, detail="Private or local network URLs are not allowed.")
    except ValueError:
        # Hostname is a domain name, continue.
        pass

    # Ignore fragments as they are browser-only and not needed for server fetch.
    normalized = parsed._replace(fragment="").geturl()
    return normalized


def _strip_html_to_text(value: str, max_chars: int = 0) -> str:
    text = str(value or "")
    text = re.sub(r"<!--[\s\S]*?-->", " ", text)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars]
    return text


# --- Extracted Block (Lines 6109-6647) ---
@router.post("/documents/upload")
async def upload_document(
    files: List[UploadFile] = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    revision_version: Optional[int] = Form(None),
):
    """
    Upload and process multiple documents using Direct AI Extraction.
    Supports: PDF, DOCX, PPTX, HTML, Images, and more.
    Requires authentication.
    """
    allowed_extensions = {".pdf", ".docx", ".pptx", ".html", ".htm", ".png", ".jpg", ".jpeg", ".txt", ".md"}
    
    MAX_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
    total_size = 0
    
    processed_files = []
    processed_file_paths = []
    combined_markdown = ""
    combined_html = ""
    total_pages = 0
    all_images = []

    for file in files:
        # Validate file type
        file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
        
        if file_ext not in allowed_extensions:
            # Skip invalid files or raise error? For now, we'll raise error to be safe
            continue 
            # Alternatively: raise HTTPException(status_code=400, detail=f"File {file.filename} not supported.")
        
        # Read and save file
        content = await file.read()
        total_size += len(content)
        if total_size > MAX_SIZE_BYTES:
            raise HTTPException(status_code=400, detail="Total file size exceeds 100MB limit.")

        # Handle plain text and markdown files directly
        if file_ext in {".txt", ".md"}:
            try:
                text_content = content.decode("utf-8", errors="replace").strip()
            except Exception:
                text_content = content.decode("latin-1", errors="replace").strip()

            if text_content:
                file_markdown = f"\n\n--- DOCUMENT: {file.filename} ---\n\n{text_content}"
                combined_markdown += file_markdown
                combined_html += f"<div class='document-separator'><h2>Document: {file.filename}</h2></div><pre style='white-space: pre-wrap; font-family: inherit;'>{text_content}</pre>"
                total_pages += 1
                
                # Save plain text/markdown to disk for viewing/download as well
                file_path = ingestion.save_uploaded_file(content, file.filename)
                processed_file_paths.append(os.path.basename(file_path))
                processed_files.append(file.filename)
            else:
                print(f"Warning: Text file {file.filename} was empty.")
            continue

        file_path = ingestion.save_uploaded_file(content, file.filename)
        
        # Process with Direct AI Ingestion
        result = await ingestion.process_document(file_path)
        
        # Keep the file on disk! Do not cleanup.
        # ingestion.cleanup_file(file_path)
        
        if result["status"] == "error":
            print(f"Error processing {file.filename}: {result['error']}")
            # Cleanup only failed files to prevent orphan corrupted files
            ingestion.cleanup_file(file_path)
            continue

        # Aggregate results
        file_markdown = f"\n\n--- DOCUMENT: {file.filename} ---\n\n{result['markdown']}"
        combined_markdown += file_markdown
        
        if result.get("html"):
            combined_html += f"<div class='document-separator'><h2>Document: {file.filename}</h2></div>{result['html']}"
        
        total_pages += result.get("num_pages", 0) or 0
        all_images.extend(result.get("images", []))
        
        processed_file_paths.append(os.path.basename(file_path))
        processed_files.append(file.filename)

    if not processed_files:
        raise HTTPException(status_code=400, detail="No valid files processed.")

    response = {
        "filename": ", ".join(processed_files), # Combined filename for display
        "filenames": processed_files,
        "user": current_user.email,
        "markdown": combined_markdown,
        "html": combined_html if combined_html else None,
        "num_pages": total_pages,
        "images": all_images,
        "file_path": ",".join(processed_file_paths),
        "revision_version": revision_version
    }
    
    print(f"DEBUG: API Response keys: {list(response.keys())}")
    return response


@router.get("/documents/download/{filename}")
async def download_document_file(
    filename: str,
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """
    Download or view the original uploaded document by its unique filename.
    Requires token either in Authorization header or token query parameter.
    """
    import os
    from jose import jwt
    from app.core.config import settings
    from fastapi.responses import FileResponse
    
    # 1. Resolve token
    resolved_token = None
    if authorization and authorization.startswith("Bearer "):
        resolved_token = authorization.split(" ")[1]
    elif token:
        resolved_token = token

    if not resolved_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # 2. Verify token
    try:
        payload = jwt.decode(resolved_token, settings.secret_key, algorithms=[settings.algorithm])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # 3. Serve file with smart resolution across uploads and uploads/images
    base_dir = os.path.dirname(os.path.abspath(__file__))
    uploads_dir = os.path.normpath(os.path.join(base_dir, "uploads"))
    images_dir = os.path.normpath(os.path.join(uploads_dir, "images"))

    clean_filename = filename.replace("---", "").replace("DOCUMENT:", "").strip()

    # List candidate directories to check
    check_dirs = [uploads_dir]
    if os.path.exists(images_dir):
        check_dirs.append(images_dir)

    # Step 1: Direct match check on disk
    for d in check_dirs:
        cand = os.path.normpath(os.path.join(d, clean_filename))
        if os.path.exists(cand) and os.path.isfile(cand):
            return FileResponse(cand)

    # Step 2: Database lookup candidate check by file_path or filename
    doc_match = None
    try:
        from app.core.database import SessionLocal
        import models
        from sqlalchemy import or_
        db_session = SessionLocal()
        try:
            doc_match = db_session.query(models.Document).filter(
                or_(
                    models.Document.file_path.contains(clean_filename),
                    models.Document.filename == clean_filename,
                    models.Document.full_content.contains(clean_filename),
                    models.Document.screening_inputs.contains(clean_filename)
                )
            ).order_by(models.Document.upload_date.desc()).first()

            if doc_match and doc_match.file_path:
                for candidate in doc_match.file_path.split(","):
                    c_name = candidate.strip().replace("---", "").replace("DOCUMENT:", "").strip()
                    for d in check_dirs:
                        c_path = os.path.normpath(os.path.join(d, c_name))
                        if os.path.exists(c_path) and os.path.isfile(c_path):
                            return FileResponse(c_path)
        finally:
            db_session.close()
    except Exception as e:
        print(f"Warning: DB lookup failed during file download resolution: {e}")

    # Step 3: Partial / Prefix filename match in uploads & images
    base_search = os.path.splitext(clean_filename)[0].lower()
    if base_search:
        for d in check_dirs:
            if os.path.exists(d):
                for f in os.listdir(d):
                    full_f = os.path.join(d, f)
                    if os.path.isfile(full_f) and (base_search in f.lower() or f.lower().endswith(clean_filename.lower())):
                        return FileResponse(full_f)

    # Step 4: Timestamp-assisted resolution for matched database document
    if doc_match and doc_match.upload_date:
        ext = os.path.splitext(clean_filename)[1].lower() or ".png"
        all_candidates = []
        for d in check_dirs:
            if os.path.exists(d):
                for f in os.listdir(d):
                    if f.lower().endswith(ext):
                        full_f = os.path.join(d, f)
                        if os.path.isfile(full_f):
                            all_candidates.append((full_f, os.path.getmtime(full_f)))
        if all_candidates:
            from datetime import timezone
            doc_ts = doc_match.upload_date.replace(tzinfo=timezone.utc).timestamp()
            best_candidate = min(all_candidates, key=lambda x: abs(x[1] - doc_ts))[0]
            return FileResponse(best_candidate)

    # Step 5: Fallback SVG preview card
    from fastapi.responses import Response
    escaped_title = clean_filename.replace("<", "&lt;").replace(">", "&gt;")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="600" height="260" viewBox="0 0 600 260">
  <rect width="600" height="260" fill="#f8fafc" rx="16" ry="16"/>
  <rect x="2" y="2" width="596" height="256" fill="none" stroke="#e2e8f0" stroke-width="2" rx="14" ry="14"/>
  <circle cx="300" cy="95" r="32" fill="#eff6ff"/>
  <path d="M288 83 h24 v24 h-24 z" fill="none" stroke="#2563eb" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M294 91 h12 M294 97 h12 M294 103 h8" stroke="#3b82f6" stroke-width="2" stroke-linecap="round"/>
  <text x="300" y="160" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="15" font-weight="700" fill="#1e293b" text-anchor="middle">{escaped_title}</text>
  <text x="300" y="185" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="12" font-weight="500" fill="#64748b" text-anchor="middle">Requirement Document Specification</text>
</svg>"""
    return Response(content=svg.encode("utf-8"), media_type="image/svg+xml")


@router.post("/documents/extract-from-url")
async def extract_document_from_url(
    payload: URLIngestRequest,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Fetch website content and convert it into requirement-style markdown.
    """
    source_url = _normalize_and_validate_public_url(payload.url)

    headers = {
        "User-Agent": "BRD-Analyzer/1.0 (+Requirement-Extraction)",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(source_url, headers=headers)
            resp.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timed out while fetching the URL.")
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else 502
        if code == 404:
            detail = "Website page not found (404). Check the URL and try again."
        elif code in (401, 403):
            detail = "Website denied access to this URL."
        else:
            detail = f"Failed to fetch URL content (HTTP {code})."
        raise HTTPException(status_code=code, detail=detail)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"URL fetch failed: {exc}")

    content_type = str(resp.headers.get("content-type", "")).lower()
    raw_text = resp.text or ""
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Fetched page is empty.")

    parser = _RequirementPageParser()
    parser.feed(raw_text)
    parser.close()
    parsed = parser.to_requirement_markdown(str(resp.url))

    markdown = parsed["markdown"]
    if not markdown.strip():
        plain_text = _strip_html_to_text(raw_text)
        markdown = (
            f"# Extracted Requirements\n"
            f"Source URL: {str(resp.url)}\n\n"
            f"## Candidate Requirements\n"
            f"{plain_text[:120000] if plain_text else 'No readable content found.'}"
        )

    filename_source = (parser.title_parts[0] if parser.title_parts else "") or urlparse(str(resp.url)).hostname or "Website_URL"
    safe_label = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename_source).strip("_") or "Website_URL"
    generated_filename = f"URL_{safe_label}_{datetime.utcnow().strftime('%Y-%m-%d')}"

    return {
        "filename": generated_filename,
        "url": str(resp.url),
        "content_type": content_type or None,
        "markdown": markdown,
        "summary": parsed.get("summary") or {},
        "user": current_user.email,
    }

def _auto_populate_document_file_metadata(payload: dict) -> dict:
    """Helper to auto-extract and populate file_path and screening_inputs if missing."""
    import re
    full_content = payload.get("full_content") or payload.get("content_preview") or ""
    filename = payload.get("filename") or ""
    file_path = payload.get("file_path") or ""
    
    screening_inputs = payload.get("screening_inputs")
    if not isinstance(screening_inputs, dict):
        screening_inputs = {}

    uploaded_files = screening_inputs.get("uploaded_files")
    if not isinstance(uploaded_files, list):
        uploaded_files = []

    # Extract filenames from full_content (e.g. --- Screenshot 2026-07-23 180448.png ---)
    matches = re.findall(r'---\s*(?:DOCUMENT:\s*)?([^\n\r]+?\.(?:png|jpg|jpeg|gif|webp|pdf|docx|pptx|html|txt|md))\s*---', full_content, re.IGNORECASE)
    extracted = []
    if matches:
        # Use the last file match which corresponds to the current revision's upload
        last_file = matches[-1].strip()
        if last_file:
            extracted.append(last_file)

    # Check filename if it looks like an uploaded file
    if not extracted and filename:
        fn_ext = filename.split('.')[-1].lower()
        if fn_ext in ['png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'docx', 'pptx', 'html', 'txt', 'md']:
            extracted.append(filename)

    if extracted:
        if not file_path:
            payload["file_path"] = ",".join(extracted)
        if not uploaded_files:
            screening_inputs["uploaded_files"] = extracted
            payload["screening_inputs"] = screening_inputs

    return payload


# --- History Endpoints ---

@router.get("/history", response_model=List[schemas.Document])
def get_user_history(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 20,
    project_token: Optional[str] = None,
):
    """
    Retrieve user's document history.
    If project_token is provided, filters documents by that project.
    Otherwise returns all documents for the organization.
    """
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))
    
    if not organization_name:
        query = db.query(models.Document).filter(models.Document.owner_id == current_user.id)
    else:
        org_user_ids = _org_user_ids_subquery(db, organization_name)
        query = db.query(models.Document).filter(models.Document.owner_id.in_(org_user_ids))
    
    if project_token:
        # Filter by project_token column (new) or fallback to matching within analysis_result JSON
        query = query.filter(
            or_(
                models.Document.project_token == project_token,
                models.Document.analysis_result.contains(project_token),
            )
        )
    
    docs = (
        query
        .order_by(models.Document.upload_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    # Auto-repair any documents missing file_path or screening_inputs.uploaded_files
    has_repaired = False
    for d in docs:
        if not d.file_path or not (d.screening_inputs or {}).get("uploaded_files"):
            payload = {
                "full_content": d.full_content,
                "content_preview": d.content_preview,
                "filename": d.filename,
                "file_path": d.file_path,
                "screening_inputs": d.screening_inputs or {}
            }
            updated = _auto_populate_document_file_metadata(payload)
            if updated.get("file_path") and not d.file_path:
                d.file_path = updated["file_path"]
                has_repaired = True
            if updated.get("screening_inputs") and not (d.screening_inputs or {}).get("uploaded_files"):
                d.screening_inputs = updated["screening_inputs"]
                has_repaired = True

    if has_repaired:
        try:
            db.commit()
        except Exception:
            db.rollback()

    # Auto-expand combined legacy document rows into individual revision records if project_token is specified
    if project_token and docs:
        import re
        expanded_docs = []
        seen_revisions = set()

        for d in docs:
            full_content = d.full_content or ""
            matches = list(re.finditer(r'---\s*(?:NEW\s+)?REVISION\s+(\d+)\s*-\s*([^\n]+)\s*---', full_content, re.IGNORECASE))

            if len(matches) > 1:
                for i, match in enumerate(matches):
                    rev_num = int(match.group(1))
                    if rev_num in seen_revisions:
                        continue
                    seen_revisions.add(rev_num)

                    rev_title = match.group(2).strip().replace("(Combined)", "").strip()
                    start_idx = match.start()
                    end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(full_content)
                    sec_content = full_content[start_idx:end_idx]

                    file_matches = re.findall(r'---\s*(?:DOCUMENT:\s*)?([^\n\r]+?\.(?:png|jpg|jpeg|gif|webp|pdf|docx|pptx|html|txt|md))\s*---', sec_content, re.IGNORECASE)
                    sec_files = []
                    if file_matches:
                        seen_f = set()
                        for f_m in file_matches:
                            f_clean = f_m.strip()
                            if f_clean not in seen_f:
                                seen_f.add(f_clean)
                                sec_files.append(f_clean)

                    sec_screening = {
                        "uploaded_files": sec_files if sec_files else [rev_title],
                        "manual_text": "",
                        "linked_documents": [],
                        "url_content": "",
                        "repository_context": None,
                        "skills_files": []
                    }

                    manual_match = re.search(r'---\s*MANUAL TEXT INPUT\s*---\s*([^\n\r]+)', sec_content, re.IGNORECASE)
                    if manual_match:
                        sec_screening["manual_text"] = manual_match.group(1).strip()

                    expanded_docs.append(models.Document(
                        id=d.id * 100 + rev_num,
                        filename=rev_title,
                        upload_date=getattr(d, "upload_date", None) or datetime.utcnow(),
                        content_preview=sec_content[:200],
                        full_content=sec_content,
                        analysis_result=d.analysis_result,
                        file_path=",".join(sec_files) if sec_files else d.file_path,
                        screening_inputs=sec_screening,
                        project_token=project_token,
                        revision_version=rev_num,
                        owner_id=d.owner_id
                    ))
            else:
                rev_num = d.revision_version or 1
                if rev_num not in seen_revisions:
                    seen_revisions.add(rev_num)
                    expanded_docs.append(d)

        if expanded_docs:
            expanded_docs.sort(key=lambda x: (x.revision_version or 0, getattr(x, "id", 0)))
            docs = expanded_docs

    return docs

@router.post("/history", response_model=schemas.Document)
def save_document_history(
    document: schemas.DocumentCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Save an analysis result to history."""
    payload = document.dict()
    payload = _auto_populate_document_file_metadata(payload)

    # Auto-populate project_token from analysis_result JSON if not provided
    if not payload.get("project_token") and payload.get("analysis_result"):
        try:
            parsed = json.loads(payload["analysis_result"])
            if isinstance(parsed, dict):
                token = parsed.get("project_token") or (parsed.get("projectMeta") or {}).get("project_token")
                if token:
                    payload["project_token"] = token
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    db_doc = models.Document(**payload, owner_id=current_user.id)
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc

@router.put("/history/{document_id}", response_model=schemas.Document)
def update_document_history(
    document_id: int,
    document: schemas.DocumentCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing document history entry for the current user."""
    db_doc = db.query(models.Document).filter(
        models.Document.id == document_id,
        models.Document.owner_id == current_user.id,
    ).first()
    if not db_doc:
        raise HTTPException(status_code=404, detail="Document not found")

    payload = document.dict()
    payload = _auto_populate_document_file_metadata(payload)

    db_doc.filename = payload["filename"]
    db_doc.content_preview = payload.get("content_preview")
    db_doc.full_content = payload.get("full_content")
    db_doc.analysis_result = payload.get("analysis_result")
    db_doc.file_path = payload.get("file_path")
    if payload.get("screening_inputs"):
        db_doc.screening_inputs = payload.get("screening_inputs")
    if "screening_inputs" in payload:
        db_doc.screening_inputs = payload.get("screening_inputs")
    # Auto-populate project_token from analysis_result JSON if not provided in payload
    project_token_val = payload.get("project_token")
    if not project_token_val and payload.get("analysis_result"):
        try:
            parsed = json.loads(payload["analysis_result"])
            if isinstance(parsed, dict):
                project_token_val = parsed.get("project_token") or (parsed.get("projectMeta") or {}).get("project_token")
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    if project_token_val:
        db_doc.project_token = project_token_val

    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc
# --- Share Document Endpoints ---

# --- Extracted Block (Lines 6648-7763) ---
@router.post("/api/share-doc")
async def share_doc_documents(
    files: List[UploadFile] = File([]),
    config: str = Form(...),
    recipients: str = Form(...),
    selected_files: str = Form("[]"),
    project_token: str = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    print(f"DEBUG: share_doc_documents called with project_token={project_token}")
    """
    Share Document documents with external users via secure links.
    Uploads files, creates a share link, and sends email notifications.
    """
    # Parse configuration and recipients
    print(f"DEBUG: share_doc_documents params: config={config[:100]}..., recipients={recipients[:100]}..., selected_files={selected_files}")
    import json
    import hashlib
    from datetime import timedelta
    try:
        share_config = json.loads(config)
        recipient_list = json.loads(recipients)
        selected_file_ids = json.loads(selected_files)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid configuration, recipients, or selected_files format")
    
    # Validate share project if provided
    share_project_id = None
    if project_token:
        share_project = db.query(models.ShareProject).filter(
            models.ShareProject.project_token == project_token,
            models.ShareProject.owner_id == current_user.id
        ).first()
        
        if not share_project:
            raise HTTPException(status_code=404, detail="Share project not found")
        
        share_project_id = share_project.id
        
        # Expire old documents for this project to ensure only the latest is active
        try:
            db.query(models.SharedDocument).filter(
                models.SharedDocument.share_project_id == share_project_id
            ).update({"expires_at": datetime.utcnow() - timedelta(seconds=1)})
            db.flush()
        except Exception as e:
            print(f"Warning: Failed to expire old documents: {e}")
    
    # Create upload directory inside the project directory, as an isolated folder
    base_upload_dir = Path("shared_documents")
    base_upload_dir.mkdir(exist_ok=True)
    if project_token:
        upload_dir = base_upload_dir / project_token
    else:
        upload_dir = base_upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)

    # ── Upload processing ────────────────────────────────────────────────────
    # The client sends each file as a zip (already client-side converted to PDF).
    # Server wraps the received zip in an AES-256 encrypted zip WITHOUT extracting
    # or converting anything. The password is stored in DB.
    # ─────────────────────────────────────────────────────────────────────────
    import pyzipper as _pyzipper

    file_paths = []
    if files:
        for file in files:
            file_id = secrets.token_urlsafe(16)
            content = await file.read()

            # Generate a strong random AES-256 password for this file
            zip_password = secrets.token_urlsafe(32)

            # Store the AES-encrypted zip on disk
            enc_filename = f"{file_id}.szp"   # .szp = secure zip
            enc_path = upload_dir / enc_filename

            try:
                with _pyzipper.AESZipFile(
                    str(enc_path), 'w',
                    compression=_pyzipper.ZIP_DEFLATED,
                    encryption=_pyzipper.WZ_AES
                ) as zf:
                    zf.setpassword(zip_password.encode())
                    # Store client's zip as an opaque blob — no extraction
                    zf.writestr('data.zip', content)

                orig_name = file.filename
                ext = Path(orig_name).suffix.lower()
                media_type = 'text/html' if ext in ['.html', '.htm'] else 'application/pdf'
                
                file_paths.append({
                    'filename': enc_filename,
                    'original_filename': orig_name,
                    'path': str(enc_path),
                    'size': len(content),
                    'type': media_type,
                    'zip_password': zip_password
                })
                print(f"[upload] Stored encrypted container for {file.filename} → {enc_filename}")
            except Exception as e:
                print(f"[upload] Failed to encrypt {file.filename}: {e}")
                # Fallback: store raw (still functional but unencrypted)
                raw_path = upload_dir / f"{file_id}_raw{Path(file.filename).suffix}"
                raw_path.write_bytes(content)
                file_paths.append({
                    'filename': raw_path.name,
                    'original_filename': file.filename,
                    'path': str(raw_path),
                    'size': len(content),
                    'type': file.content_type or '',
                    'zip_password': None
                })

    
    # If no new files but project token provided, get existing files from latest share
    if not file_paths and share_project_id:
        latest_share = db.query(models.SharedDocument).filter(
            models.SharedDocument.share_project_id == share_project_id
        ).order_by(models.SharedDocument.created_at.desc()).first()
        
        if latest_share and latest_share.files:
            for f in latest_share.files:
                # Only include if it was selected in the frontend
                # (Handle both integer IDs and string IDs from JS)
                if selected_file_ids and str(f.id) not in [str(sid) for sid in selected_file_ids]:
                    continue
                    
                file_paths.append({
                    'filename': f.filename,
                    'original_filename': f.original_filename,
                    'path': f.file_path,
                    'size': f.file_size,
                    'type': f.file_type,
                    'zip_password': f.zip_password  # CRITICAL FIX: copy the password!
                })
    
    # Create shared document entry
    try:
        # Generate unique share token
        share_token = secrets.token_urlsafe(32)
        
        # Calculate expiration
        expires_at = None
        expiration_time = share_config.get('expirationTime', 'no-expiration')
        expiration_days = share_config.get('expirationDays')
        expiration_date = share_config.get('expirationDate')
        
        now = datetime.utcnow()
        
        if expiration_date:
            try:
                # Expecting YYYY-MM-DD
                expires_at = datetime.fromisoformat(expiration_date).replace(hour=23, minute=59, second=59)
            except (ValueError, TypeError):
                pass
        
        if not expires_at and share_config.get('dashboardAccess') == 'once':
            # Handle Limited View days
            try:
                days = int(expiration_days) if expiration_days else 7
            except (ValueError, TypeError):
                days = 7
            expires_at = now + timedelta(days=days)
        elif not expires_at and expiration_time != 'no-expiration':
            if expiration_time == '24h':
                expires_at = now + timedelta(hours=24)
            elif expiration_time == '7d':
                expires_at = now + timedelta(days=7)
            elif expiration_time == '30d':
                expires_at = now + timedelta(days=30)
        
        # Hash password if required
        password_hash = None
        if share_config.get('requirePassword') and share_config.get('password'):
            password_hash = hashlib.sha256(share_config['password'].encode()).hexdigest()
        
        # Create shared document record
        shared_doc = models.SharedDocument(
            share_token=share_token,
            user_id=current_user.id,
            share_project_id=share_project_id,
            title=f"Shared Documents - {datetime.utcnow().strftime('%Y-%m-%d')}",
            access_type=share_config.get('dashboardAccess', 'once'),
            expiration_time=expiration_time,
            expires_at=expires_at,
            require_password=share_config.get('requirePassword', False),
            password_hash=password_hash,
            view_limit=share_config.get('viewLimit') if share_config.get('dashboardAccess') == 'once' else None,
            can_download=share_config.get('canDownload', True),
            allow_anonymous=share_config.get('allowAnonymous', True)
        )
        
        db.add(shared_doc)
        db.flush()  # Get the ID without committing
        
        # Add file records (including zip_password for encrypted containers)
        for file_info in file_paths:
            shared_file = models.SharedDocumentFile(
                share_id=shared_doc.id,
                filename=file_info['filename'],
                original_filename=file_info['original_filename'],
                file_path=file_info['path'],
                file_size=file_info.get('size', 0),
                file_type=file_info.get('type', ''),
                zip_password=file_info.get('zip_password')
            )
            db.add(shared_file)
        
        # Add recipients with individual tokens
        recipient_data = []
        if recipient_list:
            for item in recipient_list:
                email = item.get('email', '').strip() if isinstance(item, dict) else item.strip()
                access_level = item.get('access_level', 'view') if isinstance(item, dict) else 'view'
                if email:
                    token = secrets.token_urlsafe(32)
                    recipient = models.SharedDocumentRecipient(
                        share_id=shared_doc.id,
                        email=email,
                        share_token=token,
                        access_level=access_level
                    )
                    db.add(recipient)
                    recipient_data.append({
                        'email': email,
                        'share_token': token,
                        'access_level': access_level
                    })
        
        db.commit()
        
        # Generate share URL
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        share_url = f"{frontend_url}/shared/{share_token}"
        
        # Send email notifications using individual links
        if recipient_data:
            try:
                from share_document_service import send_share_notification_emails
                send_share_notification_emails(
                    share_id=shared_doc.id,
                    recipients_data=recipient_data,
                    sender_name=current_user.email,
                    document_count=len(file_paths),
                    config=share_config
                )
            except Exception as e:
                print(f"Failed to send email notifications: {e}")
        
        return {
            'success': True,
            'share_url': share_url,
            'share_token': share_token
        }
        
    except Exception as e:
        db.rollback()
        # Clean up uploaded files on error
        for file_info in file_paths:
            try:
                Path(file_info['path']).unlink(missing_ok=True)
            except:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to create share: {str(e)}")



# ── Streaming helpers ─────────────────────────────────────────────────────────

def _chunked(buf, chunk_size: int = 256 * 1024):
    """Yield bytes from a file-like object in chunks for StreamingResponse."""
    while True:
        data = buf.read(chunk_size)
        if not data:
            break
        yield data


def _decrypt_and_extract_file(file_path: "Path", file_info) -> tuple[bytes, str]:
    """
    Decrypt the AES-256 outer zip, extract the client's inner zip,
    extract the actual file, and return (file_bytes, media_type).
    Preserves HTML/PDF raw files and converts other documents to PDF on the fly.
    Falls back to reading the file directly if it isn't an encrypted container.
    """
    import io, zipfile, pyzipper, pdf_converter

    raw_bytes = None
    orig_name = file_info.original_filename or file_path.name

    # ── Encrypted container (.szp) ──────────────────────────────────────────
    if file_info.zip_password and file_path.suffix == '.szp':
        with pyzipper.AESZipFile(str(file_path)) as outer:
            outer.setpassword(file_info.zip_password.encode())
            inner_zip_bytes = outer.read('data.zip')

        # Inner zip: contains the original file sent by the client
        try:
            with zipfile.ZipFile(io.BytesIO(inner_zip_bytes)) as inner:
                names = inner.namelist()
                if not names:
                    raise ValueError("Client zip is empty")
                raw_bytes = inner.read(names[0])
                orig_name = names[0]
        except zipfile.BadZipFile:
            # If the inner content is not a zip file, it was stored raw inside the szp!
            raw_bytes = inner_zip_bytes
    else:
        # ── Unencrypted fallback (plain PDF or older uploads) / Raw storage ─────
        raw_bytes = file_path.read_bytes()

    ext = Path(orig_name).suffix.lower()
    
    # Preserve HTML files
    if ext in ['.html', '.htm']:
        return raw_bytes, "text/html"
        
    # Preserve PDF files
    if ext == '.pdf':
        return raw_bytes, "application/pdf"

    # Always convert other types to PDF so they render natively in the browser's PDF viewer
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        tmp.write(raw_bytes)
        tmp.close()
        pdf_bytes = pdf_converter.convert_to_pdf(tmp.name, orig_name)
        return pdf_bytes, "application/pdf"
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/shared/{share_token}")
async def get_shared_document(
    share_token: str,
    password: Optional[str] = None,
    r: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Retrieve shared document information by token.
    Validates access permissions and logs access.
    """
    import hashlib
    
    # Get shared document - check base token OR individual recipient token
    shared_doc = db.query(models.SharedDocument).filter(
        models.SharedDocument.share_token == share_token
    ).first()
    
    recipient_email = r
    individual_access_level = None
    
    if not shared_doc:
        # Check individual recipient token
        recipient = db.query(models.SharedDocumentRecipient).filter(
            models.SharedDocumentRecipient.share_token == share_token
        ).first()
        
        if not recipient:
            raise HTTPException(status_code=404, detail="Share link not found or expired")
        
        shared_doc = recipient.shared_document
        recipient_email = recipient.email
        individual_access_level = recipient.access_level
    else:
        # If base token, check if anonymous access is allowed
        if not shared_doc.allow_anonymous:
            raise HTTPException(status_code=403, detail="Anonymous access is disabled for this share")
    
    # Check if expired
    if shared_doc.expires_at and datetime.utcnow() > shared_doc.expires_at:
        raise HTTPException(status_code=404, detail="Share link has expired")
    
    # Check if access limit reached (for 'once' access type)
    # If view_limit is set, we check against the total access_count
    if shared_doc.access_type == 'once':
        limit = shared_doc.view_limit or 1 # Default to 1 if not set but type is 'once'
        if shared_doc.access_count >= limit:
            raise HTTPException(status_code=404, detail=f"Share link has reached its access limit of {limit} views")
    
    # Check password if required
    if shared_doc.require_password:
        if not password:
            return {
                'require_password': True,
                'message': 'Password required to access this share'
            }
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if password_hash != shared_doc.password_hash:
            raise HTTPException(status_code=403, detail="Invalid password")
    
    # Log access - prevent duplicate logs within a short timeframe (e.g., 10 seconds)
    # to handle React StrictMode double-mounting or browser pre-fetching
    ip_address = request.client.host if request else None
    user_agent = request.headers.get('user-agent') if request else None
    
    # Check for recent identical log (last 10 seconds)
    recent_log = db.query(models.SharedDocumentAccessLog).filter(
        models.SharedDocumentAccessLog.share_id == shared_doc.id,
        models.SharedDocumentAccessLog.ip_address == ip_address,
        models.SharedDocumentAccessLog.recipient_email == recipient_email,
        models.SharedDocumentAccessLog.action == "view",
        models.SharedDocumentAccessLog.accessed_at >= datetime.utcnow() - timedelta(seconds=10)
    ).first()
    
    if not recent_log:
        access_log = models.SharedDocumentAccessLog(
            share_id=shared_doc.id,
            ip_address=ip_address,
            user_agent=user_agent,
            recipient_email=recipient_email,
            action="view",
            filename="Dashboard"
        )
        db.add(access_log)
        
        # Increment access count
        shared_doc.access_count += 1
    
    db.commit()
    
    # Determine download permission based on global setting AND individual level
    can_download = shared_doc.can_download
    if individual_access_level == 'view':
        can_download = False
    
    # Return share information (without sensitive data)
    return {
        'title': shared_doc.title,
        'files': [
            {
                'id': f.id,
                'filename': f.original_filename,
                'size': f.file_size,
                'type': f.file_type,
                'uploaded_at': (f.uploaded_at.isoformat() + 'Z') if f.uploaded_at else None
            }
            for f in shared_doc.files
        ],
        'created_at': (shared_doc.created_at.isoformat() + 'Z') if shared_doc.created_at else None,
        'access_type': shared_doc.access_type,
        'can_download': can_download,
        'recipient_email': recipient_email
    }


@router.get("/api/shared/{share_token}/download/{file_id}")
async def download_shared_file(
    share_token: str,
    file_id: int,
    password: Optional[str] = None,
    v_token: Optional[str] = None,
    r: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Download a specific file from a shared document.
    """
    import hashlib
    from fastapi.responses import FileResponse
    
    # Get shared document - check base token OR individual recipient token
    shared_doc = db.query(models.SharedDocument).filter(
        models.SharedDocument.share_token == share_token
    ).first()
    
    recipient_email = r
    individual_access_level = None
    
    if not shared_doc:
        # Check individual recipient token
        recipient = db.query(models.SharedDocumentRecipient).filter(
            models.SharedDocumentRecipient.share_token == share_token
        ).first()
        
        if not recipient:
            raise HTTPException(status_code=404, detail="Share link not found or expired")
        
        shared_doc = recipient.shared_document
        recipient_email = recipient.email
        individual_access_level = recipient.access_level
    else:
        # If base token, check if anonymous access is allowed
        if not shared_doc.allow_anonymous:
            raise HTTPException(status_code=403, detail="Anonymous access is disabled for this share")
    
    # Determine download permission based on global setting AND individual level
    can_download = shared_doc.can_download
    if individual_access_level == 'view':
        can_download = False
        
    if not can_download:
        raise HTTPException(status_code=403, detail="Downloads are not allowed for this share")
    
    # Check if expired
    if shared_doc.expires_at and datetime.utcnow() > shared_doc.expires_at:
        raise HTTPException(status_code=404, detail="Share link has expired")
    
    # Check password if required
    if shared_doc.require_password:
        if not password:
            raise HTTPException(status_code=403, detail="Password required")
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if password_hash != shared_doc.password_hash:
            raise HTTPException(status_code=403, detail="Invalid password")
    
    # Find the requested file
    file_info = db.query(models.SharedDocumentFile).filter(
        models.SharedDocumentFile.share_id == shared_doc.id,
        models.SharedDocumentFile.id == file_id
    ).first()
    
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found")

    # Log download
    ip_address = request.client.host if request else None
    user_agent = request.headers.get('user-agent') if request else None
    
    access_log = models.SharedDocumentAccessLog(
        share_id=shared_doc.id,
        ip_address=ip_address,
        user_agent=user_agent,
        recipient_email=recipient_email,
        action="download",
        filename=file_info.original_filename
    )
    db.add(access_log)
    db.commit()
    
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File no longer available")

    # Decrypt AES zip -> inner zip -> extract file -> stream
    try:
        file_bytes, media_type = _decrypt_and_extract_file(file_path, file_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to decrypt file: {e}")

    from fastapi.responses import StreamingResponse
    import io
    return StreamingResponse(
        _chunked(io.BytesIO(file_bytes)),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_info.original_filename}"',
            "Content-Length": str(len(file_bytes)),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff"
        }
    )



@router.get("/api/shared/{share_token}/view/{file_id}")
async def view_shared_file(
    share_token: str,
    file_id: int,
    password: Optional[str] = None,
    v_token: Optional[str] = None,
    r: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    View a specific file from a shared document inline.
    """
    import hashlib
    from fastapi.responses import Response
    
    # Get shared document - check base token OR individual recipient token
    shared_doc = db.query(models.SharedDocument).filter(
        models.SharedDocument.share_token == share_token
    ).first()
    
    recipient_email = r
    individual_access_level = None
    
    if not shared_doc:
        # Check individual recipient token
        recipient = db.query(models.SharedDocumentRecipient).filter(
            models.SharedDocumentRecipient.share_token == share_token
        ).first()
        
        if not recipient:
            raise HTTPException(status_code=404, detail="Share link not found or expired")
        
        shared_doc = recipient.shared_document
        recipient_email = recipient.email
        individual_access_level = recipient.access_level
    else:
        # If base token, check if anonymous access is allowed
        if not shared_doc.allow_anonymous:
            raise HTTPException(status_code=403, detail="Anonymous access is disabled for this share")
    
    # Check if expired
    if shared_doc.expires_at and datetime.utcnow() > shared_doc.expires_at:
        raise HTTPException(status_code=404, detail="Share link has expired")
    
    # Check password if required
    if shared_doc.require_password:
        if not password:
            raise HTTPException(status_code=403, detail="Password required")
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if password_hash != shared_doc.password_hash:
            raise HTTPException(status_code=403, detail="Invalid password")
    
    # Find the requested file
    file_info = db.query(models.SharedDocumentFile).filter(
        models.SharedDocumentFile.share_id == shared_doc.id,
        models.SharedDocumentFile.id == file_id
    ).first()
    
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found")

    # Log view
    ip_address = request.client.host if request else None
    user_agent = request.headers.get('user-agent') if request else None
    
    access_log = models.SharedDocumentAccessLog(
        share_id=shared_doc.id,
        ip_address=ip_address,
        user_agent=user_agent,
        recipient_email=recipient_email,
        action="view",
        filename=file_info.original_filename
    )
    db.add(access_log)
    db.commit()
    
    file_path = Path(file_info.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File no longer available")

    # Decrypt AES zip -> inner zip -> extract file -> stream inline
    try:
        file_bytes, media_type = _decrypt_and_extract_file(file_path, file_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to decrypt file: {e}")

    from fastapi.responses import StreamingResponse
    import io
    return StreamingResponse(
        _chunked(io.BytesIO(file_bytes)),
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{file_info.original_filename}"',
            "Content-Length": str(len(file_bytes)),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff"
        }
    )

@router.get("/api/share-doc/{share_id}/recipients", response_model=List[Dict[str, Any]])
async def get_share_doc_recipients(
    share_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get all recipients for a share with their tokens and access levels."""
    # Verify ownership
    share = db.query(models.SharedDocument).filter(
        models.SharedDocument.id == share_id,
        models.SharedDocument.user_id == current_user.id
    ).first()
    
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")
        
    recipients = db.query(models.SharedDocumentRecipient).filter(
        models.SharedDocumentRecipient.share_id == share_id
    ).all()
    
    return [
        {
            'email': r.email,
            'share_token': r.share_token,
            'access_level': r.access_level,
            'notified_at': r.notified_at.isoformat() if r.notified_at else None
        }
        for r in recipients
    ]


@router.get("/api/share-doc/stats")
async def get_share_stats(
    token: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Get statistics for a shared document (access count, access log, etc.)
    """
    
    # Get share data
    shared_doc = db.query(models.SharedDocument).filter(
        models.SharedDocument.share_token == token,
        models.SharedDocument.user_id == current_user.id
    ).first()
    
    if not shared_doc:
        raise HTTPException(status_code=404, detail="Share not found")
    
    # Get access log (limit to 50 most recent)
    access_logs = db.query(models.SharedDocumentAccessLog).filter(
        models.SharedDocumentAccessLog.share_id == shared_doc.id
    ).order_by(models.SharedDocumentAccessLog.accessed_at.desc()).limit(50).all()
    
    return {
        'access_count': shared_doc.access_count,
        'access_log': [
            {
                'id': log.id,
                'accessed_at': (log.accessed_at.isoformat() + 'Z') if log.accessed_at else None,
                'ip_address': log.ip_address,
                'user_agent': log.user_agent,
                'email': log.recipient_email,
                'action': log.action,
                'filename': log.filename
            }
            for log in access_logs
        ],
        'created_at': (shared_doc.created_at.isoformat() + 'Z') if shared_doc.created_at else None,
        'expires_at': (shared_doc.expires_at.isoformat() + 'Z') if shared_doc.expires_at else None
    }


def _share_project_query_for_user(db: Session, current_user: models.User):
    """
    Returns a SQLAlchemy query for ShareProject scoped to the user's organization if present,
    or to the individual user if no organization is specified.
    This ensures org members can see and manage each other's share projects,
    while strictly filtering out any project that has been archived.
    """
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))
    not_archived_sp = or_(
        models.ShareProject.is_archived == None,
        models.ShareProject.is_archived == False
    )
    archived_gov_tokens = db.query(models.GovernanceResponse.project_token).filter(
        models.GovernanceResponse.is_archived == True
    ).scalar_subquery()

    if not organization_name:
        return db.query(models.ShareProject).filter(
            models.ShareProject.owner_id == current_user.id,
            not_archived_sp,
            ~models.ShareProject.project_token.in_(archived_gov_tokens)
        )
    org_user_ids = db.query(models.User.id).filter(
        func.lower(models.User.organization_name) == organization_name.lower()
    ).scalar_subquery()
    return db.query(models.ShareProject).filter(
        models.ShareProject.owner_id.in_(org_user_ids),
        not_archived_sp,
        ~models.ShareProject.project_token.in_(archived_gov_tokens)
    )


# --- Share Project Endpoints ---
@router.post("/api/share-projects")
async def create_share_project(
    project_data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Create a new share project for organizing shared documents
    """
    import secrets
    
    project_name = project_data.get('project_name', '').strip()
    if not project_name:
        raise HTTPException(status_code=400, detail="Project name is required")
    
    # Generate unique project token
    project_token = f"share_{secrets.token_urlsafe(16)}"
    
    # Create share project
    share_project = models.ShareProject(
        project_token=project_token,
        owner_id=current_user.id,
        project_name=project_name,
        description=project_data.get('description', 'Shared Documents')
    )
    
    db.add(share_project)
    db.commit()
    db.refresh(share_project)
    
    return {
        'success': True,
        'project': {
            'id': share_project.id,
            'project_token': share_project.project_token,
            'project_name': share_project.project_name,
            'description': share_project.description,
            'created_at': share_project.created_at.isoformat() if share_project.created_at else None,
            'current_step': share_project.current_step
        }
    }


@router.get("/api/share-projects")
async def get_share_projects(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Get all share projects for the current user
    """
    share_projects = _share_project_query_for_user(db, current_user).order_by(models.ShareProject.created_at.desc()).all()
    
    # Get document counts for each project
    result = []
    for project in share_projects:
        doc_count = db.query(func.count(models.SharedDocumentFile.original_filename.distinct())).join(models.SharedDocument).filter(
            models.SharedDocument.share_project_id == project.id
        ).scalar() or 0
        
        result.append({
            'id': project.id,
            'project_token': project.project_token,
            'project_name': project.project_name,
            'description': project.description,
            'document_count': doc_count,
            'created_at': (project.created_at.isoformat() + 'Z') if project.created_at else None,
            'updated_at': (project.updated_at.isoformat() + 'Z') if project.updated_at else None,
            'current_step': project.current_step
        })
    
    return result


@router.get("/api/share-projects/{project_token}")
async def get_share_project(
    project_token: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Get a specific share project with its documents
    """
    share_project = _share_project_query_for_user(db, current_user).filter(
        models.ShareProject.project_token == project_token
    ).first()
    
    if not share_project:
        raise HTTPException(status_code=404, detail="Share project not found")
    
    # Get all shared documents for this project
    shared_docs = db.query(models.SharedDocument).filter(
        models.SharedDocument.share_project_id == share_project.id
    ).order_by(models.SharedDocument.created_at.desc()).all()
    
    documents = []
    for doc in shared_docs:
        # Get files
        files = db.query(models.SharedDocumentFile).filter(
            models.SharedDocumentFile.share_id == doc.id
        ).all()
        
        # Get recipients
        recipients = db.query(models.SharedDocumentRecipient).filter(
            models.SharedDocumentRecipient.share_id == doc.id
        ).all()
        
        documents.append({
            'id': doc.id,
            'share_token': doc.share_token,
            'title': doc.title,
            'access_type': doc.access_type,
            'access_count': doc.access_count,
            'can_download': doc.can_download,
            'allow_anonymous': doc.allow_anonymous,
            'view_limit': doc.view_limit,
            'created_at': (doc.created_at.isoformat() + 'Z') if doc.created_at else None,
            'expires_at': (doc.expires_at.isoformat() + 'Z') if doc.expires_at else None,
            'files': [{
                'id': f.id,
                'filename': f.filename,
                'original_filename': f.original_filename,
                'file_size': f.file_size,
                'file_type': f.file_type
            } for f in files],
            'recipients': [{
                'email': r.email,
                'access_level': r.access_level
            } for r in recipients]
        })
    
    return {
        'project': {
            'id': share_project.id,
            'project_token': share_project.project_token,
            'project_name': share_project.project_name,
            'description': share_project.description,
            'created_at': (share_project.created_at.isoformat() + 'Z') if share_project.created_at else None,
            'updated_at': (share_project.updated_at.isoformat() + 'Z') if share_project.updated_at else None,
            'current_step': share_project.current_step
        },
        'documents': documents
    }


@router.patch("/api/share-projects/{project_token}")
async def update_share_project(
    project_token: str,
    project_data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Update a share project (e.g. current_step)
    """
    share_project = _share_project_query_for_user(db, current_user).filter(
        models.ShareProject.project_token == project_token
    ).first()
    
    if not share_project:
        raise HTTPException(status_code=404, detail="Share project not found")
    
    if 'current_step' in project_data:
        share_project.current_step = project_data['current_step']
    
    if 'project_name' in project_data:
        share_project.project_name = project_data['project_name']
        
    if 'description' in project_data:
        share_project.description = project_data['description']
        
    db.commit()
    db.refresh(share_project)
    
    return {
        'success': True,
        'project': {
            'id': share_project.id,
            'project_token': share_project.project_token,
            'project_name': share_project.project_name,
            'current_step': share_project.current_step
        }
    }

@router.post("/api/share-projects/{project_token}/upload-files")
async def upload_project_files(
    project_token: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Upload and encrypt files immediately inside a project-isolated folder
    """
    # 1. Fetch project
    project = _share_project_query_for_user(db, current_user).filter(
        models.ShareProject.project_token == project_token
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. Get or create the latest SharedDocument for this project (acting as active draft/share)
    shared_doc = db.query(models.SharedDocument).filter(
        models.SharedDocument.share_project_id == project.id
    ).order_by(models.SharedDocument.created_at.desc()).first()

    if not shared_doc:
        shared_doc = models.SharedDocument(
            share_token=secrets.token_urlsafe(32),
            user_id=current_user.id,
            share_project_id=project.id,
            title=f"Shared Documents - {datetime.utcnow().strftime('%Y-%m-%d')}",
            access_type='once',
            expiration_time='no-expiration',
            expires_at=None,
            require_password=False,
            password_hash=None,
            view_limit=None,
            can_download=True,
            allow_anonymous=True
        )
        db.add(shared_doc)
        db.flush()

    # 3. Create isolated upload directory: shared_documents/{project_token}/
    base_upload_dir = Path("shared_documents")
    base_upload_dir.mkdir(exist_ok=True)
    upload_dir = base_upload_dir / project_token
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 4. Save files directly as default as is
    added_files = []

    for file in files:
        file_id = secrets.token_urlsafe(16)
        content = await file.read()
        
        orig_name = file.filename
        ext = Path(orig_name).suffix.lower()
        
        enc_filename = f"{file_id}{ext}"
        enc_path = upload_dir / enc_filename

        try:
            # Write raw content directly as is
            enc_path.write_bytes(content)
            
            media_type = 'text/html' if ext in ['.html', '.htm'] else 'application/pdf'
            
            shared_file = models.SharedDocumentFile(
                share_id=shared_doc.id,
                filename=enc_filename,
                original_filename=orig_name,
                file_path=str(enc_path),
                file_size=len(content),
                file_type=media_type,
                zip_password=None
            )
            db.add(shared_file)
            db.flush()

            added_files.append({
                'id': shared_file.id,
                'filename': shared_file.filename,
                'original_filename': shared_file.original_filename,
                'file_size': shared_file.file_size,
                'file_type': shared_file.file_type
            })
        except Exception as e:
            print(f"Failed to save uploaded file {file.filename}: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to upload and save file: {e}")

    db.commit()
    return {"success": True, "files": added_files}


@router.delete("/api/share-projects/{project_token}/files/{file_id}")
async def delete_project_file(
    project_token: str,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Delete a specific uploaded file from project isolated folder and database
    """
    project = db.query(models.ShareProject).filter(
        models.ShareProject.project_token == project_token,
        models.ShareProject.owner_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    shared_file = db.query(models.SharedDocumentFile).join(models.SharedDocument).filter(
        models.SharedDocumentFile.id == file_id,
        models.SharedDocument.share_project_id == project.id
    ).first()

    if not shared_file:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        Path(shared_file.file_path).unlink(missing_ok=True)
    except Exception as e:
        print(f"Warning: Failed to delete physical file {shared_file.file_path}: {e}")

    db.delete(shared_file)
    db.commit()
    return {"success": True}


@router.delete("/api/share-projects/{project_token}")
async def delete_share_project(
    project_token: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Delete a share project and all its associated documents
    """
    share_project = _share_project_query_for_user(db, current_user).filter(
        models.ShareProject.project_token == project_token
    ).first()
    
    if not share_project:
        raise HTTPException(status_code=404, detail="Share project not found")
    
    # Delete all associated shared documents (cascade will handle files, recipients, logs)
    db.query(models.SharedDocument).filter(
        models.SharedDocument.share_project_id == share_project.id
    ).delete()
    
    # Delete the project
    db.delete(share_project)
    db.commit()
    
    return {'success': True, 'message': 'Share project deleted successfully'}


# --- Chat Message Endpoints ---

# --- Extracted Block (Lines 7876-7940) ---
@router.post("/documents/upload-and-analyze")
async def upload_and_analyze_document(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Upload a document, extract content with Direct AI, and analyze with AI.
    One-step endpoint for complete BRD analysis.
    """
    # Validate file type
    allowed_extensions = {".pdf", ".docx", ".pptx", ".html", ".htm", ".png", ".jpg", ".jpeg"}
    file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(allowed_extensions)}"
        )
    
    MAX_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
    
    # Read and save file
    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds 100MB limit.")
        
    file_path = ingestion.save_uploaded_file(content, file.filename)
    
    # Process with Direct AI Ingestion
    extraction_result = await ingestion.process_document(file_path)
    
    # Cleanup the uploaded file
    ingestion.cleanup_file(file_path)
    
    if extraction_result["status"] == "error":
        raise HTTPException(status_code=500, detail=extraction_result["error"])
    
    # Analyze with AI (using chunked or original based on configuration)
    if settings.use_chunked_analysis:
        logger.info("Using chunked multi-stage analysis for uploaded document")
        analysis_result = await ai_service_chunked.analyze_document(
            document_content=extraction_result["markdown"],
            image_paths=extraction_result.get("images", [])
        )
    else:
        logger.info("Using original single-stage analysis for uploaded document")
        analysis_result = await ai_service.analyze_document(
            document_content=extraction_result["markdown"],
            image_paths=extraction_result.get("images", [])
        )
    
    return {
        "filename": file.filename,
        "user": current_user.email,
        "extraction": {
            "markdown": extraction_result["markdown"],
            "html": extraction_result.get("html"),
            "num_pages": extraction_result.get("num_pages")
        },
        "analysis": analysis_result
    }


# ═══════════════════════════════════════════════════════════════════════════
# ARCHITECTURE DESIGN (HLD & LLD) ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

class GenerateDesignPayload(BaseModel):
    design_type: Optional[str] = "all"  # "all" | "hld" | "lld"
    user_preferences: Optional[str] = None
    force_regenerate: Optional[bool] = False


@router.get("/documents/{document_id}/design")
async def get_document_architecture_design(
    document_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve the industry-grade High-Level Design (HLD) and Low-Level Design (LLD)
    for a given document. If not present in stored analysis, auto-synthesizes them.
    """
    db_doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not db_doc:
        raise HTTPException(status_code=404, detail="Document not found")

    analysis_data = {}
    if db_doc.analysis_result:
        try:
            analysis_data = json.loads(db_doc.analysis_result)
        except Exception:
            analysis_data = {}

    from app.services.ai.architecture_design_service import architecture_design_service, sanitize_design_markdown_date

    if getattr(db_doc, "project_token", None):
        from app.integrations.llm.llm_gateway import current_project_token_var
        current_project_token_var.set(db_doc.project_token)

    if getattr(db_doc, "project_token", None):
        from app.integrations.llm.llm_gateway import current_project_token_var
        current_project_token_var.set(db_doc.project_token)

    p_name = analysis_data.get("title") or db_doc.filename or "Enterprise Solution"
    brd_content = db_doc.full_content or db_doc.content_preview or analysis_data.get("analysis") or ""
    changed = False

    # Check or generate HLD via AI architecture design service
    hld = analysis_data.get("hld")
    if not hld or not isinstance(hld, dict) or not hld.get("markdown"):
        hld_res = await architecture_design_service.generate_high_level_design(
            brd_content=brd_content,
            analysis_data=analysis_data,
            project_name=p_name
        )
        analysis_data["hld"] = hld_res
        changed = True
    elif isinstance(hld, dict) and hld.get("markdown"):
        clean_md = sanitize_design_markdown_date(hld["markdown"])
        if clean_md != hld["markdown"]:
            hld["markdown"] = clean_md
            changed = True

    # Check or generate LLD via AI architecture design service
    lld = analysis_data.get("lld")
    if not lld or not isinstance(lld, dict) or not lld.get("markdown"):
        lld_res = await architecture_design_service.generate_low_level_design(
            brd_content=brd_content,
            hld_content=(analysis_data.get("hld") or {}).get("markdown"),
            analysis_data=analysis_data,
            project_name=p_name
        )
        analysis_data["lld"] = lld_res
        changed = True
    elif isinstance(lld, dict) and lld.get("markdown"):
        clean_md = sanitize_design_markdown_date(lld["markdown"])
        if clean_md != lld["markdown"]:
            lld["markdown"] = clean_md
            changed = True

    if changed:
        try:
            db_doc.analysis_result = json.dumps(analysis_data)
            db.add(db_doc)
            db.commit()
            db.refresh(db_doc)
        except Exception as e:
            logger.warning(f"Failed to persist synthesized HLD/LLD to database: {e}")

    return {
        "status": "success",
        "document_id": document_id,
        "filename": db_doc.filename,
        "hld": analysis_data.get("hld"),
        "lld": analysis_data.get("lld")
    }


@router.post("/documents/{document_id}/design/generate")
async def generate_document_architecture_design(
    document_id: int,
    payload: GenerateDesignPayload = GenerateDesignPayload(),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate or regenerate industry-grade High-Level Design (HLD) and/or
    Low-Level Design (LLD) for a BRD document using the AI architecture design service.
    """
    db_doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not db_doc:
        raise HTTPException(status_code=404, detail="Document not found")

    analysis_data = {}
    if db_doc.analysis_result:
        try:
            analysis_data = json.loads(db_doc.analysis_result)
        except Exception:
            analysis_data = {}

    if getattr(db_doc, "project_token", None):
        from app.integrations.llm.llm_gateway import current_project_token_var
        current_project_token_var.set(db_doc.project_token)

    p_name = analysis_data.get("title") or db_doc.filename or "Enterprise Solution"
    brd_content = db_doc.full_content or analysis_data.get("analysis") or ""

    from app.services.ai.architecture_design_service import architecture_design_service

    design_type = (payload.design_type or "all").lower()

    if design_type == "hld":
        hld_res = await architecture_design_service.generate_high_level_design(
            brd_content=brd_content,
            analysis_data=analysis_data,
            project_name=p_name,
            user_preferences=payload.user_preferences
        )
        analysis_data["hld"] = hld_res
    elif design_type == "lld":
        hld_content = (analysis_data.get("hld") or {}).get("markdown")
        lld_res = await architecture_design_service.generate_low_level_design(
            brd_content=brd_content,
            hld_content=hld_content,
            analysis_data=analysis_data,
            project_name=p_name,
            user_preferences=payload.user_preferences
        )
        analysis_data["lld"] = lld_res
    else:  # "all"
        suite = await architecture_design_service.generate_complete_design_suite(
            brd_content=brd_content,
            analysis_data=analysis_data,
            project_name=p_name,
            user_preferences=payload.user_preferences
        )
        analysis_data["hld"] = suite.get("hld")
        analysis_data["lld"] = suite.get("lld")
        analysis_data["architecture_summary"] = suite.get("summary")

    db_doc.analysis_result = json.dumps(analysis_data)
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)

    return {
        "status": "success",
        "document_id": document_id,
        "filename": db_doc.filename,
        "hld": analysis_data.get("hld"),
        "lld": analysis_data.get("lld"),
        "architecture_summary": analysis_data.get("architecture_summary")
    }


@router.get("/documents/{document_id}/design/export")
async def export_document_architecture_design(
    document_id: int,
    design_type: str = Query("hld", description="Type of design: 'hld' or 'lld'"),
    format: str = Query("markdown", description="Export format: 'markdown'"),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export the High-Level Design (HLD) or Low-Level Design (LLD) as a standalone file.
    """
    db_doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not db_doc:
        raise HTTPException(status_code=404, detail="Document not found")

    analysis_data = {}
    if db_doc.analysis_result:
        try:
            analysis_data = json.loads(db_doc.analysis_result)
        except Exception:
            analysis_data = {}

    p_name = analysis_data.get("title") or db_doc.filename or "Enterprise Solution"
    brd_content = db_doc.full_content or db_doc.content_preview or analysis_data.get("analysis") or ""
    dtype = design_type.lower().strip()

    if dtype == "lld":
        design_obj = analysis_data.get("lld")
        if not design_obj or not design_obj.get("markdown"):
            from app.services.ai.architecture_design_service import architecture_design_service
            res = await architecture_design_service.generate_low_level_design(
                brd_content=brd_content,
                analysis_data=analysis_data,
                project_name=p_name
            )
            md = res.get("markdown", "")
        else:
            md = design_obj.get("markdown")
        doc_tag = "LLD"
    else:
        design_obj = analysis_data.get("hld")
        if not design_obj or not design_obj.get("markdown"):
            from app.services.ai.architecture_design_service import architecture_design_service
            res = await architecture_design_service.generate_high_level_design(
                brd_content=brd_content,
                analysis_data=analysis_data,
                project_name=p_name
            )
            md = res.get("markdown", "")
        else:
            md = design_obj.get("markdown")
        doc_tag = "HLD"

    from app.services.ai.architecture_design_service import sanitize_design_markdown_date
    md = sanitize_design_markdown_date(md)

    clean_proj = re.sub(r"[^A-Za-z0-9_-]", "_", p_name)
    export_filename = f"{clean_proj}_{doc_tag}_Specification.md"

    return Response(
        content=md.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{export_filename}"'
        }
    )



