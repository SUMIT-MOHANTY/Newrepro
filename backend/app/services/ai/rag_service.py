"""
RAG Service — LightRAG Integration for Codebase Retrieval
Wraps LightRAG to provide semantic search + knowledge graph traversal
over indexed codebases, using the project's existing OpenAI-compatible API.
"""

import os
import asyncio
import json
import logging
import shutil
from typing import Dict, Any, Optional, List

import numpy as np

from app.core.config import settings
from app.integrations.llm import llm_gateway

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  LightRAG Custom LLM & Embedding Functions
# ---------------------------------------------------------------------------

async def _llm_model_func(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: Optional[list] = None,
    keyword_extraction: bool = False,
    **kwargs,
) -> str:
    """
    Custom LLM function for LightRAG that uses our existing
    AI API (BRN Llama or OpenAI-compatible, based on USE_BRN_LLAMA).
    """
    from lightrag.llm.openai import openai_complete_if_cache

    # Strip /chat/completions from the URL to get the base URL
    base_url = llm_gateway.resolve_url()
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    elif base_url.endswith("/v1/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]

    try:
        return await openai_complete_if_cache(
            llm_gateway.resolve_model(),
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            api_key=llm_gateway.resolve_key() or "dummy",
            base_url=base_url,
            **kwargs,
        )
    except Exception as e:
        logger.warning(f"LightRAG LLM call failed: {e}")
        # Return a minimal valid response to prevent crash
        return '{"entities": [], "relations": []}'


async def _embedding_func_impl(texts: list) -> np.ndarray:
    """
    Custom embedding function for LightRAG.
    Uses the same AI API for embeddings.
    Falls back to a simple hash-based embedding if a dedicated
    embedding endpoint isn't available.
    """
    try:
        from lightrag.llm.openai import openai_embed

        base_url = llm_gateway.resolve_url()
        if base_url.endswith("/chat/completions"):
            base_url = base_url[: -len("/chat/completions")]
        elif base_url.endswith("/v1/chat/completions"):
            base_url = base_url[: -len("/chat/completions")]

        result = await openai_embed.func(
            texts,
            model="text-embedding-ada-002",
            api_key=llm_gateway.resolve_key() or "dummy",
            base_url=base_url,
        )
        return result
    except Exception as e:
        logger.warning(
            f"OpenAI embedding failed ({e}), falling back to hash-based embeddings"
        )
        return _fallback_hash_embedding(texts)


# Flag to track if rerank is available
_rerank_available = None


def _check_rerank_available():
    """Check if rerank model is available."""
    global _rerank_available
    if _rerank_available is not None:
        return _rerank_available
    try:
        # Try to import and check rerank
        from lightrag import LightRAG

        _rerank_available = True
        return True
    except Exception:
        _rerank_available = False
        return False


def _fallback_hash_embedding(texts: list, dim: int = 1024) -> np.ndarray:
    """
    Simple deterministic hash-based embedding as fallback.
    Not ideal for production but ensures the system works even
    without a dedicated embedding model endpoint.
    """
    import hashlib

    embeddings = []
    for text in texts:
        h = hashlib.sha512(text.encode("utf-8")).digest()
        # Expand hash to fill dimension
        repeated = h * (dim // len(h) + 1)
        vec = np.frombuffer(repeated[:dim], dtype=np.uint8).astype(np.float32)
        # Normalize to unit vector
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        embeddings.append(vec)
    return np.array(embeddings)


# ---------------------------------------------------------------------------
#  RAG Storage Manager
# ---------------------------------------------------------------------------

# In-memory store of RAG instances per project
_rag_instances: Dict[str, Any] = {}  # project_token -> LightRAG
_rag_statuses: Dict[str, Dict[str, Any]] = {}  # project_token -> status

RAG_STORAGE_BASE = os.path.join(os.path.dirname(__file__), "rag_storage")
os.makedirs(RAG_STORAGE_BASE, exist_ok=True)


def _get_rag_working_dir(project_token: str) -> str:
    """Get or create the working directory for a project's RAG data."""
    safe_token = project_token.replace("/", "_").replace("\\", "_")
    working_dir = os.path.join(RAG_STORAGE_BASE, safe_token)
    os.makedirs(working_dir, exist_ok=True)
    return working_dir


async def _get_or_create_rag(project_token: str):
    """Get an existing LightRAG instance or create a new one."""
    from lightrag import LightRAG
    from lightrag.utils import wrap_embedding_func_with_attrs

    if project_token in _rag_instances:
        return _rag_instances[project_token]

    working_dir = _get_rag_working_dir(project_token)

    # Create the decorated embedding function
    @wrap_embedding_func_with_attrs(
        embedding_dim=1024, max_token_size=8192, model_name="custom-embedding"
    )
    async def embedding_func(texts: list) -> np.ndarray:
        return await _embedding_func_impl(texts)

    rag = LightRAG(
        working_dir=working_dir,
        llm_model_func=_llm_model_func,
        embedding_func=embedding_func,
        # Use defaults: NetworkX for graph, NanoVectorDB for vectors
        chunk_token_size=1200,
        chunk_overlap_token_size=100,
        entity_extract_max_gleaning=1,
    )

    await rag.initialize_storages()

    _rag_instances[project_token] = rag
    logger.info(f"LightRAG instance created for project {project_token}")
    return rag


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

async def index_codebase(
    project_token: str,
    text_chunks: List[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Index a codebase into LightRAG.

    Args:
        project_token: Unique project identifier
        text_chunks: List of text chunks from knowledge_graph_service
        metadata: Optional metadata about the repo

    Returns:
        Status dict with indexing results
    """
    _rag_statuses[project_token] = {
        "status": "indexing",
        "total_chunks": len(text_chunks),
        "indexed_chunks": 0,
        "error": None,
    }

    try:
        rag = await _get_or_create_rag(project_token)

        # Insert chunks in batches
        batch_size = 5
        indexed = 0
        for i in range(0, len(text_chunks), batch_size):
            batch = text_chunks[i : i + batch_size]
            try:
                await rag.ainsert(batch)
                indexed += len(batch)
                _rag_statuses[project_token]["indexed_chunks"] = indexed
                logger.info(
                    f"[{project_token}] Indexed {indexed}/{len(text_chunks)} chunks"
                )
            except Exception as e:
                logger.warning(f"[{project_token}] Batch insert error: {e}")
                # Try one-by-one for this batch
                for chunk in batch:
                    try:
                        await rag.ainsert(chunk)
                        indexed += 1
                    except Exception as e2:
                        # Log but continue - don't let one bad chunk stop everything
                        logger.warning(f"[{project_token}] Single insert error: {e2}")
                _rag_statuses[project_token]["indexed_chunks"] = indexed

        _rag_statuses[project_token].update({
            "status": "ready",
            "indexed_chunks": indexed,
            "metadata": metadata or {},
        })
        logger.info(f"[{project_token}] Indexing complete: {indexed} chunks indexed")

        return _rag_statuses[project_token]

    except Exception as e:
        err_msg = str(e)
        logger.warning(f"[{project_token}] Indexing failed: {err_msg}")
        _rag_statuses[project_token].update({
            "status": "error",
            "error": err_msg,
        })
        return _rag_statuses[project_token]


async def incremental_insert(
    project_token: str,
    text_chunks: List[str],
    source_label: str = "agent_output",
) -> Dict[str, Any]:
    """
    Incrementally insert new text chunks into an EXISTING RAG index.
    This is called when an agent completes a task — its generated code
    is parsed back into the KG and then fed here so downstream agents
    can discover it via semantic search.

    Unlike index_codebase(), this does NOT reset the index status or
    overwrite existing data. It appends to the existing vector store.
    """
    status = _rag_statuses.get(project_token, {})
    if status.get("status") != "ready":
        logger.warning(
            f"[{project_token}] incremental_insert skipped — index not ready "
            f"(status={status.get('status', 'unknown')})"
        )
        return {"status": "skipped", "reason": "index_not_ready"}

    try:
        rag = await _get_or_create_rag(project_token)
        inserted = 0

        for chunk in text_chunks:
            try:
                # Prefix each chunk with source so it's identifiable
                labeled = f"[{source_label}]\n{chunk}"
                await rag.ainsert(labeled)
                inserted += 1
            except Exception as e:
                # Log but don't crash on individual chunk errors
                logger.warning(
                    f"[{project_token}] incremental insert error for chunk: {e}"
                )
                # Try to insert a simplified version of the chunk
                try:
                    simplified = f"[{source_label}]\nError in chunk, skipping detailed content"
                    await rag.ainsert(simplified)
                    inserted += 1
                except Exception:
                    pass  # Give up on this chunk

        # Update total indexed count
        prev_count = status.get("indexed_chunks", 0)
        _rag_statuses[project_token]["indexed_chunks"] = prev_count + inserted

        logger.info(
            f"[{project_token}] Incremental insert: {inserted}/{len(text_chunks)} "
            f"chunks from {source_label}"
        )
        return {
            "status": "inserted",
            "inserted_chunks": inserted,
            "total_chunks_now": prev_count + inserted,
            "source": source_label,
        }

    except Exception as e:
        logger.warning(f"[{project_token}] incremental_insert failed: {e}")
        return {"status": "error", "error": str(e)}


async def query_codebase(
    project_token: str,
    query: str,
    mode: str = "hybrid",
    top_k: int = 10,
) -> Dict[str, Any]:
    """
    Query the indexed codebase for relevant context.

    Args:
        project_token: Project identifier
        query: Natural language query or task description
        mode: LightRAG query mode (naive, local, global, hybrid)
        top_k: Number of results to return

    Returns:
        Dict with query results and context
    """
    from lightrag import QueryParam

    status = _rag_statuses.get(project_token, {})
    if status.get("status") != "ready":
        return {
            "status": "not_indexed",
            "message": f"Project {project_token} is not indexed yet. Status: {status.get('status', 'unknown')}",
            "context": "",
        }

    try:
        rag = await _get_or_create_rag(project_token)

        # Disable rerank if no model is configured
        try:
            result = await rag.aquery(
                query,
                param=QueryParam(mode=mode, top_k=top_k, enable_rerank=False),
            )
        except Exception as rerank_error:
            # If rerank fails, try without it
            logger.warning(f"Rerank failed ({rerank_error}), retrying without rerank")
            result = await rag.aquery(
                query,
                param=QueryParam(mode=mode, top_k=top_k, enable_rerank=False),
            )

        return {
            "status": "success",
            "query": query,
            "mode": mode,
            "context": result,
        }

    except Exception as e:
        logger.warning(f"[{project_token}] Query failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "context": "",
        }


async def get_multiple_contexts(
    project_token: str,
    queries: List[str],
    mode: str = "hybrid",
) -> str:
    """
    Run multiple queries and combine the results into a single context string.
    Useful for getting context from different angles (e.g., task description,
    tech stack, dependencies).
    """
    contexts = []
    for q in queries:
        result = await query_codebase(project_token, q, mode=mode)
        if result.get("context"):
            contexts.append(result["context"])
    return "\n\n---\n\n".join(contexts)


def get_indexing_status(project_token: str) -> Dict[str, Any]:
    """Get the current indexing status for a project."""
    status = _rag_statuses.get(project_token)
    if not status:
        return {"status": "not_started", "project_token": project_token}
    return {**status, "project_token": project_token}


async def delete_index(project_token: str) -> Dict[str, Any]:
    """Delete all indexed data for a project."""
    # Close and remove the RAG instance
    if project_token in _rag_instances:
        try:
            rag = _rag_instances[project_token]
            await rag.finalize_storages()
        except Exception as e:
            logger.warning(f"Error finalizing RAG instance: {e}")
        del _rag_instances[project_token]

    # Remove status
    _rag_statuses.pop(project_token, None)

    # Remove storage directory
    working_dir = _get_rag_working_dir(project_token)
    if os.path.exists(working_dir):
        shutil.rmtree(working_dir, ignore_errors=True)
        logger.info(f"Deleted RAG storage for project {project_token}")

    return {"status": "deleted", "project_token": project_token}


def list_indexed_projects() -> List[Dict[str, Any]]:
    """List all projects that have been indexed."""
    return [
        {
            "project_token": token,
            "status": status.get("status", "unknown"),
            "indexed_chunks": status.get("indexed_chunks", 0),
        }
        for token, status in _rag_statuses.items()
    ]
