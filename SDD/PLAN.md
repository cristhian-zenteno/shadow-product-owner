# Shadow PO — Implementation Plan (PLAN)

This is the Phase 2 "Plan" artifact for Shadow PO, built from `SPECIFY.md`. It follows the five things the SDD skill asks a plan to cover: components and dependencies, build order, risks and mitigations, what can run in parallel vs. must be sequential, and verification checkpoints between phases.

This plan is reviewable on its own — read it and tell me "yes, build it in this order" or "no, change X" before Phase 3 (Tasks) breaks it into concrete tickets.

---

## 1. Components and Their Dependencies

Ten components fall out of SPECIFY.md. Each one below lists what it needs to already exist before it can be built for real (not stubbed).

| # | Component | Depends on | Why |
|---|---|---|---|
| A | **Workspace manager** | Nothing | Just folder/config logic: creates `workspaces/<feature>/{input/documents, input/meetings, progress/chat, output}`, reads the app-level `settings.yaml`. Foundation everything else is built on top of. |
| B | **Privacy scrubber** (Presidio) | Nothing | Pure function: text in, scrubbed text out. No dependency on any other component, but everything else depends on *it*. |
| C | **Local transcription** (faster-whisper) | A (needs `input/meetings/` to exist), B (output must pass through it) | Converts audio/video to text, then the text must be scrubbed before going anywhere else. |
| D | **Document ingestion & RAG** (MarkItDown + chunking + embeddings + vector store) | A (needs `input/documents/` to exist), B (scrubbing happens before chunks are used downstream — see Risk R3) | Turns `input/documents/` and `input/meetings/` into a searchable per-feature index. |
| E | **Web grounding** (SearXNG client) | B (queries must be scrubbed before leaving the machine) | Sends scrubbed search queries, returns raw snippets. |
| F | **LLM orchestration** (LangChain + `ChatNVIDIA`) | B, D, E | The chain that assembles scrubbed input + retrieved chunks + search snippets into a model call. This is the integration point — it can't be meaningfully tested until D and E exist, even as stubs. |
| G | **Chat history** (save/append/resume) | A, F (a conversation only exists once there's something to save) | Persists conversation turns to `progress/chat/`. |
| H | **Answered-questions tracking** | A, F, G (needs a chat turn to detect "the PO answered X") | Writes Q&A pairs into `input/documents/answered-questions.md`; also a *consumer* of D, since that file re-enters the RAG index. |
| I | **"Generate docs" generator** | C, D, E, F, G, H all functioning | The integration point that pulls from every other component. By definition this is built last. |
| J | **Streamlit UI** | Can be stubbed early against fake data; needs B–I for real functionality | Workspace picker, chat window, file upload, "Generate docs" button. |

### Dependency graph (text form)

```
A (workspace manager)
└─┬─ B (privacy scrubber)
  ├─ C (transcription)        ──┐
  ├─ D (document ingestion/RAG) ─┼─→ F (LLM orchestration) ─┬─→ G (chat history)
  └─ E (web grounding)        ──┘                           ├─→ H (answered-questions) ──→ (feeds back into D)
                                                              └─→ I ("Generate docs", needs C,D,E,F,G,H)
J (UI) wraps around all of the above, stubbed early, wired for real late
```

The one cycle worth naming explicitly: **H feeds back into D.** Answering a question during chat writes a file that then re-enters the RAG index for future retrieval. This isn't a build-order problem — D just needs to be able to pick up new/changed files in `input/documents/` without a full rebuild being required, which is a concrete requirement for D's design, not a circular dependency that blocks building either piece.

---

## 2. Build Order

Sequential, in the order a human could review and sign off on each stage:

1. **A — Workspace manager.** Nothing else has anywhere to put files without this.
2. **B — Privacy scrubber.** Built and tested in isolation, with the fixture-based test described in SPECIFY.md §2, before it's wired into anything that touches a network call.
3. **C — Local transcription**, **D — Document ingestion/RAG**, and **E — Web grounding** can now start. Each only needs A and B, not each other (see §3 below — these three run in parallel).
4. **F — LLM orchestration**, using `nvidia/nemotron-3-ultra-550b-a55b` (confirmed free-tier, tool-calling-capable — see Open Questions section below). Needs D and E to be real — C can still be in progress (see decision in §3).
5. **G — Chat history**, in parallel with the tail end of F, since saving a turn just needs there to *be* a turn — it doesn't need F to be fully correct, just producing something.
6. **H — Answered-questions tracking.** Needs G (a real chat loop to detect an answer in) and a working D (to confirm the new file actually re-enters retrieval).
7. **I — "Generate docs" generator.** Last, by definition — it's the integration point that reads from C, D, E, F, G, and H all at once.
8. **J — UI**, wired up incrementally throughout: a rough shell can exist from step 1 onward (so there's something to look at and click through), but each panel only becomes "real" once its backing component is real — chat panel after F, upload panel after C, Generate docs button after I.

---

## 3. Parallel vs. Sequential Work

**Must be sequential:**
- A before everything (nothing else has a place to write files without it)
- B before C, D's retrieval-from-scrubbed-content path, E, F (the trust boundary has to exist before anything that crosses it)
- F before G, H, I (nothing downstream of "the model answers" can be built against a fake answer forever)
- G before H (need a real saved conversation to detect an answer inside)
- C, D, E, F, G, H all before I (I is the integration point)

**Can be built in parallel, once A and B exist:**
- **C (transcription)**, **D (document ingestion/RAG)**, and **E (web grounding)** don't depend on each other at all. These are the best candidates for genuinely parallel work — three different people (or three different focused sessions) could build these independently and only need to agree on one thing: what shape of text each one hands off to F.
- **J (UI shell)** can be roughed in any time after A, in parallel with B–E, as long as it's clearly understood to be working against fake/stub data until the real components land.

**Decided:** F is allowed to start once D and E are real, even if C is still in progress. Voice input is one of several ways to start a conversation, not a hard prerequisite for chat to work at all — so transcription (C) keeps being built in parallel with F instead of gating it.

---

## 4. Risks and Mitigations

| Risk | Why it matters | Mitigation |
|---|---|---|
| **R1 — Scrubber gives false confidence.** Presidio doesn't know your org's project codenames out of the box. | If someone assumes "the scrubber catches everything," a codename could leak before the custom deny-list is configured. | Ship with the custom-codename-list mechanism *required to be configured*, not optional — make the app refuse to send anything to the network until at least an empty/confirmed list exists, so the gap is visible rather than silent. |
| **R2 — `ChatNVIDIA` model/tool-calling support varies by model.** Not every free-tier NVIDIA model reliably supports structured output / tool calling, which F depends on. | If the chosen model can't do structured output, the Pydantic-schema-enforced answer (and therefore I's file generation) breaks. | **Resolved:** `nvidia/nemotron-3-ultra-550b-a55b` is confirmed directly on NVIDIA's own model page as a free-endpoint model tagged Agent/Frontier/Long Context/MoE/Reasoning, explicitly built for agentic reasoning, planning, and tool calling, with a 1M-token context window and first-party LangChain integration shown on its own prototype page. This replaces the earlier placeholder model ID — see §6 below for the confirmed model entry. |
| **R3 — Stale or double-scrubbed content in the RAG index.** D's local vector index could end up holding either unscrubbed text (if D is built before B is wired in) or get re-indexed inconsistently when `answered-questions.md` changes. | A retrieval bug here silently leaks unscrubbed text into a model call, or serves stale answers after a question's been resolved. | D's design must scrub *before* chunking/embedding, not after, and must support incremental re-indexing of a single changed file (the H → D feedback loop) rather than requiring a full folder rebuild each time. Both are concrete acceptance criteria for D, not nice-to-haves. |
| **R4 — SearXNG availability.** E depends on a separately-run local service; if it's not running, web grounding silently fails. | A model answering "I checked the web" when it didn't is worse than no grounding at all. | F must treat a failed/empty SearXNG response as "no grounding available" and say so in the answer, never silently fall back to ungrounded-but-confident phrasing. This mirrors the "never silently degrade" boundary already in SPECIFY.md §4. |
| **R5 — Per-feature index isolation.** D's vector store must never let one feature's retrieval pull in another feature's documents. | A leak here breaks the entire "self-contained workspace" premise of the per-feature folder design. | Build and run the cross-feature isolation test (two feature workspaces, confirm a query in one never surfaces chunks from the other) as part of D's own test suite, before D is connected to F. |
| **R6 — Generate docs reading partial/inconsistent state.** I pulls from six different sources (C/D/E/F/G/H) at once; if one is mid-write or errored, the generated snapshot could be silently incomplete. | A dev trusting a generated `business-rules.md` that's missing something it should have had is worse than the file not existing. | I should fail loudly (clear error, no partial file written) rather than produce a partial snapshot, mirroring the "never silently degrade" pattern from R4. |

---

## 5. Verification Checkpoints

Each checkpoint is a point where the human should look at something concrete and approve before moving on — not just "trust that it works."

- **After A:** Manually create a feature workspace and confirm the folder structure matches SPECIFY.md §1 exactly (`input/documents/`, `input/meetings/`, `progress/chat/`, `output/`).
- **After B:** Run the fixture-based privacy test from SPECIFY.md §2 (fake API key, fake IP, fake codename, fake email) and confirm none of them survive. This is a hard gate — nothing proceeds to being wired into C/D/E/F until this passes.
- **After C, D, E (can be checked independently, in any order):**
  - C: feed a short test audio clip, confirm a plain-text transcript comes out, confirm it passed through B before being usable.
  - D: load a small fixture set of documents (one PDF, one Word doc, one markdown file) into a test feature's `input/documents/`, ask a question whose answer is only in one of them, confirm retrieval finds the right chunk and not the others. Also run the R5 cross-feature isolation check here.
  - E: confirm a scrubbed query reaches a running local SearXNG instance and raw snippets come back; confirm a graceful "no grounding" path when SearXNG is unreachable (R4).
- **After F:** Run the two demo scenarios from the earlier architecture review (1-Click checkout happy path; an offline/cloud contradiction case) end-to-end through chat and confirm the answer is grounded, schema-valid, and doesn't leak unscrubbed input.
- **After G:** Close and reopen the app mid-conversation, confirm the conversation resumes with full prior history intact.
- **After H:** During a chat, tell the app a question was answered; confirm the Q&A pair lands in `answered-questions.md`, and confirm a fresh retrieval query can find it.
- **After I:** Click "Generate docs" twice for the same feature; confirm two separate timestamped folders exist, confirm the second `open-questions.md` excludes anything answered between the two clicks, confirm the four files match the structure in SPECIFY.md §8.
- **After J is fully wired:** A full manual walkthrough — create a feature, upload a document and a short recording, chat for a few turns, answer a previously-raised question in chat, click "Generate docs," inspect the resulting files.

---

## Open Questions — Now Resolved

All three open questions from the last review are now settled:

1. **Can F start before C (transcription) is finished?** Yes — confirmed. F only needs D (document/RAG) and E (web grounding) to be real; C can keep being built in parallel. The build order in §2 and the parallel/sequential grouping in §3 already reflect this.

2. **Which NVIDIA model does F actually use?** `nvidia/nemotron-3-ultra-550b-a55b` — confirmed directly on NVIDIA's own build.nvidia.com model page:
   - **Free Endpoint: Available** (no payment required)
   - Tagged Agent, Frontier, Long Context, MoE, Reasoning — purpose-built for agentic reasoning, planning, and tool calling, which is exactly what F's structured-output requirement (`with_structured_output` / Pydantic schema enforcement) depends on
   - 1M-token context window — comfortably covers a feature's retrieved chunks + search snippets + conversation history in one call
   - First-party LangChain integration shown directly on its own NVIDIA prototype page
   - 8M API calls in the last 30 days at time of writing — a real, heavily-used endpoint, not an obscure or soon-to-be-deprecated one
   
   This replaces the placeholder model ID used earlier in the project's tech-stack notes. `settings.yaml`'s `model.name` should be set to `nvidia/nemotron-3-ultra-550b-a55b`.

3. **Embedding model and vector store for D — confirmed.** Sticking with the original proposal, now license-verified:
   - **`sentence-transformers`** (Apache 2.0 — free, open-source, permissive) for generating embeddings locally, no API key or network call needed.
   - **Chroma** (Apache 2.0 — free, open-source, permissive, Python-native, first-class LangChain integration, runs fully locally either in-memory or persisted to disk) as the vector store.
   
   Neither is GPL — both are Apache 2.0, which is the same category as MIT: free, open-source, permissive. This matches the same license trade-off already accepted for Presidio (MIT) and noted in SPECIFY.md — copyleft (GPL/AGPL) tools were preferred where available (SearXNG is AGPL-3.0), but the strongest local, free, no-API-key options for embeddings and vector storage are Apache 2.0. Flagging this explicitly rather than silently treating Apache 2.0 as equivalent to GPL.
