# Shadow PO — Task Breakdown (TASKS)

This is the Phase 3 "Tasks" artifact for Shadow PO, built from `PLAN.md`. Each task is sized for a single focused session, touches at most 5 files, has explicit acceptance criteria, and a concrete verification step. Tasks are ordered by dependency — following `PLAN.md`'s build order (A → B → C/D/E → F → G → H → I → J) — not by perceived importance.

Letters in brackets (e.g. `[A]`) tag which `PLAN.md` component a task belongs to, so it's easy to trace a task back to the plan.

---

## A — Workspace Manager

- [x] Task: Define the per-feature folder structure and a function to create it
  - Acceptance: Calling `create_workspace("1-click-checkout")` creates `workspaces/1-click-checkout/{input/documents, input/meetings, progress/chat, output}`, matching `SPECIFY.md` §1 exactly. Calling it again on an existing workspace doesn't error or wipe anything.
  - Verify: `pytest tests/test_workspace.py` — create a workspace, assert all 4 subfolders exist, call create again, assert no data loss.
  - Files: `shadow_po/workspace.py`, `tests/test_workspace.py`

- [x] Task: Load app-level `settings.yaml` into a typed config object
  - Acceptance: `load_settings()` reads `settings.yaml`, returns an object with `.workspaces_root`, `.model_name`, `.searxng_url`, `.whisper_model_size`, `.embedding_model` — all the fields named in the earlier project tech-stack notes. Missing file or missing required field raises a clear error, not a silent default.
  - Verify: `pytest tests/test_settings.py` — load a valid fixture `settings.yaml`, assert all fields populate; load a fixture missing a required field, assert it raises.
  - Files: `shadow_po/config.py`, `settings.yaml` (example/template), `tests/test_settings.py`, `tests/fixtures/settings_valid.yaml`, `tests/fixtures/settings_missing_field.yaml`

- [x] Task: List existing feature workspaces under `workspaces_root`
  - Acceptance: `list_workspaces()` returns every subfolder of `workspaces_root` that has the expected 4-folder shape; ignores anything that doesn't (e.g. a stray file).
  - Verify: `pytest tests/test_workspace.py::test_list_workspaces` — create 2 valid workspaces and 1 stray file, confirm only the 2 are listed.
  - Files: `shadow_po/workspace.py`, `tests/test_workspace.py`

---

## B — Privacy Scrubber

- [x] Task: Wrap Presidio for one-call text scrubbing
  - Acceptance: `scrub(text: str) -> str` runs Presidio's analyzer + anonymizer and returns text with detected emails, IPs, credit cards, and credential-shaped strings replaced by clear placeholder tags (e.g. `[EMAIL]`, `[IP_ADDRESS]`).
  - Verify: `pytest tests/test_privacy.py::test_scrub_basic` — feed a string containing a fake email and fake IP, assert neither appears in the output.
  - Files: `shadow_po/privacy.py`, `tests/test_privacy.py`

- [x] Task: Add the custom codename deny-list, loaded from settings
  - Acceptance: `scrub()` also redacts any term in a user-configurable codename list (from `settings.yaml`, e.g. `privacy.codenames: ["Project Titan"]`); an empty/unset list is allowed but the app must clearly warn at startup that no codenames are configured, not stay silent (per PLAN.md Risk R1).
  - Verify: `pytest tests/test_privacy.py::test_codename_redaction` — configure a fake codename, confirm it's redacted; confirm an empty list logs a startup warning.
  - Files: `shadow_po/privacy.py`, `tests/test_privacy.py`, `settings.yaml`

- [x] Task: Build the non-negotiable fixture test and hard-stop-on-failure behavior
  - Acceptance: One test feeds a fixture transcript containing a fake API key, fake internal IP, fake codename, and fake email, asserting none survive (per `SPECIFY.md` §2 / `PLAN.md` §5 "After B" checkpoint). Separately, `scrub()` raises (rather than returning unscrubbed text) if Presidio itself throws.
  - Verify: `pytest tests/test_privacy.py::test_full_fixture_redaction` and `::test_scrub_failure_hard_stops`.
  - Files: `shadow_po/privacy.py`, `tests/test_privacy.py`, `tests/fixtures/sensitive_transcript.txt`

**Checkpoint (matches PLAN.md §5):** All of B's tests pass before any task in C, D, or E is allowed to call `scrub()` for real instead of a stub.

---

## C — Local Transcription

- [x] Task: Wrap `faster-whisper` for local audio transcription
  - Acceptance: `transcribe_audio(path: str) -> str` runs entirely offline (no network calls — confirm by running with no internet connection) and returns a plain-text transcript with timestamps per segment.
  - Verify: `pytest tests/test_transcription.py::test_transcribe_audio` against a short fixture audio clip with known speech content; assert key phrases appear in the output.
  - Files: `shadow_po/transcription.py`, `tests/test_transcription.py`, `tests/fixtures/sample_audio.wav`

- [x] Task: Extract audio track from video before transcribing
  - Acceptance: `transcribe_video(path: str) -> str` extracts only the audio track (via `ffmpeg`) and reuses `transcribe_audio`; never touches video frames.
  - Verify: `pytest tests/test_transcription.py::test_transcribe_video` against a short fixture video; assert the same transcript quality as the audio-only path.
  - Files: `shadow_po/transcription.py`, `tests/test_transcription.py`, `tests/fixtures/sample_video.mp4`

- [x] Task: Pipe transcription output through the privacy scrubber, and add deliberate save-to-`input/meetings/`
  - Acceptance: The transcription functions' output is always passed through `scrub()` before being returned to any caller; a separate explicit `save_meeting_transcript(workspace, filename, text)` writes a *scrubbed* transcript into that feature's `input/meetings/`, only when called, never automatically.
  - Verify: `pytest tests/test_transcription.py::test_transcript_is_scrubbed` and `::test_save_meeting_transcript_explicit`.
  - Files: `shadow_po/transcription.py`, `tests/test_transcription.py`

---

## D — Document Ingestion & RAG

- [x] Task: Convert documents to Markdown via MarkItDown
  - Acceptance: `convert_to_markdown(path: str) -> str` runs MarkItDown on a file from that feature's `input/documents/` only (never an arbitrary path, per `SPECIFY.md` §2's MarkItDown note) and returns clean Markdown text for PDF, Word, and PowerPoint fixture files.
  - Verify: `pytest tests/test_knowledge_base.py::test_convert_to_markdown` against one fixture PDF, one fixture .docx, one fixture .pptx.
  - Files: `shadow_po/knowledge_base.py`, `tests/test_knowledge_base.py`, `tests/fixtures/sample.pdf`, `tests/fixtures/sample.docx`, `tests/fixtures/sample.pptx`

- [x] Task: Chunk converted documents and transcripts into retrievable pieces
  - Acceptance: `chunk_text(text: str) -> list[str]` splits text into paragraph-sized chunks suitable for embedding; handles very short documents (single chunk) and very long ones without erroring.
  - Verify: `pytest tests/test_knowledge_base.py::test_chunking` — confirm chunk count and rough size bounds on a short and a long fixture document.
  - Files: `shadow_po/knowledge_base.py`, `tests/test_knowledge_base.py`

- [x] Task: Embed chunks locally with `sentence-transformers` and store in a per-feature Chroma collection
  - Acceptance: `index_workspace_documents(workspace)` embeds every chunk from that feature's `input/documents/` and `input/meetings/` (after scrubbing, per Risk R3) into a Chroma collection named/scoped uniquely per feature workspace; no network call is made during embedding.
  - Verify: `pytest tests/test_knowledge_base.py::test_indexing_is_local_and_scrubbed` — confirm indexing works offline and that scrubbed placeholders (not raw secrets) end up in the stored chunks.
  - Files: `shadow_po/knowledge_base.py`, `tests/test_knowledge_base.py`

- [x] Task: Query the per-feature index and return top relevant chunks
  - Acceptance: `retrieve(workspace, query: str, k=5) -> list[str]` returns the `k` most relevant chunks for that feature's index only.
  - Verify: `pytest tests/test_knowledge_base.py::test_retrieval_relevance` — fixture documents where the answer is only in one file; confirm that chunk is retrieved and ranks highly.
  - Files: `shadow_po/knowledge_base.py`, `tests/test_knowledge_base.py`

- [x] Task: Cross-feature isolation test (Risk R5 — hard gate before D connects to F)
  - Acceptance: A query run against feature workspace 1's index never returns chunks from feature workspace 2's index, even if both contain similar content.
  - Verify: `pytest tests/test_knowledge_base.py::test_cross_feature_isolation` — two fixture workspaces with overlapping topics, confirm no cross-contamination in results.
  - Files: `tests/test_knowledge_base.py`

- [x] Task: Support incremental re-indexing of a single changed file
  - Acceptance: `reindex_file(workspace, file_path)` updates only that file's chunks in the Chroma collection, without rebuilding the whole feature's index — needed for the H → D feedback loop (`answered-questions.md` changes shouldn't require a full rebuild).
  - Verify: `pytest tests/test_knowledge_base.py::test_incremental_reindex` — modify one fixture file, confirm only its chunks change, confirm other files' chunks are untouched and a timestamp/hash check confirms no full-rebuild occurred.
  - Files: `shadow_po/knowledge_base.py`, `tests/test_knowledge_base.py`

**Checkpoint (matches PLAN.md §5):** D's full test suite (including cross-feature isolation) passes before D is wired into F.

---

## E — Web Grounding

- [x] Task: Build the SearXNG client wrapper
  - Acceptance: `search_web(query: str) -> list[dict]` sends a query to the configured local SearXNG instance (`settings.searxng_url`) and returns a list of `{title, url, snippet}` dicts.
  - Verify: `pytest tests/test_web_grounding.py::test_search_web` against a mocked SearXNG HTTP response.
  - Files: `shadow_po/web_grounding.py`, `tests/test_web_grounding.py`

- [x] Task: Scrub queries before they leave the machine
  - Acceptance: `search_web()` always passes the query through `scrub()` first; a query containing a fake secret never reaches the (mocked) outbound HTTP call unscrubbed.
  - Verify: `pytest tests/test_web_grounding.py::test_query_is_scrubbed` — assert the mocked HTTP call's actual request body never contains the fixture secret.
  - Files: `shadow_po/web_grounding.py`, `tests/test_web_grounding.py`

- [x] Task: Graceful "no grounding available" path when SearXNG is unreachable (Risk R4)
  - Acceptance: If the SearXNG request fails or returns no results, `search_web()` returns a clear "unavailable" signal (not an empty list indistinguishable from "no results found") so callers can tell the model to say it couldn't check the web.
  - Verify: `pytest tests/test_web_grounding.py::test_searxng_unreachable` — mock a connection error, confirm the distinct "unavailable" signal is returned.
  - Files: `shadow_po/web_grounding.py`, `tests/test_web_grounding.py`

---

## F — LLM Orchestration

- [x] Task: Configure `ChatNVIDIA` with the confirmed model
  - Acceptance: `get_llm()` returns a `ChatNVIDIA` instance configured with `nvidia/nemotron-3-ultra-550b-a55b` (per `PLAN.md` §6) and the API key from `.env`; raises a clear error if `NVIDIA_API_KEY` is missing, rather than failing deep inside a chain call.
  - Verify: `pytest tests/test_pipeline.py::test_get_llm_missing_key` (mocked, no real key needed) and a manual one-off real call during development to confirm the live endpoint responds.
  - Files: `shadow_po/pipeline.py`, `tests/test_pipeline.py`, `.env.example`

- [x] Task: Define the Pydantic output schema
  - Acceptance: A `ShadowPOAnswer` Pydantic model exists with fields matching what chat needs to render (a plain-language answer, optional Gherkin scenario, optional Mermaid diagram) — distinct from the "Generate docs" output schema in task I, since chat answers are conversational, not the four-file package.
  - Verify: `pytest tests/test_schemas.py` — instantiate with valid/invalid data, confirm validation errors are clear.
  - Files: `shadow_po/schemas.py`, `tests/test_schemas.py`

- [x] Task: Build the chat chain — assemble scrubbed input + RAG chunks + search snippets
  - Acceptance: `answer_question(workspace, question: str) -> ShadowPOAnswer` scrubs the question, retrieves relevant chunks via D, optionally calls E if the question needs current/public info, and calls F's LLM with all of it assembled into one prompt, returning a schema-validated answer.
  - Verify: `pytest tests/test_pipeline.py::test_answer_question` with D and E mocked; confirm the assembled prompt contains the scrubbed question, the mocked chunks, and the mocked snippets.
  - Files: `shadow_po/pipeline.py`, `tests/test_pipeline.py`

- [x] Task: Decide when to call web grounding vs. answer from documents alone
  - Acceptance: `answer_question()` only calls E when the question plausibly needs current/public/industry information (e.g. via a lightweight classification step or explicit model decision) — not on every single question, per `SPECIFY.md` §1's "only when genuinely needed" rule.
  - Verify: `pytest tests/test_pipeline.py::test_grounding_decision` — a question clearly answerable from local docs alone should not trigger a (mocked) E call; a question about current industry standards should.
  - Files: `shadow_po/pipeline.py`, `tests/test_pipeline.py`

- [x] Task: Never silently degrade when grounding is unavailable (Risk R4)
  - Acceptance: If E returns the "unavailable" signal from its own task, the final answer explicitly says grounding wasn't available for this question, rather than answering confidently as if it had checked.
  - Verify: `pytest tests/test_pipeline.py::test_ungrounded_disclosure` — mock E's "unavailable" signal, assert the returned answer text flags this.
  - Files: `shadow_po/pipeline.py`, `tests/test_pipeline.py`

- [x] Task: End-to-end demo scenario regression tests
  - Acceptance: The two demo scenarios (1-Click checkout happy path; offline/cloud contradiction case) pass end-to-end through the real chain (mocked LLM response, real D/E wiring) per `PLAN.md` §5's "After F" checkpoint.
  - Verify: `pytest tests/test_pipeline.py::test_demo_scenario_1click` and `::test_demo_scenario_contradiction`.
  - Files: `tests/test_pipeline.py`, `tests/fixtures/demo_1click/`, `tests/fixtures/demo_contradiction/`

**Checkpoint (matches PLAN.md §5):** Both demo scenarios pass, with confirmed schema-valid, grounded-or-honestly-ungrounded answers, before G is built against real chat output.

---

## G — Chat History

- [x] Task: Append a chat turn to that feature's conversation file
  - Acceptance: `save_turn(workspace, conversation_id, role, content)` appends one message to `progress/chat/<conversation_id>.md` (or similar), creating the file if it's the first turn.
  - Verify: `pytest tests/test_chat_history.py::test_save_turn_appends` — save 3 turns, confirm all 3 are present in order, confirm the file isn't rewritten/truncated between calls.
  - Files: `shadow_po/chat_history.py`, `tests/test_chat_history.py`

- [x] Task: List and load past conversations for resuming
  - Acceptance: `list_conversations(workspace)` returns all saved conversation IDs for that feature; `load_conversation(workspace, conversation_id)` returns the full message history in order.
  - Verify: `pytest tests/test_chat_history.py::test_list_and_load` — save a multi-turn conversation, confirm it round-trips losslessly through list + load.
  - Files: `shadow_po/chat_history.py`, `tests/test_chat_history.py`

- [x] Task: Confirm scrubbing applies to saved chat content
  - Acceptance: `save_turn()` never writes unscrubbed text — any text saved has already passed through `scrub()` upstream (this task verifies the integration point with F, not a new scrub call).
  - Verify: `pytest tests/test_chat_history.py::test_saved_chat_is_scrubbed` — run a fixture question containing a fake secret through the real `answer_question()` → `save_turn()` path, confirm the saved file doesn't contain it.
  - Files: `tests/test_chat_history.py`

---

## H — Answered-Questions Tracking

- [x] Task: Detect "the PO answered X" during a chat turn
  - Acceptance: `detect_answered_question(conversation_history, new_message) -> QAPair | None` identifies when a new chat message is answering a previously raised open question (via the LLM itself, with a focused prompt) and returns a structured question+answer pair, or `None` if it isn't.
  - Verify: `pytest tests/test_answered_questions.py::test_detect_answer` — feed a fixture conversation where a later message clearly answers an earlier question; confirm a `QAPair` is returned with both fields populated.
  - Files: `shadow_po/answered_questions.py`, `tests/test_answered_questions.py`

- [x] Task: Append detected answers to `input/documents/answered-questions.md`
  - Acceptance: `record_answer(workspace, qa_pair)` appends the Q&A pair to that feature's `answered-questions.md` in a consistent, parseable format; file is created if it doesn't exist yet.
  - Verify: `pytest tests/test_answered_questions.py::test_record_answer` — record 2 answers, confirm both appear, confirm no earlier entries are overwritten.
  - Files: `shadow_po/answered_questions.py`, `tests/test_answered_questions.py`

- [x] Task: Trigger re-indexing after a new answer is recorded
  - Acceptance: After `record_answer()` succeeds, D's `reindex_file()` (from task D) is called on `answered-questions.md` so the new answer is retrievable in future chat turns without a manual or full rebuild.
  - Verify: `pytest tests/test_answered_questions.py::test_reindex_triggered` — record an answer, then immediately run a retrieval query that should now surface it.
  - Files: `shadow_po/answered_questions.py`, `tests/test_answered_questions.py`

---

## I — "Generate docs" Generator

- [x] Task: Gather everything relevant to a feature for doc generation
  - Acceptance: `gather_feature_context(workspace) -> FeatureContext` pulls that feature's `input/documents/`, `input/meetings/` transcripts, the full saved chat conversation(s) from `progress/chat/`, and a record of web search results used during the session — failing loudly (not partially) if any required source can't be read, per Risk R6.
  - Verify: `pytest tests/test_generate_docs.py::test_gather_context_complete` and `::test_gather_context_fails_loudly_on_missing_source`.
  - Files: `shadow_po/generate_docs.py`, `tests/test_generate_docs.py`

- [x] Task: Define the "Generate docs" output schema and system prompt
  - Acceptance: A Pydantic schema (or four separate schemas) for `business-rules.md`, `scenarios.md`, `diagram.md`, `open-questions.md` content; a system prompt in `prompts/` instructs the model to produce markdown matching this structure directly (per `SPECIFY.md` §8's "model does the formatting" rule).
  - Verify: `pytest tests/test_generate_docs.py::test_output_schema` — validate a fixture model response against the schema.
  - Files: `shadow_po/schemas.py`, `prompts/generate_docs_system_prompt.md`, `tests/test_generate_docs.py`

- [x] Task: Filter open questions against `answered-questions.md`
  - Acceptance: When building `open-questions.md` content, any question already present in that feature's `answered-questions.md` is excluded from the new list (per `SPECIFY.md` §7/§8).
  - Verify: `pytest tests/test_generate_docs.py::test_open_questions_excludes_answered` — fixture with 3 open questions, 1 already answered; confirm the generated list has only 2.
  - Files: `shadow_po/generate_docs.py`, `tests/test_generate_docs.py`

- [x] Task: Write the timestamped output folder, never overwriting past runs
  - Acceptance: `generate_docs(workspace) -> output_path` creates a new `output/<timestamp>/` folder with all 4 files written; running it twice produces two separate timestamped folders, neither overwriting the other.
  - Verify: `pytest tests/test_generate_docs.py::test_two_runs_create_two_folders`.
  - Files: `shadow_po/generate_docs.py`, `tests/test_generate_docs.py`

---

## J — Streamlit UI

- [x] Task: Workspace picker shell (can be built early against stub data)
  - Acceptance: A sidebar lists existing feature workspaces (via A's `list_workspaces()`) and lets the user create a new one or select an existing one.
  - Verify: Manual check — run `streamlit run app.py`, confirm workspace list renders and a new workspace can be created via the UI.
  - Files: `app.py`, `shadow_po/ui_workspace.py`

- [x] Task: Chat panel wired to real `answer_question()`
  - Acceptance: Typing a question in the chat panel calls F's `answer_question()` for the selected workspace and renders the answer (including any Gherkin/diagram) in the chat.
  - Verify: Manual check — ask a question against a fixture workspace, confirm a grounded answer renders; re-run after closing/reopening the app and confirm history (via G) reloads.
  - Files: `app.py`, `shadow_po/ui_chat.py`

- [x] Task: File upload panel for documents and meeting recordings
  - Acceptance: Uploading a document saves it into the selected workspace's `input/documents/` and triggers D's indexing; uploading audio/video runs it through C's transcription before offering to save it into `input/meetings/`.
  - Verify: Manual check — upload one fixture PDF and one fixture audio clip, confirm both appear in their respective folders and become retrievable in chat.
  - Files: `app.py`, `shadow_po/ui_upload.py`

- [x] Task: "Generate docs" button
  - Acceptance: Clicking the button calls I's `generate_docs()` for the current workspace and shows the resulting file paths/preview to the user.
  - Verify: Manual check — full walkthrough per `PLAN.md` §5's final checkpoint: create a feature, upload a document and a recording, chat for a few turns, answer a previously-raised question in chat, click "Generate docs," inspect the resulting files.
  - Files: `app.py`, `shadow_po/ui_generate.py`

---

## Verification Summary

This mirrors `PLAN.md` §5's checkpoints, now mapped to concrete pytest targets:

| Checkpoint | Command |
|---|---|
| After A | `pytest tests/test_workspace.py tests/test_settings.py` |
| After B (hard gate) | `pytest tests/test_privacy.py` |
| After C | `pytest tests/test_transcription.py` |
| After D (hard gate before F) | `pytest tests/test_knowledge_base.py` |
| After E | `pytest tests/test_web_grounding.py` |
| After F (hard gate before G/H/I) | `pytest tests/test_pipeline.py tests/test_schemas.py` |
| After G | `pytest tests/test_chat_history.py` |
| After H | `pytest tests/test_answered_questions.py` |
| After I | `pytest tests/test_generate_docs.py` |
| After J | Manual full walkthrough (no automated UI test in this iteration) |
| Everything | `pytest -v --cov=shadow_po` |
