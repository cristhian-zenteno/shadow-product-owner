"""
Document Ingestion & RAG - Component D

Converts documents to Markdown, chunks them, embeds with sentence-transformers,
and stores in a per-feature Chroma vector database for retrieval.

This component depends on:
- Component A (workspace manager) - needs input/documents/ and input/meetings/
- Component B (privacy scrubber) - chunks must be scrubbed before indexing

Per-feature isolation: each workspace gets its own Chroma collection,
with zero cross-contamination between workspaces (tested explicitly).
"""

from pathlib import Path
from typing import Union, List, Optional
import hashlib
import logging

from markitdown import MarkItDown

# Configure logger
logger = logging.getLogger(__name__)


def convert_to_markdown(path: Union[str, Path]) -> str:
    """
    Convert a document to Markdown using MarkItDown.
    
    Per SPECIFY.md §2: This function only accepts paths from a feature's
    input/documents/ directory (never arbitrary paths). Caller must validate
    the path is within the expected workspace structure.
    
    Supported formats:
    - PDF (.pdf)
    - Word (.docx, .doc)
    - PowerPoint (.pptx, .ppt)
    - Excel (.xlsx, .xls)
    - Images with OCR (.png, .jpg, .jpeg)
    - HTML (.html)
    - Plain text (.txt, .md)
    
    Args:
        path: Path to document file (must be within workspace input/documents/)
        
    Returns:
        Clean Markdown text extracted from the document
        
    Raises:
        FileNotFoundError: If the file does not exist
        RuntimeError: If conversion fails
        
    Example:
        >>> from shadow_po import knowledge_base as kb
        >>> markdown = kb.convert_to_markdown("workspaces/feature/input/documents/spec.pdf")
        >>> print(markdown[:100])
        # Product Requirements
        
        ## Overview
        This document describes...
    """
    file_path = Path(path)
    
    if not file_path.exists():
        raise FileNotFoundError(
            f"Document not found: {path}\n"
            "Ensure the file exists before calling convert_to_markdown()."
        )
    
    logger.info(f"Converting document to Markdown: {file_path}")
    
    try:
        # Initialize MarkItDown converter
        md_converter = MarkItDown()
        
        # Convert the document
        result = md_converter.convert(str(file_path))
        
        # Extract text content from result
        markdown_text = result.text_content if hasattr(result, 'text_content') else str(result)
        
        if not markdown_text or not markdown_text.strip():
            logger.warning(
                f"Document conversion produced empty output: {file_path}\n"
                "The file may be empty, corrupted, or in an unsupported format."
            )
            return ""
        
        logger.info(
            f"Document converted successfully: {file_path} "
            f"({len(markdown_text)} characters)"
        )
        
        return markdown_text
        
    except Exception as e:
        raise RuntimeError(
            f"Failed to convert document {path} to Markdown: {str(e)}\n"
            "Ensure the file is a valid document format supported by MarkItDown."
        ) from e



def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[str]:
    """
    Split text into paragraph-sized chunks suitable for embedding and retrieval.
    
    Uses a simple but effective chunking strategy:
    - Split on double newlines (paragraphs) when possible
    - Fall back to sentence boundaries for very long paragraphs
    - Maintain some overlap between chunks to preserve context
    
    This function handles both very short documents (returns single chunk)
    and very long documents (splits appropriately without erroring).
    
    Args:
        text: Input text to chunk (Markdown from convert_to_markdown or transcript)
        chunk_size: Target size for each chunk in characters (default: 1000)
        chunk_overlap: Number of characters to overlap between chunks (default: 200)
        
    Returns:
        List of text chunks, each suitable for embedding
        Empty list if input text is empty
        
    Example:
        >>> text = "# Introduction\\n\\nThis is paragraph 1.\\n\\nThis is paragraph 2."
        >>> chunks = chunk_text(text, chunk_size=50)
        >>> len(chunks)
        3
    """
    if not text or not text.strip():
        return []
    
    # Normalize whitespace - replace multiple newlines with double newline
    text = text.strip()
    
    # Split on paragraph boundaries (double newlines)
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    
    if not paragraphs:
        return []
    
    chunks: List[str] = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        # If adding this paragraph would exceed chunk_size and we already have content
        if current_chunk and len(current_chunk) + len(paragraph) + 2 > chunk_size:
            # Save current chunk
            chunks.append(current_chunk.strip())
            
            # Start new chunk with overlap from previous chunk
            if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                # Take the last chunk_overlap characters as context
                overlap_text = current_chunk[-chunk_overlap:].strip()
                current_chunk = overlap_text + "\n\n" + paragraph
            else:
                current_chunk = paragraph
        else:
            # Add paragraph to current chunk
            if current_chunk:
                current_chunk += "\n\n" + paragraph
            else:
                current_chunk = paragraph
        
        # If a single paragraph is longer than chunk_size, split it further
        if len(current_chunk) > chunk_size * 2:
            # Split on sentence boundaries (. ! ?)
            sentences = []
            current_sentence = ""
            
            for char in current_chunk:
                current_sentence += char
                if char in '.!?' and len(current_sentence) > 50:
                    sentences.append(current_sentence.strip())
                    current_sentence = ""
            
            if current_sentence.strip():
                sentences.append(current_sentence.strip())
            
            # Rebuild chunks from sentences
            if sentences:
                chunks.append(current_chunk.strip())
                current_chunk = ""
                
                temp_chunk = ""
                for sentence in sentences:
                    if temp_chunk and len(temp_chunk) + len(sentence) > chunk_size:
                        chunks.append(temp_chunk.strip())
                        
                        # Add overlap
                        if chunk_overlap > 0 and len(temp_chunk) > chunk_overlap:
                            overlap_text = temp_chunk[-chunk_overlap:].strip()
                            temp_chunk = overlap_text + " " + sentence
                        else:
                            temp_chunk = sentence
                    else:
                        if temp_chunk:
                            temp_chunk += " " + sentence
                        else:
                            temp_chunk = sentence
                
                current_chunk = temp_chunk
    
    # Add the last chunk if there's remaining content
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # Handle edge case: if no chunks were created but we have text
    if not chunks and text.strip():
        chunks.append(text.strip())
    
    logger.info(
        f"Chunked text: {len(text)} characters → {len(chunks)} chunks "
        f"(avg {sum(len(c) for c in chunks) // len(chunks) if chunks else 0} chars/chunk)"
    )
    
    return chunks


# ---------------------------------------------------------------------------
# Embedding + Chroma vector store  (Task D-3)
# ---------------------------------------------------------------------------

# Global embedding model instance — loaded once, reused across calls
_embedding_model: Optional[object] = None
_embedding_model_name: Optional[str] = None


def _get_embedding_model(model_name: str):
    """
    Return the global sentence-transformers embedding model, loading it on
    first call.  Subsequent calls with the same model_name are free (cached).

    Args:
        model_name: HuggingFace model identifier,
                    e.g. "sentence-transformers/all-MiniLM-L6-v2"

    Returns:
        SentenceTransformer instance
    """
    global _embedding_model, _embedding_model_name

    if _embedding_model is None or _embedding_model_name != model_name:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed.  "
                "Run: uv add sentence-transformers"
            ) from exc

        logger.info(f"Loading embedding model: {model_name}")
        _embedding_model = SentenceTransformer(model_name)
        _embedding_model_name = model_name
        logger.info("Embedding model loaded")

    return _embedding_model


def _collection_name(workspace_path: Union[str, Path]) -> str:
    """
    Derive a stable, filesystem-safe Chroma collection name from a workspace
    path.  Chroma collection names must be 3-63 chars, start/end with a
    letter or digit, and contain only letters, digits, underscores, or hyphens.

    We use the workspace folder name (kebab-case), truncated and sanitised,
    then suffix a short hash to guarantee uniqueness even for long names.

    Args:
        workspace_path: Path to the feature workspace root

    Returns:
        Chroma-compatible collection name string
    """
    name = Path(workspace_path).name
    # Keep letters, digits, hyphens, underscores; replace everything else
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    short_hash = hashlib.md5(str(Path(workspace_path).resolve()).encode()).hexdigest()[:8]
    collection = f"{safe[:40]}_{short_hash}"
    # Ensure starts with a letter/digit (Chroma requirement)
    if not collection[0].isalnum():
        collection = "ws_" + collection
    return collection


def _get_chroma_client(db_path: Union[str, Path]):
    """
    Return a persistent Chroma client rooted at *db_path*.

    Args:
        db_path: Directory where Chroma will persist its data

    Returns:
        chromadb.PersistentClient instance
    """
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError(
            "chromadb is not installed.  Run: uv add chromadb"
        ) from exc

    db_path = Path(db_path)
    db_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(db_path))


def _chroma_db_path(workspace_path: Union[str, Path]) -> Path:
    """Return the path where Chroma persists data for this workspace."""
    return Path(workspace_path) / ".chroma"


class _SentenceTransformerEmbedder:
    """
    Thin adapter so we can pass sentence-transformers embeddings to Chroma
    without pulling in langchain-community in this module.

    Implements Chroma's EmbeddingFunction protocol fully:
    - __call__(input: list[str]) -> list[list[float]]   used by add/upsert
    - embed_documents(input)                            alias used by some Chroma paths
    - embed_query(input)                                used by collection.query()
    - name() -> str                                     required by chromadb >= 1.x
    """

    def __init__(self, model_name: str):
        self.model_name = model_name

    def name(self) -> str:
        return f"sentence-transformers:{self.model_name}"

    def _encode(self, input: List[str]) -> List[List[float]]:
        model = _get_embedding_model(self.model_name)
        vectors = model.encode(input, show_progress_bar=False)
        return [v.tolist() for v in vectors]

    def __call__(self, input: List[str]) -> List[List[float]]:   # noqa: A002
        return self._encode(input)

    def embed_documents(self, input: List[str]) -> List[List[float]]:  # noqa: A002
        return self._encode(input)

    def embed_query(self, input: List[str]) -> List[List[float]]:  # noqa: A002
        # Chroma passes a list with one query string; return same shape
        return self._encode(input)


def index_workspace_documents(
    workspace_path: Union[str, Path],
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> int:
    """
    Convert, chunk, scrub, embed, and store all documents in a workspace.

    Processes every file in ``input/documents/`` and every ``.txt`` /
    ``.md`` file in ``input/meetings/`` (pre-saved transcripts).

    Per PLAN.md Risk R3: text is scrubbed **before** chunks are stored,
    so raw secrets never enter the vector index.
    No network call is made during embedding — sentence-transformers runs
    entirely locally.

    Args:
        workspace_path: Path to the feature workspace root
        embedding_model: HuggingFace model name for local embeddings
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between adjacent chunks in characters

    Returns:
        Total number of chunks indexed

    Raises:
        FileNotFoundError: If the workspace does not exist
        RuntimeError: If privacy scrubber is not initialised
    """
    workspace = Path(workspace_path)

    if not workspace.exists():
        raise FileNotFoundError(
            f"Workspace not found: {workspace_path}\n"
            "Create it with workspace.create_workspace() first."
        )

    # Lazy import to avoid circular deps; scrubber must be initialised by caller
    from shadow_po import privacy

    if privacy._scrubber is None:
        raise RuntimeError(
            "Privacy scrubber not initialised.  "
            "Call privacy.initialize() before indexing documents."
        )

    # Collect all indexable files
    docs_dir = workspace / "input" / "documents"
    meetings_dir = workspace / "input" / "meetings"

    files_to_index: List[Path] = []

    if docs_dir.exists():
        # All files in documents/ — MarkItDown handles format detection
        files_to_index.extend([
            f for f in docs_dir.iterdir()
            if f.is_file() and not f.name.startswith(".")
        ])

    if meetings_dir.exists():
        # Only text transcripts in meetings/
        files_to_index.extend([
            f for f in meetings_dir.iterdir()
            if f.is_file() and f.suffix.lower() in {".txt", ".md"}
        ])

    if not files_to_index:
        logger.warning(f"No indexable files found in workspace: {workspace_path}")
        return 0

    # Set up Chroma collection
    embedder = _SentenceTransformerEmbedder(embedding_model)
    client = _get_chroma_client(_chroma_db_path(workspace))
    col_name = _collection_name(workspace)

    collection = client.get_or_create_collection(
        name=col_name,
        embedding_function=embedder,
        metadata={"workspace": str(workspace.resolve())},
    )

    total_chunks = 0

    for file_path in files_to_index:
        try:
            logger.info(f"Indexing file: {file_path}")

            # Convert to text
            if file_path.suffix.lower() in {".txt", ".md"}:
                raw_text = file_path.read_text(encoding="utf-8")
            else:
                raw_text = convert_to_markdown(file_path)

            if not raw_text.strip():
                logger.warning(f"Skipping empty file: {file_path}")
                continue

            # Scrub before chunking (Risk R3)
            scrubbed_text = privacy.scrub(raw_text)

            # Chunk
            chunks = chunk_text(scrubbed_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

            if not chunks:
                continue

            # Build stable IDs: hash(workspace + file + chunk_index)
            base_id = hashlib.md5(
                (str(workspace.resolve()) + str(file_path)).encode()
            ).hexdigest()

            ids = [f"{base_id}_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "source_file": file_path.name,
                    "workspace": str(workspace.resolve()),
                    "chunk_index": i,
                }
                for i in range(len(chunks))
            ]

            # Delete stale entries for this file before re-inserting
            existing = collection.get(where={"source_file": file_path.name})
            if existing and existing["ids"]:
                collection.delete(ids=existing["ids"])

            # Upsert chunks
            collection.add(documents=chunks, ids=ids, metadatas=metadatas)
            total_chunks += len(chunks)

            logger.info(f"Indexed {len(chunks)} chunks from: {file_path.name}")

        except Exception as e:
            logger.error(f"Failed to index {file_path}: {e}")
            raise RuntimeError(f"Indexing failed for {file_path}: {e}") from e

    logger.info(
        f"Indexing complete for workspace '{workspace.name}': "
        f"{total_chunks} total chunks from {len(files_to_index)} files"
    )

    return total_chunks


def reindex_file(
    workspace_path: Union[str, Path],
    file_path: Union[str, Path],
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> int:
    """
    Incrementally re-index a single file in the workspace Chroma collection.

    Only that file's chunks are replaced — all other files' chunks remain
    untouched.  This is used by Component H after ``answered-questions.md``
    is updated, avoiding a full workspace rebuild.

    Args:
        workspace_path: Path to the feature workspace root
        file_path: Path to the specific file to re-index
        embedding_model: HuggingFace model name for local embeddings
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between adjacent chunks in characters

    Returns:
        Number of new chunks indexed for this file

    Raises:
        FileNotFoundError: If workspace or file does not exist
        RuntimeError: If privacy scrubber is not initialised
    """
    workspace = Path(workspace_path)
    file_path = Path(file_path)

    if not workspace.exists():
        raise FileNotFoundError(f"Workspace not found: {workspace_path}")

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    from shadow_po import privacy

    if privacy._scrubber is None:
        raise RuntimeError(
            "Privacy scrubber not initialised.  "
            "Call privacy.initialize() before indexing."
        )

    # Convert / read file
    if file_path.suffix.lower() in {".txt", ".md"}:
        raw_text = file_path.read_text(encoding="utf-8")
    else:
        raw_text = convert_to_markdown(file_path)

    scrubbed_text = privacy.scrub(raw_text)
    chunks = chunk_text(scrubbed_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    embedder = _SentenceTransformerEmbedder(embedding_model)
    client = _get_chroma_client(_chroma_db_path(workspace))
    col_name = _collection_name(workspace)

    collection = client.get_or_create_collection(
        name=col_name,
        embedding_function=embedder,
        metadata={"workspace": str(workspace.resolve())},
    )

    # Remove old chunks for this file
    existing = collection.get(where={"source_file": file_path.name})
    if existing and existing["ids"]:
        collection.delete(ids=existing["ids"])
        logger.info(f"Removed {len(existing['ids'])} stale chunks for: {file_path.name}")

    if not chunks:
        logger.warning(f"No chunks produced from: {file_path}")
        return 0

    base_id = hashlib.md5(
        (str(workspace.resolve()) + str(file_path)).encode()
    ).hexdigest()

    ids = [f"{base_id}_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "source_file": file_path.name,
            "workspace": str(workspace.resolve()),
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]

    collection.add(documents=chunks, ids=ids, metadatas=metadatas)

    logger.info(f"Re-indexed {len(chunks)} chunks for: {file_path.name}")

    return len(chunks)


# ---------------------------------------------------------------------------
# Retrieval  (Task D-4)
# ---------------------------------------------------------------------------

def retrieve(
    workspace_path: Union[str, Path],
    query: str,
    k: int = 5,
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> List[str]:
    """
    Query the per-feature Chroma index and return the top-k relevant chunks.

    Only the index scoped to *this* workspace is queried — chunks from other
    workspaces are structurally unreachable (per-feature collection isolation).

    The query string is scrubbed before embedding so no PII leaves the machine
    even as a vector-space query.

    Args:
        workspace_path: Path to the feature workspace root
        query: Natural-language question or search phrase
        k: Number of top chunks to return (default: 5)
        embedding_model: HuggingFace model name used at indexing time

    Returns:
        List of up to k text chunks, ordered by relevance (most relevant first).
        Returns an empty list if the workspace has no indexed content.

    Raises:
        FileNotFoundError: If the workspace does not exist
        RuntimeError: If privacy scrubber is not initialised

    Example:
        >>> from shadow_po import knowledge_base as kb
        >>> chunks = kb.retrieve("workspaces/1-click-checkout", "What is the payment flow?")
        >>> for chunk in chunks:
        ...     print(chunk[:80])
    """
    workspace = Path(workspace_path)

    if not workspace.exists():
        raise FileNotFoundError(f"Workspace not found: {workspace_path}")

    from shadow_po import privacy

    if privacy._scrubber is None:
        raise RuntimeError(
            "Privacy scrubber not initialised. "
            "Call privacy.initialize() before calling retrieve()."
        )

    # Scrub the query before it becomes an embedding vector
    scrubbed_query = privacy.scrub(query)

    db_path = _chroma_db_path(workspace)

    # If the workspace has never been indexed there is no .chroma dir yet
    if not db_path.exists():
        logger.warning(
            f"No index found for workspace '{workspace.name}'. "
            "Run index_workspace_documents() first."
        )
        return []

    client = _get_chroma_client(db_path)
    col_name = _collection_name(workspace)

    # Collection may not exist if indexing was never run
    try:
        collection = client.get_collection(
            name=col_name,
            embedding_function=_SentenceTransformerEmbedder(embedding_model),
        )
    except Exception:
        logger.warning(
            f"Collection '{col_name}' not found for workspace '{workspace.name}'. "
            "Run index_workspace_documents() first."
        )
        return []

    total_docs = collection.count()
    if total_docs == 0:
        return []

    # Clamp k to the number of available docs to avoid Chroma errors
    effective_k = min(k, total_docs)

    results = collection.query(
        query_texts=[scrubbed_query],
        n_results=effective_k,
    )

    # results["documents"] is a list-of-lists (one list per query)
    chunks: List[str] = results["documents"][0] if results["documents"] else []

    logger.info(
        f"Retrieved {len(chunks)} chunks for workspace '{workspace.name}' "
        f"(query: '{scrubbed_query[:60]}...')"
    )

    return chunks
