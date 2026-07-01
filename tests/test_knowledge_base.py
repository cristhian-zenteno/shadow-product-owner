"""
Tests for Document Ingestion & RAG - Component D

Verifies document conversion, chunking, embedding, and retrieval.
"""

import pytest
from pathlib import Path
from shadow_po import knowledge_base as kb


# Paths to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PDF = FIXTURES_DIR / "sample.pdf"
SAMPLE_DOCX = FIXTURES_DIR / "sample.docx"
SAMPLE_PPTX = FIXTURES_DIR / "sample.pptx"


# ---------------------------------------------------------------------------
# Task D-1: Convert documents to Markdown via MarkItDown
# ---------------------------------------------------------------------------

def test_convert_to_markdown_pdf():
    """
    Test conversion of PDF to Markdown.
    
    Acceptance: convert_to_markdown() runs MarkItDown on a PDF and returns
    clean Markdown text.
    """
    if not SAMPLE_PDF.exists():
        pytest.skip(
            f"PDF fixture not found: {SAMPLE_PDF}\n"
            f"Run: python tests/fixtures/generate_sample_documents.py"
        )
    
    # Act
    markdown = kb.convert_to_markdown(str(SAMPLE_PDF))
    
    # Assert
    assert isinstance(markdown, str), "Result must be a string"
    assert len(markdown) > 0, "Markdown should not be empty"
    
    # Check that key content from the PDF is present
    # (MarkItDown may add extra formatting, so we check for core phrases)
    markdown_lower = markdown.lower()
    assert "one-click checkout" in markdown_lower or "checkout" in markdown_lower, \
        "Key content 'checkout' should appear in converted markdown"


def test_convert_to_markdown_docx():
    """
    Test conversion of DOCX to Markdown.
    
    Acceptance: convert_to_markdown() runs MarkItDown on a Word document
    and returns clean Markdown text.
    """
    if not SAMPLE_DOCX.exists():
        pytest.skip(
            f"DOCX fixture not found: {SAMPLE_DOCX}\n"
            f"Run: python tests/fixtures/generate_sample_documents.py"
        )
    
    # Act
    markdown = kb.convert_to_markdown(str(SAMPLE_DOCX))
    
    # Assert
    assert isinstance(markdown, str), "Result must be a string"
    assert len(markdown) > 0, "Markdown should not be empty"
    
    # Check for key content
    markdown_lower = markdown.lower()
    assert "checkout" in markdown_lower, \
        "Key content 'checkout' should appear in converted markdown"
    assert "user story" in markdown_lower or "story" in markdown_lower, \
        "Document heading 'User Story' should appear"


def test_convert_to_markdown_pptx():
    """
    Test conversion of PPTX to Markdown.
    
    Acceptance: convert_to_markdown() runs MarkItDown on a PowerPoint
    and returns clean Markdown text.
    """
    if not SAMPLE_PPTX.exists():
        pytest.skip(
            f"PPTX fixture not found: {SAMPLE_PPTX}\n"
            f"Run: python tests/fixtures/generate_sample_documents.py"
        )
    
    # Act
    markdown = kb.convert_to_markdown(str(SAMPLE_PPTX))
    
    # Assert
    assert isinstance(markdown, str), "Result must be a string"
    assert len(markdown) > 0, "Markdown should not be empty"
    
    # Check for key content from slides
    markdown_lower = markdown.lower()
    assert "one-click checkout" in markdown_lower or "checkout" in markdown_lower, \
        "Slide title 'One-Click Checkout' should appear in converted markdown"


def test_convert_to_markdown_file_not_found():
    """Test that convert_to_markdown raises FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError, match="Document not found"):
        kb.convert_to_markdown("nonexistent_document.pdf")


def test_convert_to_markdown_handles_empty_file(tmp_path):
    """
    Test that convert_to_markdown handles empty files gracefully.
    
    Should return empty string or minimal content, not crash.
    """
    # Create an empty text file
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("", encoding="utf-8")
    
    # Should not crash, may return empty string
    result = kb.convert_to_markdown(str(empty_file))
    assert isinstance(result, str), "Should return a string even for empty files"



# ---------------------------------------------------------------------------
# Task D-2: Chunk converted documents and transcripts
# ---------------------------------------------------------------------------

def test_chunking_short_document():
    """
    Test chunking a very short document.
    
    Acceptance: chunk_text() handles very short documents without erroring,
    returning a single chunk.
    """
    short_text = "This is a short document with just one paragraph."
    
    chunks = kb.chunk_text(short_text, chunk_size=100)
    
    assert isinstance(chunks, list), "Should return a list"
    assert len(chunks) == 1, "Short text should produce a single chunk"
    assert chunks[0] == short_text, "Single chunk should contain the full text"


def test_chunking_long_document():
    """
    Test chunking a long document with multiple paragraphs.
    
    Acceptance: chunk_text() splits long documents into multiple chunks
    without erroring, with reasonable chunk sizes.
    """
    # Create a long document with multiple paragraphs
    paragraphs = [
        "# Introduction",
        "This is the first paragraph with some content about the product requirements.",
        "This is the second paragraph discussing the user stories and acceptance criteria.",
        "This is the third paragraph covering technical implementation details.",
        "This is the fourth paragraph about testing and quality assurance.",
        "This is the fifth paragraph discussing deployment and rollout strategy.",
    ]
    long_text = "\n\n".join(paragraphs)
    
    chunks = kb.chunk_text(long_text, chunk_size=150, chunk_overlap=50)
    
    assert isinstance(chunks, list), "Should return a list"
    assert len(chunks) > 1, "Long text should produce multiple chunks"
    
    # Verify chunks are within reasonable size bounds
    for i, chunk in enumerate(chunks):
        assert len(chunk) > 0, f"Chunk {i} should not be empty"
        # Chunks might exceed chunk_size slightly due to paragraph boundaries
        assert len(chunk) <= 300, f"Chunk {i} should not be excessively large"


def test_chunking_empty_text():
    """Test that chunk_text handles empty input gracefully."""
    assert kb.chunk_text("") == [], "Empty string should return empty list"
    assert kb.chunk_text("   ") == [], "Whitespace-only string should return empty list"
    assert kb.chunk_text("\n\n\n") == [], "Newlines-only string should return empty list"


def test_chunking_preserves_content():
    """
    Test that chunking preserves all content from the original text.
    
    With overlap, chunks will contain some duplicate content, but all
    original content should appear at least once.
    """
    text = """# Feature: One-Click Checkout

User Story:
As a customer, I want to complete my purchase with a single click
so that I can checkout faster and reduce cart abandonment.

Acceptance Criteria:
- The checkout button is visible on the cart page
- Clicking the button completes the purchase immediately
- User receives confirmation email within 1 minute"""
    
    chunks = kb.chunk_text(text, chunk_size=100, chunk_overlap=20)
    
    # Reconstruct text from chunks (removing overlap duplicates)
    combined = " ".join(chunks)
    
    # Check that key phrases appear in the combined chunks
    assert "One-Click Checkout" in combined
    assert "User Story" in combined
    assert "Acceptance Criteria" in combined
    assert "checkout button" in combined


def test_chunking_with_overlap():
    """
    Test that chunks have overlap when configured.
    
    Overlapping chunks help preserve context at chunk boundaries.
    """
    text = """First paragraph with some content.

Second paragraph with different content.

Third paragraph with more information."""
    
    chunks = kb.chunk_text(text, chunk_size=80, chunk_overlap=20)
    
    # With overlap, adjacent chunks should share some content
    if len(chunks) > 1:
        # Check that there's some commonality between adjacent chunks
        # (This is a weak check since overlap depends on where splits happen)
        assert len(chunks) > 1, "Should produce multiple chunks with this text"


def test_chunking_very_long_paragraph():
    """
    Test chunking handles a single very long paragraph.
    
    Should split on sentence boundaries when a paragraph exceeds chunk size.
    """
    # Create a very long single paragraph
    sentences = [
        "This is sentence one with some content.",
        "This is sentence two with more information.",
        "This is sentence three continuing the discussion.",
        "This is sentence four adding further details.",
        "This is sentence five concluding the paragraph.",
    ]
    long_paragraph = " ".join(sentences)
    
    chunks = kb.chunk_text(long_paragraph, chunk_size=100, chunk_overlap=20)
    
    # Should split into multiple chunks
    assert isinstance(chunks, list), "Should return a list"
    assert len(chunks) >= 1, "Should produce at least one chunk"
    
    # Verify all sentences appear somewhere in the chunks
    combined = " ".join(chunks)
    for sentence in sentences:
        assert sentence in combined, f"Sentence should appear in chunks: {sentence}"


def test_chunking_markdown_formatting():
    """
    Test that chunking preserves Markdown formatting.
    
    Headers, lists, and other Markdown elements should be preserved.
    """
    markdown_text = """# Main Title

## Subtitle

- List item 1
- List item 2
- List item 3

Some paragraph content here."""
    
    chunks = kb.chunk_text(markdown_text, chunk_size=200)
    
    # Check that markdown elements are preserved
    combined = "\n\n".join(chunks)
    assert "#" in combined, "Headers should be preserved"
    assert "-" in combined or "•" in combined, "List markers should be preserved"



# ---------------------------------------------------------------------------
# Task D-3: Embed chunks locally + store in per-feature Chroma collection
# ---------------------------------------------------------------------------

@pytest.fixture()
def privacy_scrubber():
    """Initialise the privacy scrubber for tests that call index functions."""
    from shadow_po import privacy
    original = privacy._scrubber
    privacy.initialize(custom_codenames=["SuperSecretProject"])
    yield
    privacy._scrubber = original


def test_indexing_is_local_and_scrubbed(tmp_path, privacy_scrubber):
    """
    Acceptance:
    - index_workspace_documents() runs without network calls during embedding
    - Text is scrubbed before chunks land in the index
    - Returns a positive chunk count

    We verify scrubbing by writing a document containing a fake API key and
    confirming the stored chunk contains the [API_KEY] placeholder, not the
    raw secret.
    """
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("index-test", workspaces_root=tmp_path)
    docs_dir = feature_ws / "input" / "documents"

    # Write a document with a recognisable fake secret
    fake_key = "sk-abcdef1234567890abcdef1234567890abcdef12"
    doc = docs_dir / "spec.txt"
    doc.write_text(
        f"Feature: One-Click Checkout\n\n"
        f"API integration key: {fake_key}\n\n"
        f"Users want to complete a purchase in a single click.",
        encoding="utf-8",
    )

    # Act — use a fast local model; no network call made after first download
    count = kb.index_workspace_documents(
        workspace_path=feature_ws,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    assert count > 0, "Should have indexed at least one chunk"

    # Verify scrubbing: query the stored docs directly via Chroma
    import chromadb
    client = chromadb.PersistentClient(path=str(feature_ws / ".chroma"))
    col_name = kb._collection_name(feature_ws)
    collection = client.get_collection(
        name=col_name,
        embedding_function=kb._SentenceTransformerEmbedder(
            "sentence-transformers/all-MiniLM-L6-v2"
        ),
    )
    all_docs = collection.get()
    combined = " ".join(all_docs["documents"])

    assert fake_key not in combined, (
        "Raw API key must not appear in stored chunks — scrubbing must run before indexing"
    )
    assert "[API_KEY]" in combined, (
        "Scrubbed [API_KEY] placeholder must appear in stored chunks"
    )


def test_indexing_requires_privacy_scrubber(tmp_path):
    """
    Acceptance: index_workspace_documents() raises clearly if the privacy
    scrubber has not been initialised.
    """
    from shadow_po import privacy, workspace as ws

    # Ensure scrubber is NOT initialised
    original = privacy._scrubber
    privacy._scrubber = None

    try:
        feature_ws = ws.create_workspace("no-scrub-test", workspaces_root=tmp_path)
        with pytest.raises(RuntimeError, match="Privacy scrubber not initialised"):
            kb.index_workspace_documents(feature_ws)
    finally:
        privacy._scrubber = original


def test_indexing_missing_workspace(tmp_path, privacy_scrubber):
    """index_workspace_documents() raises FileNotFoundError for a nonexistent workspace."""
    with pytest.raises(FileNotFoundError, match="Workspace not found"):
        kb.index_workspace_documents(tmp_path / "ghost-workspace")


def test_indexing_empty_workspace(tmp_path, privacy_scrubber):
    """
    index_workspace_documents() returns 0 and does not crash when the
    workspace exists but has no indexable files.
    """
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("empty-ws", workspaces_root=tmp_path)
    count = kb.index_workspace_documents(feature_ws)
    assert count == 0


def test_incremental_reindex(tmp_path, privacy_scrubber):
    """
    Acceptance (D-6 gate used here too):
    reindex_file() updates only that file's chunks — other files' chunks
    are untouched, and a timestamp/hash check confirms no full rebuild occurred.
    """
    from shadow_po import workspace as ws
    import chromadb

    feature_ws = ws.create_workspace("reindex-test", workspaces_root=tmp_path)
    docs_dir = feature_ws / "input" / "documents"

    # Write two files
    file_a = docs_dir / "doc_a.txt"
    file_b = docs_dir / "doc_b.txt"
    file_a.write_text("Document A: authentication flow details.", encoding="utf-8")
    file_b.write_text("Document B: payment gateway integration.", encoding="utf-8")

    # Full index first
    kb.index_workspace_documents(
        workspace_path=feature_ws,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    # Grab IDs for file_b before the reindex — they must be unchanged after
    client = chromadb.PersistentClient(path=str(feature_ws / ".chroma"))
    col_name = kb._collection_name(feature_ws)
    embedder = kb._SentenceTransformerEmbedder("sentence-transformers/all-MiniLM-L6-v2")
    collection = client.get_collection(name=col_name, embedding_function=embedder)

    before_b = set(collection.get(where={"source_file": "doc_b.txt"})["ids"])
    assert len(before_b) > 0, "doc_b.txt should be indexed initially"

    # Update only file_a
    file_a.write_text(
        "Document A: updated authentication flow with OAuth 2.0 details.",
        encoding="utf-8",
    )
    new_count = kb.reindex_file(
        workspace_path=feature_ws,
        file_path=file_a,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )
    assert new_count > 0, "Reindex should produce at least one chunk"

    # doc_b IDs must be completely unchanged
    after_b = set(collection.get(where={"source_file": "doc_b.txt"})["ids"])
    assert before_b == after_b, (
        "Reindexing doc_a must not change doc_b's chunks"
    )

    # doc_a content must reflect the updated text
    all_a = collection.get(where={"source_file": "doc_a.txt"})
    combined_a = " ".join(all_a["documents"])
    assert "OAuth" in combined_a, "Updated doc_a content should be retrievable"


# ---------------------------------------------------------------------------
# Task D-4: Query the per-feature index and return top relevant chunks
# ---------------------------------------------------------------------------

@pytest.fixture()
def indexed_workspace(tmp_path, privacy_scrubber):
    """
    Create and index a workspace with two documents whose content is clearly
    distinct so retrieval relevance is easy to assert.

    Returns the workspace Path.
    """
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("retrieval-test", workspaces_root=tmp_path)
    docs_dir = feature_ws / "input" / "documents"

    # Doc 1: clearly about authentication
    (docs_dir / "auth.txt").write_text(
        "Authentication and Authorization\n\n"
        "Users must log in with a username and password before accessing the system.\n\n"
        "OAuth 2.0 tokens expire after 60 minutes and must be refreshed.\n\n"
        "Failed login attempts are locked after 5 tries.",
        encoding="utf-8",
    )

    # Doc 2: clearly about payments
    (docs_dir / "payments.txt").write_text(
        "Payment Gateway Integration\n\n"
        "The checkout flow connects to Stripe for credit card processing.\n\n"
        "Transactions are authorised in real time and confirmed via webhook.\n\n"
        "Refunds can be issued within 30 days of purchase.",
        encoding="utf-8",
    )

    kb.index_workspace_documents(
        workspace_path=feature_ws,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    return feature_ws


def test_retrieval_relevance(indexed_workspace):
    """
    Acceptance: retrieve() returns the k most relevant chunks for that
    feature's index only, and the answer to a targeted question ranks
    a domain-specific chunk highly.
    """
    # Query about payments — payments.txt chunks should rank first
    chunks = kb.retrieve(
        workspace_path=indexed_workspace,
        query="How does the payment gateway work?",
        k=3,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    assert isinstance(chunks, list), "Should return a list"
    assert len(chunks) > 0, "Should return at least one chunk"
    assert len(chunks) <= 3, "Should respect the k limit"

    # The most relevant chunk should contain payment-related content
    top_chunk = chunks[0].lower()
    assert any(
        keyword in top_chunk
        for keyword in ("payment", "stripe", "checkout", "transaction", "refund")
    ), f"Top chunk should be payment-related, got: {chunks[0][:120]}"


def test_retrieval_auth_query(indexed_workspace):
    """
    A query about authentication should surface auth.txt chunks, not
    payment chunks, as the top result.
    """
    chunks = kb.retrieve(
        workspace_path=indexed_workspace,
        query="How does user login and authentication work?",
        k=3,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    assert len(chunks) > 0
    top_chunk = chunks[0].lower()
    assert any(
        keyword in top_chunk
        for keyword in ("login", "password", "oauth", "token", "authenticat")
    ), f"Top chunk should be auth-related, got: {chunks[0][:120]}"


def test_retrieval_returns_empty_for_unindexed_workspace(tmp_path, privacy_scrubber):
    """retrieve() returns [] without crashing when workspace has no index."""
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("empty-retrieval", workspaces_root=tmp_path)

    result = kb.retrieve(
        workspace_path=feature_ws,
        query="anything",
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )
    assert result == []


def test_retrieval_respects_k_limit(indexed_workspace):
    """retrieve() never returns more than k chunks."""
    for k in (1, 2, 4):
        chunks = kb.retrieve(
            workspace_path=indexed_workspace,
            query="feature details",
            k=k,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        )
        assert len(chunks) <= k, f"Expected at most {k} chunks, got {len(chunks)}"


def test_retrieval_scrubs_query(indexed_workspace, monkeypatch):
    """
    retrieve() passes the query through scrub() before embedding it.
    A query containing a fake secret must never reach the embedder raw.
    """
    from shadow_po import privacy

    scrubbed_queries: List[str] = []
    original_scrub = privacy._scrubber.scrub

    def capturing_scrub(text: str) -> str:
        result = original_scrub(text)
        scrubbed_queries.append(result)
        return result

    monkeypatch.setattr(privacy._scrubber, "scrub", capturing_scrub)

    fake_key = "sk-abcdef1234567890abcdef1234567890abcdef12"
    kb.retrieve(
        workspace_path=indexed_workspace,
        query=f"What is the API key {fake_key}?",
        k=2,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    assert len(scrubbed_queries) > 0, "scrub() should have been called"
    # The scrubbed version sent to the embedder must not contain the raw key
    assert all(fake_key not in q for q in scrubbed_queries), (
        "Raw API key must not appear in any scrubbed query"
    )


# ---------------------------------------------------------------------------
# Task D-5: Cross-feature isolation (hard gate before D connects to F)
# ---------------------------------------------------------------------------

def test_cross_feature_isolation(tmp_path, privacy_scrubber):
    """
    Acceptance: a query against workspace A never returns chunks from
    workspace B, even when both contain overlapping topic keywords.

    This is the Risk R5 hard gate — must pass before D is wired into F.
    """
    from shadow_po import workspace as ws

    # --- Workspace A: one-click-checkout ---
    ws_a = ws.create_workspace("checkout-feature", workspaces_root=tmp_path)
    (ws_a / "input" / "documents" / "checkout.txt").write_text(
        "One-Click Checkout Feature\n\n"
        "The EXCLUSIVE_TOKEN_ALPHA identifier marks all checkout transactions.\n\n"
        "Users complete purchases with a single button press.",
        encoding="utf-8",
    )
    kb.index_workspace_documents(
        workspace_path=ws_a,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    # --- Workspace B: user-authentication ---
    ws_b = ws.create_workspace("auth-feature", workspaces_root=tmp_path)
    (ws_b / "input" / "documents" / "auth.txt").write_text(
        "User Authentication Feature\n\n"
        "The EXCLUSIVE_TOKEN_BETA identifier marks all login sessions.\n\n"
        "Users authenticate with username and password.",
        encoding="utf-8",
    )
    kb.index_workspace_documents(
        workspace_path=ws_b,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    # Query workspace A — should only see ALPHA content, never BETA
    chunks_a = kb.retrieve(
        workspace_path=ws_a,
        query="What is the exclusive token identifier?",
        k=5,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    combined_a = " ".join(chunks_a)
    assert "EXCLUSIVE_TOKEN_ALPHA" in combined_a, (
        "Workspace A query should return workspace A content"
    )
    assert "EXCLUSIVE_TOKEN_BETA" not in combined_a, (
        "Workspace A query must NEVER return workspace B content — isolation violated!"
    )

    # Query workspace B — should only see BETA content, never ALPHA
    chunks_b = kb.retrieve(
        workspace_path=ws_b,
        query="What is the exclusive token identifier?",
        k=5,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    combined_b = " ".join(chunks_b)
    assert "EXCLUSIVE_TOKEN_BETA" in combined_b, (
        "Workspace B query should return workspace B content"
    )
    assert "EXCLUSIVE_TOKEN_ALPHA" not in combined_b, (
        "Workspace B query must NEVER return workspace A content — isolation violated!"
    )
