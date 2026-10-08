"""
Architecture Validator & Traceability Engine
Provides comprehensive quality validation, requirements coverage analysis,
traceability mapping (Stage 1-4 -> HLD -> LLD), and HLD <-> LLD consistency checks.

Designed to enhance the existing architecture generation pipeline without
disrupting existing workflows or failing generation unnecessarily.
"""

import re
import json
import logging
from typing import Dict, Any, List, Optional, Tuple, Set

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "at",
    "by", "for", "with", "about", "against", "between", "into", "through",
    "during", "before", "after", "above", "below", "to", "from", "up", "down",
    "in", "out", "on", "off", "over", "under", "again", "further", "then", "once",
    "here", "there", "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too",
    "very", "can", "will", "just", "don", "should", "now", "user", "system",
    "platform", "application", "service", "must", "shall", "able", "need", "needs",
    "high", "low", "level", "design", "specification", "document", "architecture",
    "section", "overview", "core", "tier", "layer"
}


def _stem_word(w: str) -> str:
    w = w.lower().strip()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ing") and len(w) > 5:
        return w[:-3]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def _tokenize_text(text: str) -> List[str]:
    """Extract lowercased alphanumeric tokens, stripping common stop words and applying stemming."""
    if not text:
        return []
    tokens = re.findall(r"[A-Za-z0-9_]+", text.lower())
    return [_stem_word(t) for t in tokens if len(t) > 2 and t not in STOP_WORDS]


def extract_requirements_from_stages(analysis_data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Extract canonical requirement items from Stage 1-4 analysis data.
    Preserves requirement IDs if available or generates canonical deterministic IDs (REQ-001, etc.).
    """
    analysis_data = analysis_data or {}
    stages = analysis_data.get("stages") or {}
    if not isinstance(stages, dict):
        stages = {}

    stage1 = stages.get("stage1_requirements") or analysis_data.get("stage1_requirements") or {}
    raw_reqs = []

    # 1. Try functional_requirements
    fr = stage1.get("functional_requirements")
    if isinstance(fr, list):
        raw_reqs.extend(fr)
    elif isinstance(fr, str) and fr.strip():
        lines = [line.strip().lstrip("-*123456789. ") for line in fr.split("\n") if line.strip()]
        raw_reqs.extend(lines)

    # 2. Try user_stories or scope items
    us = stage1.get("user_stories") or stage1.get("scope") or stage1.get("core_features")
    if isinstance(us, list):
        raw_reqs.extend(us)
    elif isinstance(us, str) and us.strip():
        lines = [line.strip().lstrip("-*123456789. ") for line in us.split("\n") if line.strip()]
        raw_reqs.extend(lines)

    # 3. Fallback to extracting from stage3 endpoints if stage1 has no explicit list
    if not raw_reqs:
        stage3 = stages.get("stage3_data_api") or analysis_data.get("stage3_data_api") or {}
        endpoints = stage3.get("api_endpoints", [])
        if isinstance(endpoints, list):
            for ep in endpoints:
                if isinstance(ep, dict) and ep.get("purpose"):
                    raw_reqs.append(f"{ep.get('purpose')} ({ep.get('method', 'GET')} {ep.get('path', '')})")

    # 4. Fallback to product vision / scope
    if not raw_reqs:
        pv = stage1.get("product_vision") or stage1.get("project_description") or analysis_data.get("title")
        if pv:
            raw_reqs.append(str(pv))

    normalized: List[Dict[str, Any]] = []
    seen_titles = set()

    for i, req in enumerate(raw_reqs):
        if isinstance(req, dict):
            req_id = req.get("id") or req.get("req_id") or f"REQ-{i+1:03d}"
            title = req.get("title") or req.get("name") or req.get("description") or f"Requirement {i+1}"
            category = req.get("category") or req.get("domain") or "Functional"
        else:
            req_str = str(req).strip()
            id_match = re.match(r"^\[?(REQ-[0-9A-Za-z_-]+)\]?[:\s-]+(.*)$", req_str, re.IGNORECASE)
            if id_match:
                req_id = id_match.group(1).upper()
                title = id_match.group(2).strip() or req_str
            else:
                req_id = f"REQ-{i+1:03d}"
                title = req_str
            category = "Functional"

        if title in seen_titles:
            continue
        seen_titles.add(title)

        tokens = _tokenize_text(title)
        normalized.append({
            "id": req_id,
            "title": title,
            "category": category,
            "keywords": tokens
        })

    return normalized


def calculate_requirements_coverage(
    hld_markdown: str,
    analysis_data: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculates requirements-to-architecture coverage between Stage 1 requirements
    and the generated High-Level Design (HLD).

    Distinguishes between:
    - COVERED: Supported by a concrete architectural component, service, sequence flow, or API/data model.
    - PARTIALLY_COVERED: Represented in architectural sections but without a dedicated component.
    - MENTIONED_ONLY: Appears only in executive summary/scope/overview with no architectural representation.
    - UNCOVERED: Not represented in HLD.

    Returns:
        total_requirements: int
        covered_requirements: int (count of COVERED requirements)
        coverage_percentage: float (0.0 to 100.0)
        covered_items: list of {id, requirement, mapped_component, coverage_status, evidence_type}
        partially_covered_items: list of {id, requirement, mapped_component, coverage_status}
        mentioned_only_items: list of {id, requirement, mapped_component, coverage_status, reason}
        uncovered_items: list of {id, requirement, reason, coverage_status}
        status: "PASS" | "WARNING"
    """
    requirements = extract_requirements_from_stages(analysis_data)
    if not requirements:
        return {
            "total_requirements": 0,
            "covered_requirements": 0,
            "partially_covered_count": 0,
            "mentioned_only_count": 0,
            "uncovered_count": 0,
            "coverage_percentage": 100.0,
            "covered_items": [],
            "partially_covered_items": [],
            "mentioned_only_items": [],
            "uncovered_items": [],
            "status": "PASS",
            "message": "No structured requirements identified to analyze."
        }

    hld_raw = hld_markdown or ""
    hld_lower = hld_raw.lower()
    total_reqs = len(requirements)

    # Split HLD into Executive Summary vs Architectural Sections
    summary_parts = []
    arch_parts = []

    sections = re.split(r"(^\s*#{1,4}\s+[^\n]+)", hld_raw, flags=re.MULTILINE)
    current_header = ""
    for part in sections:
        if re.match(r"^\s*#{1,4}\s+[^\n]+", part):
            current_header = part.strip().lower()
        else:
            if any(h in current_header for h in ["executive summary", "overview", "introduction", "vision", "scope", "background"]):
                summary_parts.append(part)
            else:
                arch_parts.append(part)

    summary_text = "\n".join(summary_parts).lower()
    arch_text = "\n".join(arch_parts).lower()

    # Extract concrete architectural components, services, and diagrams from HLD
    # 1. Services & Components (e.g., PlaylistManagementService, TrackStreamingService)
    component_matches = set(re.findall(r"([A-Za-z0-9_-]+\s*(?:Service|Engine|Gateway|Manager|Tier|Worker|Controller|Cluster|Portal|Registry))", hld_raw, re.IGNORECASE))
    # 2. Mermaid container nodes
    container_nodes = set(re.findall(r'(\w+)\["([^"]+)"\]', hld_raw))
    # 3. Mermaid sequence participants / actors
    participants = set(re.findall(r'(?:participant|actor)\s+(\w+)(?:\s+as\s+([^\n]+))?', hld_raw, re.IGNORECASE))
    # 4. API paths and SQL tables
    api_paths = set(re.findall(r"(?:GET|POST|PUT|DELETE|PATCH)\s+([A-Za-z0-9_/{}]+)", hld_raw, re.IGNORECASE))
    sql_tables = set(re.findall(r"CREATE\s+TABLE\s+([A-Za-z0-9_]+)", hld_raw, re.IGNORECASE))

    # All architectural components normalized
    arch_component_catalog = []
    for c in component_matches:
        arch_component_catalog.append((c.strip(), _tokenize_text(c)))
    for nid, label in container_nodes:
        arch_component_catalog.append((label.strip(), _tokenize_text(label)))
    for p_id, p_label in participants:
        lbl = p_label.strip() if p_label else p_id
        arch_component_catalog.append((lbl, _tokenize_text(lbl)))
    for ep in api_paths:
        arch_component_catalog.append((f"API {ep}", _tokenize_text(ep)))
    for tbl in sql_tables:
        arch_component_catalog.append((f"Table {tbl}", _tokenize_text(tbl)))

    # Also capture HLD section headers
    hld_headers = re.findall(r"^\s*#{1,4}\s+(.+)$", hld_raw, re.MULTILINE)

    covered_items = []
    partially_covered_items = []
    mentioned_only_items = []
    uncovered_items = []

    for req in requirements:
        req_id = req["id"]
        title = req["title"]
        keywords = req["keywords"]
        title_lower = title.lower()

        coverage_status = "UNCOVERED"
        mapped_component = "General System Architecture"
        evidence_type = "none"
        reason = ""

        # 1. Check Explicit Requirement Tag in HLD (e.g. [REQ-001] or REQ-001)
        if req_id.lower() in arch_text:
            coverage_status = "COVERED"
            evidence_type = "explicit_id"
            mapped_component = f"Explicit Requirement Reference ({req_id})"
        elif req_id.lower() in summary_text:
            # Mentioned in summary with explicit tag
            coverage_status = "PARTIALLY_COVERED"
            evidence_type = "explicit_id_summary"
            mapped_component = "Executive Summary"
        else:
            # 2. Check match against Architectural Components / Services / Diagrams / APIs
            best_comp = None
            best_comp_score = 0
            for comp_name, comp_tokens in arch_component_catalog:
                matched_tokens = [k for k in keywords if k in comp_tokens or any(k in ct for ct in comp_tokens)]
                if len(matched_tokens) > best_comp_score:
                    best_comp_score = len(matched_tokens)
                    best_comp = comp_name

            # Also check if requirement keywords match concrete services in arch text
            arch_keyword_matches = [k for k in keywords if k in arch_text]
            arch_ratio = len(arch_keyword_matches) / max(1, len(keywords))

            # Summary keyword matches
            summary_keyword_matches = [k for k in keywords if k in summary_text]
            summary_ratio = len(summary_keyword_matches) / max(1, len(keywords))

            if best_comp and (best_comp_score >= 2 or (best_comp_score >= 1 and arch_ratio >= 0.2)):
                # Strongly mapped to a real architectural component or service
                coverage_status = "COVERED"
                evidence_type = "architectural_component"
                mapped_component = best_comp
            elif arch_ratio >= 0.4 or (len(arch_keyword_matches) >= 2 and arch_ratio >= 0.35):
                # Substantial presence in architectural sections (sections 2+)
                coverage_status = "COVERED"
                evidence_type = "architecture_section"
                if best_comp:
                    mapped_component = best_comp
                else:
                    # Find matching header
                    best_hdr = None
                    best_hdr_matches = 0
                    for hdr in hld_headers:
                        if any(h in hdr.lower() for h in ["summary", "overview", "scope"]):
                            continue
                        m = sum(1 for k in keywords if k in hdr.lower())
                        if m > best_hdr_matches:
                            best_hdr_matches = m
                            best_hdr = hdr
                    mapped_component = best_hdr.strip() if best_hdr else "Application Services Tier"
            elif summary_ratio >= 0.35 and arch_ratio < 0.2:
                # Appears in Executive Summary / Scope ONLY without architectural component
                coverage_status = "MENTIONED_ONLY"
                evidence_type = "summary_only"
                mapped_component = "Executive Summary (Mentioned Only)"
                reason = "Mentioned in executive summary without supporting architectural component, service, or workflow"
            elif arch_ratio >= 0.25:
                # Minor mention in arch sections
                coverage_status = "PARTIALLY_COVERED"
                evidence_type = "partial_architecture"
                mapped_component = "General Architecture"
                reason = "Partially referenced in architecture but lacks detailed service contracts or diagrams"
            else:
                coverage_status = "UNCOVERED"
                evidence_type = "none"
                reason = "Not represented in HLD architectural components, sequence workflows, or data models"

        item_data = {
            "id": req_id,
            "requirement": title,
            "mapped_component": mapped_component,
            "coverage_status": coverage_status,
            "evidence_type": evidence_type
        }
        if reason:
            item_data["reason"] = reason

        if coverage_status == "COVERED":
            covered_items.append(item_data)
        elif coverage_status == "PARTIALLY_COVERED":
            partially_covered_items.append(item_data)
            # Include in uncovered_items for backward-compatibility reporting
            uncovered_items.append(item_data)
        elif coverage_status == "MENTIONED_ONLY":
            mentioned_only_items.append(item_data)
            uncovered_items.append(item_data)
        else:
            uncovered_items.append(item_data)

    covered_count = len(covered_items)
    coverage_pct = round((covered_count / total_reqs) * 100, 2) if total_reqs > 0 else 100.0

    return {
        "total_requirements": total_reqs,
        "covered_requirements": covered_count,
        "partially_covered_count": len(partially_covered_items),
        "mentioned_only_count": len(mentioned_only_items),
        "uncovered_count": len([u for u in uncovered_items if u["coverage_status"] == "UNCOVERED"]),
        "coverage_percentage": coverage_pct,
        "covered_items": covered_items,
        "partially_covered_items": partially_covered_items,
        "mentioned_only_items": mentioned_only_items,
        "uncovered_items": uncovered_items,
        "status": "PASS" if coverage_pct >= 70.0 else "WARNING"
    }


def validate_hld_quality(
    hld_markdown: str,
    analysis_data: Optional[Dict[str, Any]],
    project_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validates HLD quality and structural completeness.
    Separates baseline structural checks (required for all HLD deliverables)
    from BRD-specific checks (derived strictly from analyzed Stage 1-4 requirements).
    Does NOT impose generic or hardcoded domain rules.
    """
    text = hld_markdown or ""
    issues = []
    warnings = []
    checks = {}

    analysis_data = analysis_data or {}
    stages = analysis_data.get("stages") or {}
    if not isinstance(stages, dict):
        stages = {}
    stage1 = stages.get("stage1_requirements") or analysis_data.get("stage1_requirements") or {}

    p_name = project_name or stage1.get("product_name") or analysis_data.get("title") or "Enterprise Solution"

    # --- Baseline Structural Completeness ---
    char_len = len(text.strip())
    checks["adequate_length"] = char_len >= 1200
    if char_len < 1200:
        warnings.append(f"HLD content length is relatively brief ({char_len} characters; expected >= 1200).")

    has_exec = bool(re.search(r"##\s*1\.\s*Executive Summary", text, re.IGNORECASE))
    checks["executive_summary"] = has_exec
    if not has_exec:
        warnings.append("Missing explicit Executive Summary section (Section 1).")

    has_c4 = bool(re.search(r"C4\s*Level|System Context|Container Topology", text, re.IGNORECASE))
    mermaid_blocks = re.findall(r"```mermaid([\s\S]*?)```", text)
    checks["c4_architecture"] = has_c4 and len(mermaid_blocks) >= 1
    if not has_c4 or len(mermaid_blocks) < 1:
        issues.append("Missing C4 Architecture topology diagram (C4 Level 1/2).")

    has_seq = any("sequencediagram" in b.lower() for b in mermaid_blocks)
    checks["sequence_workflows"] = has_seq
    if not has_seq:
        warnings.append("HLD does not contain valid sequence diagrams for core domain workflows.")

    has_sec = bool(re.search(r"Security|RBAC|Authentication|Authorization|Access Control", text, re.IGNORECASE))
    checks["security_rbac"] = has_sec
    if not has_sec:
        warnings.append("Missing Security Architecture or Role-Based Access Control (RBAC) specifications.")

    has_nfr = bool(re.search(r"Non-Functional|NFR|Scalability|Availability|Disaster Recovery", text, re.IGNORECASE))
    checks["nfr_infrastructure"] = has_nfr
    if not has_nfr:
        warnings.append("Missing Non-Functional Requirements (NFR) / Infrastructure guarantees.")

    # --- BRD-Specific Completeness (Derived STRICTLY from Stage 1 Requirements) ---
    reqs = extract_requirements_from_stages(analysis_data)
    text_lower = text.lower()

    if reqs:
        # Check alignment against actual requirements tokens
        all_req_tokens = []
        for r in reqs:
            all_req_tokens.extend(r["keywords"])
        matched_tokens = [t for t in all_req_tokens if t in text_lower]
        domain_alignment_score = len(matched_tokens) / max(1, len(all_req_tokens))
        checks["domain_alignment"] = domain_alignment_score >= 0.25
        if domain_alignment_score < 0.25:
            warnings.append("HLD shows low domain keyword alignment with Stage 1 analyzed requirements.")

        # If a specific critical capability is explicitly in Stage 1, verify HLD addresses it.
        # e.g., if Stage 1 explicitly requires "fraud detection", check for fraud detection.
        for r in reqs:
            title_l = r["title"].lower()
            if "fraud" in title_l:
                if not any(k in text_lower for k in ["fraud", "anomaly", "risk-scoring"]):
                    warnings.append("Stage 1 requirement 'Fraud Detection' is not addressed in HLD components or workflows.")
            if "streaming" in title_l and "audio" in title_l:
                if not any(k in text_lower for k in ["stream", "playback", "bitrate", "cdn", "hls"]):
                    warnings.append("Stage 1 requirement 'Audio Streaming' lacks dedicated playback/streaming architectural component.")
    else:
        checks["domain_alignment"] = True

    total_checks = len(checks)
    passed_checks = sum(1 for v in checks.values() if v)
    score = round((passed_checks / total_checks) * 100, 1) if total_checks > 0 else 100.0

    status = "PASS" if len(issues) == 0 and score >= 60.0 else "WARNING"

    return {
        "status": status,
        "score": score,
        "checks": checks,
        "issues": issues,
        "warnings": warnings,
        "mermaid_diagram_count": len(mermaid_blocks)
    }


def validate_lld_quality(
    lld_markdown: str,
    analysis_data: Optional[Dict[str, Any]],
    project_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validates Low-Level Design (LLD) quality, implementation depth,
    database schemas, DDL scripts, API specifications, and contracts.
    """
    text = lld_markdown or ""
    issues = []
    warnings = []
    checks = {}

    char_len = len(text.strip())
    checks["adequate_length"] = char_len >= 1500
    if char_len < 1500:
        warnings.append(f"LLD content length is relatively brief ({char_len} characters; expected >= 1500).")

    has_layered = bool(re.search(r"Clean Architecture|Layered Component|Presentation Layer|Application Layer|Controller", text, re.IGNORECASE))
    checks["layered_architecture"] = has_layered
    if not has_layered:
        warnings.append("Missing Clean Layered Component Architecture definitions.")

    has_er = bool(re.search(r"erdiagram|entity-relationship|data dictionary", text, re.IGNORECASE))
    has_sql_block = bool(re.search(r"```sql([\s\S]*?)```", text))
    checks["database_ddl"] = has_er or has_sql_block
    if not checks["database_ddl"]:
        warnings.append("Missing Entity-Relationship Diagram (ERD) or runnable SQL Migration DDL.")

    has_api = bool(re.search(r"OpenAPI|REST API|HTTP Method|Endpoint|Request Body|Status Codes", text, re.IGNORECASE))
    has_endpoints = bool(re.search(r"(GET|POST|PUT|DELETE|PATCH)\s+/[A-Za-z0-9_/{}]+", text))
    checks["api_specifications"] = has_api or has_endpoints
    if not checks["api_specifications"]:
        warnings.append("Missing detailed REST / OpenAPI endpoint specifications with schemas.")

    has_lifecycle = bool(re.search(r"statediagram|state machine|lifecycle|concurrency|idempotency|circuit breaker", text, re.IGNORECASE))
    checks["state_and_concurrency"] = has_lifecycle
    if not has_lifecycle:
        warnings.append("Missing State Machine or Concurrency/Idempotency resilience policies.")

    has_tree = bool(re.search(r"├──|└──|repository structure|file tree|file creation manifest", text))
    checks["repository_blueprint"] = has_tree
    if not has_tree:
        warnings.append("Missing physical directory and repository file tree blueprint.")

    total_checks = len(checks)
    passed_checks = sum(1 for v in checks.values() if v)
    score = round((passed_checks / total_checks) * 100, 1) if total_checks > 0 else 100.0

    status = "PASS" if len(issues) == 0 and score >= 60.0 else "WARNING"

    return {
        "status": status,
        "score": score,
        "checks": checks,
        "issues": issues,
        "warnings": warnings
    }


def validate_hld_lld_consistency(
    hld_markdown: str,
    lld_markdown: str,
    analysis_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Validates consistency between High-Level Design (HLD) and Low-Level Design (LLD).
    Detects material architectural contradictions across:
    - Persistence technology (e.g. PostgreSQL vs MongoDB)
    - Messaging / Event architecture (e.g. Kafka vs RabbitMQ)
    - Execution model (e.g. Asynchronous event-driven vs Synchronous REST-only)
    - Caching decisions (e.g. Redis vs Memcached)
    - Major services & component continuity

    Distinguishes:
    - PASS: Consistent, implementation details legitimately refine HLD.
    - WARNING: Minor omissions or documentation warnings.
    - MATERIAL_CONTRADICTION: Direct architectural contradictions between HLD and LLD.
    """
    hld_text = hld_markdown or ""
    lld_text = lld_markdown or ""

    if not hld_text.strip() or not lld_text.strip():
        return {
            "status": "PASS",
            "score": 100.0,
            "issues": [],
            "warnings": ["HLD or LLD content was empty, skipping deep consistency comparison."],
            "aligned_components": [],
            "missing_in_lld": []
        }

    issues = []
    warnings = []
    hld_lower = hld_text.lower()
    lld_lower = lld_text.lower()

    # 1. Component & Service Alignment (Recognizes legitimate implementation details)
    hld_components = set(re.findall(r"([A-Za-z0-9]+(?:Service|Engine|Gateway|Manager|Worker|Controller|Cluster|Portal|Registry))", hld_text))
    generic_names = {"coreservice", "systemservice", "genericservice"}
    filtered_hld_comps = [c for c in hld_components if c.lower() not in generic_names and len(c) > 6]

    aligned_components = []
    missing_in_lld = []

    for comp in filtered_hld_comps:
        # Strip common architectural layer suffixes to find the domain stem
        comp_stem = re.sub(r"(Service|Engine|Gateway|Manager|Worker|Controller|Cluster|Portal|Registry)$", "", comp, flags=re.IGNORECASE).lower()
        if not comp_stem:
            comp_stem = comp.lower()

        # Legitimate implementation detail:
        # e.g., HLD: PaymentService -> LLD: PaymentServiceController, PaymentRepository, PaymentService
        # If the exact comp name, its stem, or a layered pattern (Stem + Controller/Repository/Service/Handler) appears in LLD:
        is_represented = (
            comp.lower() in lld_lower or
            comp_stem in lld_lower or
            re.search(rf"\b{re.escape(comp_stem)}(?:service|controller|repository|handler|worker|module|router)\b", lld_lower) is not None
        )

        if is_represented:
            aligned_components.append(comp)
        else:
            missing_in_lld.append(comp)

    if filtered_hld_comps and len(missing_in_lld) >= (len(filtered_hld_comps) * 0.5):
        issues.append(
            f"HLD defines key components ({', '.join(missing_in_lld[:4])}) that lack direct corresponding modules in LLD."
        )

    # 2. Material Contradiction: Persistence Technology
    relational_dbs = ["postgresql", "postgres", "mysql", "mariadb", "sqlite", "oracle", "sql server"]
    nosql_doc_dbs = ["mongodb", "couchdb", "documentdb"]

    hld_relational = any(db in hld_lower for db in relational_dbs)
    hld_nosql = any(db in hld_lower for db in nosql_doc_dbs)
    lld_relational = any(db in lld_lower for db in relational_dbs) or bool(re.search(r"CREATE\s+TABLE", lld_text, re.IGNORECASE))
    lld_nosql = any(db in lld_lower for db in nosql_doc_dbs)

    if (hld_relational and not hld_nosql) and (lld_nosql and not lld_relational):
        issues.append("Material Contradiction: HLD mandates relational persistence (PostgreSQL/SQL), but LLD specifies NoSQL document storage (MongoDB).")
    elif (hld_nosql and not hld_relational) and (lld_relational and not lld_nosql):
        issues.append("Material Contradiction: HLD mandates document storage (MongoDB), but LLD specifies relational SQL tables.")

    # 3. Material Contradiction: Messaging & Event Streaming Broker
    if "kafka" in hld_lower and "rabbitmq" in lld_lower and "kafka" not in lld_lower:
        issues.append("Material Contradiction: HLD specifies Apache Kafka event streaming, but LLD replaces it with RabbitMQ broker.")
    elif "rabbitmq" in hld_lower and "kafka" in lld_lower and "rabbitmq" not in lld_lower:
        issues.append("Material Contradiction: HLD specifies RabbitMQ message broker, but LLD replaces it with Apache Kafka.")

    # 4. Material Contradiction: Asynchronous Event-Driven vs Synchronous Execution
    hld_mandates_async = bool(re.search(r"asynchronous\s+(?:event|payment|processing|message|workflow)", hld_lower))
    lld_purely_sync = bool(re.search(r"synchronous\s+(?:rest-only|execution|only\s+rest)", lld_lower))
    if hld_mandates_async and lld_purely_sync:
        issues.append("Material Contradiction: HLD specifies asynchronous processing, but LLD defines purely synchronous REST execution.")

    # 5. Caching Technology Contradiction
    if "redis" in hld_lower and "memcached" in lld_lower and "redis" not in lld_lower:
        issues.append("Material Contradiction: HLD specifies Redis caching, but LLD replaces it with Memcached.")

    # 6. Check Major Domain Entity Continuity (from Stage 3)
    stages = (analysis_data or {}).get("stages") or {}
    if not isinstance(stages, dict):
        stages = {}
    stage3 = stages.get("stage3_data_api") or (analysis_data or {}).get("stage3_data_api") or {}
    er_raw = stage3.get("mermaid_er_diagram") or ""
    stage3_entities = re.findall(r"([A-Z0-9_]{3,})\s*\{", er_raw)

    if stage3_entities:
        missing_entities = [ent for ent in stage3_entities if ent.lower() not in lld_lower]
        if len(missing_entities) > (len(stage3_entities) * 0.5):
            warnings.append(
                f"Core domain entities from Stage 3 ({', '.join(missing_entities[:3])}) were omitted from LLD data models."
            )

    has_material_contradiction = any("Material Contradiction" in i for i in issues)

    score = 100.0 - (len(issues) * 25.0) - (len(warnings) * 10.0)
    score = max(0.0, min(100.0, score))

    if has_material_contradiction:
        status = "MATERIAL_CONTRADICTION"
    elif len(issues) > 0 or score < 70.0:
        status = "WARNING"
    else:
        status = "PASS"

    return {
        "status": status,
        "score": round(score, 1),
        "issues": issues,
        "warnings": warnings,
        "aligned_components": list(set(aligned_components)),
        "missing_in_lld": list(set(missing_in_lld))
    }


def build_architecture_traceability(
    analysis_data: Optional[Dict[str, Any]],
    hld_markdown: str,
    lld_markdown: str
) -> Dict[str, Any]:
    """
    Constructs an end-to-end traceability matrix:
    Stage 1 Requirements -> Stage 2/HLD Components -> Stage 3/LLD Data & APIs -> Stage 4/LLD Implementation

    Hierarchy of evidence:
    1. Explicit requirement ID/reference such as `[REQ-001]`. (High confidence)
    2. Explicit requirement-to-component link from structured Stage 2/3/4. (High confidence)
    3. Lexical matching against concrete service/component names or API endpoints. (Medium confidence)
    4. General text / summary overlap. (Low confidence / weak)
    5. No overlap: Unmapped (does not invent false trace relationships).
    """
    analysis_data = analysis_data or {}
    stages = analysis_data.get("stages") or {}
    if not isinstance(stages, dict):
        stages = {}

    stage1 = stages.get("stage1_requirements") or analysis_data.get("stage1_requirements") or {}
    stage2 = stages.get("stage2_architecture") or analysis_data.get("stage2_architecture") or {}
    stage3 = stages.get("stage3_data_api") or analysis_data.get("stage3_data_api") or {}
    stage4 = stages.get("stage4_implementation") or analysis_data.get("stage4_implementation") or {}

    has_any_stages = bool(stage1 or stage2 or stage3 or stage4)
    requirements = extract_requirements_from_stages(analysis_data)

    if not has_any_stages or not requirements:
        return {
            "status": "partial",
            "reason": "Legacy document - Stage 1-4 analysis unavailable or not populated",
            "total_requirements": len(requirements),
            "traceability_matrix": []
        }

    endpoints = stage3.get("api_endpoints", [])
    er_raw = stage3.get("mermaid_er_diagram") or ""
    entities = re.findall(r"([A-Z0-9_]{3,})\s*\{", er_raw)
    repo_structure = stage4.get("repository_structure") or ""
    hld_text = hld_markdown or ""
    lld_text = lld_markdown or ""

    # Catalog HLD components
    hld_comps = list(set(re.findall(r"([A-Za-z0-9_-]+\s*(?:Service|Engine|Gateway|Manager|Tier|Worker|Controller|Cluster))", hld_text, re.IGNORECASE)))

    matrix = []

    for req in requirements:
        req_id = req["id"]
        title = req["title"]
        keywords = req["keywords"]

        confidence = "none"
        trace_method = "untraced"
        status = "unmapped"

        hld_component = "Unmapped"
        lld_service = "N/A"
        mapped_endpoint = "N/A"
        mapped_entity = "N/A"

        # 1. Priority 1: Explicit Requirement ID match in HLD or LLD (e.g. [REQ-001] or REQ-001)
        id_pattern = rf"\[?{re.escape(req_id)}\]?"
        if re.search(id_pattern, hld_text, re.IGNORECASE) or re.search(id_pattern, lld_text, re.IGNORECASE):
            confidence = "high"
            trace_method = "explicit_id"
            status = "strong"

            # Find matching component near the ID
            for comp in hld_comps:
                if re.search(rf"{re.escape(comp)}[^\n]*{id_pattern}", hld_text, re.IGNORECASE) or re.search(rf"{id_pattern}[^\n]*{re.escape(comp)}", hld_text, re.IGNORECASE):
                    hld_component = comp.strip()
                    break
            if hld_component == "Unmapped" and hld_comps:
                hld_component = hld_comps[0].strip()

        # 2. Priority 2: Structured Stage 3 / Stage 4 direct match
        matched_ep = None
        best_ep_score = 0
        for ep in endpoints:
            if isinstance(ep, dict):
                ep_text = f"{ep.get('path', '')} {ep.get('purpose', '')} {ep.get('domain', '')}".lower()
                matching_kws = [kw for kw in keywords if kw in ep_text]
                if len(matching_kws) > best_ep_score:
                    best_ep_score = len(matching_kws)
                    matched_ep = f"{ep.get('method', 'GET')} {ep.get('path', '')}"

        matched_repo_file = None
        if repo_structure:
            for line in repo_structure.split("\n"):
                if ("/" in line or "." in line) and any(kw in line.lower() for kw in keywords):
                    matched_repo_file = line.strip().lstrip("├──└──│ ")
                    break

        if confidence == "none" and (matched_ep or matched_repo_file):
            confidence = "high"
            trace_method = "structured_stage"
            status = "strong"

        # 3. Priority 3: Lexical Matching against Concrete Services
        if hld_component == "Unmapped":
            for comp in hld_comps:
                comp_lower = comp.lower()
                matching_kws = [kw for kw in keywords if kw in comp_lower]
                if len(matching_kws) >= 1:
                    hld_component = comp.strip()
                    if confidence == "none":
                        confidence = "medium"
                        trace_method = "lexical_service"
                        status = "moderate"
                    break

        # Map LLD service
        if matched_repo_file:
            lld_service = matched_repo_file
        elif hld_component != "Unmapped":
            # Formulate LLD service from HLD component stem
            stem = re.sub(r"\s+", "", hld_component)
            lld_service = stem if stem.endswith("Service") else f"{stem}Service"

        # Map API Endpoint
        if matched_ep:
            mapped_endpoint = matched_ep
        elif endpoints and confidence in ["high", "medium"]:
            first_ep = endpoints[0]
            if isinstance(first_ep, dict):
                mapped_endpoint = f"{first_ep.get('method', 'GET')} {first_ep.get('path', '')}"

        # Map Data Entity
        mapped_entity = "N/A"
        best_ent_score = 0
        for ent in entities:
            ent_l = ent.lower()
            matching_kws = [kw for kw in keywords if kw in ent_l]
            if len(matching_kws) > best_ent_score:
                best_ent_score = len(matching_kws)
                mapped_entity = ent
        if mapped_entity == "N/A" and entities and confidence in ["high", "medium"]:
            mapped_entity = entities[0]

        # 4. Check for Weak/False Trace: If keywords only matched summary or minimal overlap
        if confidence == "none":
            # Check if keywords appear only in summary
            if any(kw in (hld_text or "").lower() for kw in keywords):
                confidence = "low"
                trace_method = "summary_fallback"
                status = "weak"
                hld_component = "Executive Summary"
            else:
                # Do NOT invent false trace!
                confidence = "none"
                trace_method = "untraced"
                status = "unmapped"

        matrix.append({
            "requirement_id": req_id,
            "requirement_title": title,
            "hld_component": hld_component,
            "lld_service": lld_service,
            "api_endpoint": mapped_endpoint,
            "data_entity": mapped_entity,
            "confidence": confidence,
            "trace_method": trace_method,
            "status": status
        })

    traced_count = sum(1 for m in matrix if m["status"] in ["strong", "moderate"])

    return {
        "status": "complete" if traced_count > 0 else "partial",
        "total_requirements": len(requirements),
        "total_traced": traced_count,
        "traceability_matrix": matrix
    }
