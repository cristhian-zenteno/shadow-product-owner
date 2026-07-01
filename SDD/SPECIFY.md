# Shadow PO — Business Logic Specification (SPECIFY)

This is the combined "Specify" artifact for Shadow PO: how the app works, end to end, from a business-logic perspective. It merges what were previously eight separate short docs into one file, kept in the same plain, skill-style language — no formal spec phrasing, just a clear explanation a developer can read top to bottom.

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Privacy & Scrubbing](#2-privacy--scrubbing)
3. [Local Transcription](#3-local-transcription)
4. [Knowledge Base & Retrieval](#4-knowledge-base--retrieval)
5. [Web Grounding](#5-web-grounding)
6. [Chat History](#6-chat-history)
7. [Answered Questions](#7-answered-questions)
8. [Output & "Generate docs"](#8-output--generate-docs)

---

## 1. Architecture Overview

### What this app does

It helps a developer understand a feature requirement well enough to build it correctly — by chatting with them using the team's own documents, meeting transcripts, and the web — and, when they're ready, packages that understanding into a small set of readable files a teammate or PO could open without replaying the conversation.

These are two separate things, and the app keeps them separate on purpose.

### Everything lives inside one workspace folder per feature

Working on several features at once is normal, so nothing is shared across features by default. Each feature gets its own self-contained folder under `workspaces/`:

```
workspaces/
└── 1-click-checkout/             ← one folder per feature or ticket
    ├── input/
    │   ├── documents/            ← source-of-truth specs, PDFs, requirement docs
    │   │   └── answered-questions.md   (see §7)
    │   └── meetings/             ← audio/video files and their transcripts
    ├── progress/
    │   └── chat/                 ← saved conversation history (see §6)
    └── output/
        ├── 2026-06-28_1430/      ← one timestamped folder per "Generate docs" click
        │   ├── business-rules.md
        │   ├── scenarios.md
        │   ├── diagram.md
        │   └── open-questions.md
        └── ...
```

A single `settings.yaml` at the app level points at the parent `workspaces/` folder — it doesn't need to know about individual features, since each one is just a subfolder with the same shape.

### The trust boundary — the one rule everything else follows

**Nothing leaves your machine until it's been scrubbed.** Not the audio, not the video, not your documents, not your typed question. Only a cleaned, generalized version of the text is allowed to go to the NVIDIA model or to the local search engine. This rule applies identically whether you're chatting or generating docs, and identically across every feature workspace.

### Flow 1: Chatting — understanding the requirement

This is the everyday flow. You pick a feature workspace, ask a question, the app answers.

```
1. YOU PICK A FEATURE, THEN ASK SOMETHING
   (or pick up an old conversation for that feature, see §6)
   A typed question, a pasted requirement, or "what does the audio
   from yesterday's meeting say about X" (if you've already uploaded
   and transcribed it into this feature's input/meetings/ — see §3).

2. LOCAL PRIVACY SCRUBBING   (see §2)
   Whatever you typed gets cleaned before anything past this point
   happens.

3. THE APP GATHERS WHATEVER CONTEXT IS RELEVANT, FROM THIS FEATURE'S
   WORKSPACE ONLY
   ├─ This feature's input/documents/ and input/meetings/
   │   (see §4) — pulls the few relevant chunks, not the whole
   │   folder, and never reaches into another feature's workspace.
   └─ A web search                     (see §5)
       — only when the question genuinely needs current or public
       industry information the model wouldn't already know.

4. THE MODEL ANSWERS, IN THE CHAT
   A plain-language answer, grounded in whatever was relevant from
   step 3. If you specifically ask for a diagram or a Gherkin
   scenario, it shows you one right there. If you tell the app the
   PO answered a previously open question, that answer is recorded
   into this feature's input/documents/answered-questions.md — see
   §7 — so input/documents/ isn't purely read-only during this flow.

5. THE CONVERSATION IS SAVED AS IT GOES   (see §6)
   Each new exchange is appended to that conversation's file under
   this feature's progress/chat/ — not a finished knowledge artifact,
   just a record you (and Flow 2) can come back to.
```

### Flow 2: "Generate docs" — packaging the understanding

This is the deliberate, on-demand flow. You click a button when you feel the requirement is understood well enough to write down.

```
1. YOU CLICK "Generate docs"
   For whichever feature workspace you're currently in.

2. THE APP GATHERS EVERYTHING RELEVANT TO THAT FEATURE
   ├─ This feature's input/documents/
   ├─ This feature's input/meetings/ transcripts
   ├─ This feature's saved chat conversation  (progress/chat/, see §6)
   └─ Any web search results used along the way

3. THE MODEL WRITES A SMALL SET OF FOCUSED FILES
   (see §8 for exactly what these are and why they're split up
   rather than one giant document)

4. A NEW TIMESTAMPED FOLDER LANDS IN THIS FEATURE'S output/
   Previous "Generate docs" runs for the same feature are never
   overwritten — each click creates its own dated snapshot, so you
   can see how the understanding evolved.
```

### Folder roles, at a glance

| Folder (inside a feature's workspace) | What lives there | Who reads it |
|---|---|---|
| `input/documents/` | Source-of-truth specs, PDFs, requirement docs for this feature | The app (for retrieval, in both flows) |
| `input/documents/answered-questions.md` | Running record of PO answers given during chat | The app (for retrieval, and to shape future open-questions.md) |
| `input/meetings/` | Audio/video files and their transcripts for this feature | The app (for retrieval, in both flows) |
| `progress/chat/` | One file per conversation, appended to as it continues | The app (to resume a conversation, or feed it into "Generate docs") |
| `output/<timestamp>/` | A finished, immutable snapshot of business rules, scenarios, diagram, and open questions | You, your team, future-you |

---

## 2. Privacy & Scrubbing

### The problem this solves

Product refinement conversations leak things they shouldn't: API keys someone reads out loud, internal server addresses, codenames for unannounced projects, teammates' email addresses. If a meeting transcript or a pasted Jira ticket gets sent straight to a cloud LLM, all of that goes with it.

### The rule

**Every piece of text — typed, transcribed from audio, or pulled from a document — passes through the scrubber before it is allowed to touch a network call.** That includes calls to the NVIDIA model and calls to the local search engine. There is no flag, setting, or code path that skips this step.

If the scrubber itself fails for any reason, the pipeline stops. It does not fall back to sending the original, unscrubbed text — a scrubbing failure is treated as a hard stop, not a soft degrade.

### What gets caught

Using Microsoft Presidio (a free, open-source tool that runs entirely on your machine, no internet connection needed):

- Email addresses
- IP addresses
- API keys, tokens, and other credential-shaped strings
- Credit card numbers and other financial identifiers
- Names and other personal identifiers, where detectable

Presidio combines pattern matching with smarter language-aware detection, so it catches more than a simple "look for `key=value`" search would — including secrets that show up in natural spoken sentences rather than clean code syntax.

### What doesn't get caught automatically

Internal project codenames ("Project Titan") aren't something any general-purpose tool knows about — they're specific to your company. These need a small custom list you maintain yourself, since no off-the-shelf tool can guess your org's internal naming.

### How you'd verify this is actually working

There's a permanent test that feeds the scrubber a fake transcript containing a fake API key, a fake internal IP, a fake codename, and a fake email — and checks that none of them survive. That test is the actual evidence behind "this app doesn't leak your secrets," not just a claim in a document.

### A note on document conversion specifically

Documents are converted to Markdown by **MarkItDown** (see §4) before scrubbing happens. MarkItDown itself does no network calls — it only reads the local file you point it at, the same way opening a file in a text editor would. The app is careful to only ever ask it to read files explicitly placed in that feature's `input/documents/` folder, never an arbitrary path — so the only thing MarkItDown ever touches is exactly what you put there on purpose.

### Where this fits in the bigger picture

This step sits between "input" and "everything that touches the network" — see §1.

---

## 3. Local Transcription

### The problem this solves

Meeting recordings are the richest source of "what the PO actually meant" — but they're also the riskiest thing to upload anywhere, since you can't selectively redact a waveform the way you can redact text. The fix is to never let the audio leave the machine at all.

### How it works

1. You upload an audio file, or a video file (the app extracts just the audio track from video — it never looks at video frames, slides, or screen-shares).
2. A local speech-to-text engine (`faster-whisper`, a fast, free, open-source implementation of OpenAI's Whisper model) processes the audio entirely on your CPU or GPU.
3. The output is a plain text transcript, timestamped by speaker turn where possible.
4. That transcript goes straight into the privacy scrubbing step — see §2 — before anything else happens to it.

No network request is made during transcription. If you have no internet connection at all, transcription still works.

### What happens to the raw audio afterward

The raw audio file and the raw (unscrubbed) transcript are temporary by default — kept only as long as needed to produce the cleaned transcript, then discarded. If you want to keep a transcript as part of your project's permanent record, it's saved deliberately into that feature's `input/meetings/` folder as a visible, intentional action — not left behind as an incidental leftover file.

### Trade-offs worth knowing about

- Faster transcription models are quicker but less accurate on noisy audio or strong accents; slower models are the reverse. The app lets this be tuned in the settings file rather than locking in one choice forever.
- Transcription quality on a noisy conference room recording will be noticeably worse than a clean 1:1 call — this is a real limitation of local speech-to-text generally, not specific to this app.

### Where this fits in the bigger picture

Transcription is step 1 for recordings, and always feeds directly into privacy scrubbing (step 2) before anything else — see §1.

---

## 4. Knowledge Base & Retrieval

### The problem this solves

You have project documents — old specs, PDFs, notes — and a growing pile of meeting transcripts. Pasting all of that into a prompt every time doesn't scale: it gets slow, expensive, and eventually just won't fit. You need the app to find the *relevant* few paragraphs out of potentially hundreds of pages, not read everything every time.

### How it works, in plain terms

1. **Documents go into that feature's `input/documents/` folder, and meeting transcripts go into `input/meetings/`** — and `input/documents/` isn't limited to plain markdown anymore. PDFs, Word documents, PowerPoint decks, Excel files, and more all work, because the app first runs each file through **MarkItDown** (a free, open-source, MIT-licensed tool that runs entirely on your machine) to convert it into clean Markdown before anything else touches it. This means whatever format a PO or teammate happens to hand you, the app can still read it the same way. Meeting transcripts don't need this conversion step — they're already plain text, straight out of §3 — but they join the same chunking and retrieval pipeline described below.
2. The app breaks each converted document into smaller chunks (a few paragraphs each) and converts each chunk into a numeric representation of its meaning — an "embedding" — using a small model that runs locally, no internet needed.
3. Those chunk embeddings are stored in a local, file-based search index, kept separate per feature workspace — a question asked inside one feature's workspace only ever searches that feature's own `input/` folder, never another feature's.
4. When you ask a question, the app converts your question into the same kind of numeric representation and finds the handful of chunks whose meaning is closest to it.
5. Only those few relevant chunks — not the entire folder — get added to what the model sees when it writes its answer.

This is the difference between "the model reads everything every time" (slow, doesn't scale) and "the model reads exactly the few paragraphs that actually matter for this question" (fast, scales to a large knowledge base) — and keeping the index per-feature is what makes working on several features at once not bleed context between them.

### Why convert everything to Markdown first

Models read Markdown natively and efficiently — it's close enough to plain text that there's no parsing overhead, but it still preserves headings, lists, and tables well enough that the model can tell a section heading from a body paragraph. Converting a messy Word document or a PDF with columns and tables into clean Markdown up front means the chunking and retrieval steps are working with consistently structured text, regardless of what format the original file came in.

### Why this matters for trust in the answers

Grounding an answer in your own prior specs and meeting notes means the model isn't guessing or relying purely on general training knowledge — it's pulling from what your team has actually decided and said before. The same privacy scrubbing that applies to live audio also applies here: nothing from these documents reaches the NVIDIA model unscrubbed.

### What you'd notice if this were broken

If retrieval stops working — say, the local search index can't be reached — the app should tell you the answer is ungrounded rather than quietly giving you a confident-sounding answer that's actually just guessing. An answer that looks grounded but isn't is worse than an answer that honestly says "I couldn't check your documents this time."

### Where this fits in the bigger picture

This is the "local knowledge base" half of step 3 in Flow 1, run alongside web grounding (§5) before the model writes its answer — see §1.

---

## 5. Web Grounding

### The problem this solves

A model answering purely from memory will confidently state outdated or made-up industry details — wrong payment processor behavior, outdated checkout patterns, the wrong version of an API. Grounding the answer in real, current web information fixes this, but most ways of doing that either cost money per query or mean sending your question to a third-party company.

### How it works

1. The app runs a small, free, self-hosted search engine called **SearXNG** on your own machine (or your own server). It's a metasearch tool — it queries multiple underlying search engines at once and returns the combined results, with no tracking and no per-query fee.
2. When the model decides it needs current information, it sends a (scrubbed) search query to your local SearXNG instance.
3. SearXNG returns a handful of raw results — titles, links, short snippets — the same kind of thing you'd see on a search results page.
4. Those raw snippets are handed to the NVIDIA model along with your original question. The model itself reads them and writes a synthesized, documented answer that cites what it found — it doesn't just paste the snippets back at you.

### Why this approach instead of a "smart" search API

Some search products (like Google's AI-powered search overviews) do this synthesis step themselves and hand you back an already-written answer. That's convenient, but it ties you to that specific provider and its terms. Doing the synthesis step with the same model that's already answering your question gets the same end result — a documented, right-to-the-point answer with sources — without depending on a second AI provider or paying per search.

### What this costs you in trade-offs

- Running SearXNG yourself means it's one more thing on your machine (a small background service, started once).
- The model has to do a bit more work to read raw snippets and write a synthesized answer, compared to receiving an already-synthesized one — in practice this is a small, usually unnoticeable difference in response time.

### Where this fits in the bigger picture

This is the "web grounding" half of step 3 in Flow 1, run alongside local knowledge retrieval (§4) — see §1.

---

## 6. Chat History

### The problem this solves

A chat that only lives in memory disappears the moment you close the app or refresh the page. If you've spent twenty minutes working through a feature with the app, you shouldn't have to start over just because you stepped away — and when you click "Generate docs" later, the app needs the full conversation to still be there, not just whatever's currently on screen.

### How it works

1. Each conversation is saved as its own file under that feature's `progress/chat/` folder.
2. As the conversation continues, new messages are appended to that same file — it isn't rewritten or replaced each time, just added to.
3. From the app, you can open the list of past conversations (across all your feature workspaces, or just the current one) and pick one up where you left off. The model sees the full prior history, the same as if the conversation had never closed.
4. A new conversation only starts when you explicitly start one — picking up an old conversation always continues the same file rather than silently branching into a new one.

### Why this lives in `progress/`, not `output/`

A chat transcript is a working file, not a finished piece of knowledge — it's the raw back-and-forth that *leads to* understanding, not the understanding itself. That's exactly what a feature's `progress/` folder is for (see the folder table in §1). The polished, readable result of a conversation is what "Generate docs" produces in that feature's `output/` — see §8.

### How this connects to "Generate docs"

When you click "Generate docs," the app reads the saved conversation file for that feature — not just whatever messages happen to be visible on screen — so a conversation you resumed across multiple sessions is still treated as one complete conversation when it's time to package the knowledge.

### What goes into a saved chat file

The same privacy scrubbing rule applies here as everywhere else (see §2): nothing unscrubbed gets written, including into chat history. A saved conversation file is safe to keep around or eventually share, for the same reason any other content leaving the local machine is safe.

### Where this fits in the bigger picture

Chat history sits underneath Flow 1 (chatting), and is one of the four inputs Flow 2 ("Generate docs") pulls from — see §1.

---

## 7. Answered Questions

### The problem this solves

"Generate docs" produces an `open-questions.md` file listing the critical things still worth asking the PO. But questions get answered in real life — in the next standup, in a Slack message, in a hallway conversation — and if the app has no way to learn that, every future generated doc keeps listing the same stale question forever.

### How it works

1. While chatting, you tell the app the PO answered something — for example: "the PO said yes, double-charges should be prevented with a debounce, not a confirmation dialog."
2. The app recognizes this as an answer to a previously raised question and appends that question-and-answer pair to that feature's `input/documents/answered-questions.md`.
3. Because `input/documents/` is part of the local knowledge base the app retrieves from for that feature (see §4), that answer is now part of the team's source of truth — available to ground future chat answers, the same as any other document in that folder.

### How this connects to "Generate docs"

`open-questions.md` is never edited after the fact — past timestamped folders in a feature's `output/` stay exactly as they were generated, which is the same "snapshots are never overwritten" rule described in §8. Instead, the effect shows up the **next time** you click "Generate docs" for that feature: at that point, the app checks the question list it's about to write against `input/documents/answered-questions.md`, and a question that now has a recorded answer is left out of the new `open-questions.md`.

So answering a question doesn't change history — it changes what counts as "still open" going forward.

### What ends up in `answered-questions.md`

A running, append-only record of question-and-answer pairs, each one originating from something you told the app during a chat. It lives in that feature's `input/documents/` alongside your other source-of-truth files, not in `output/`, because it functions the same way any other reference document does — something the app reads from, not something it generates as a finished deliverable for a feature.

### Where this fits in the bigger picture

This is part of Flow 1 (chatting): a side effect that updates a feature's `input/documents/` while you talk, which then quietly shapes what Flow 2 ("Generate docs") produces the next time you run it for that same feature — see §1.

---

## 8. Output & "Generate docs"

### The problem this solves

A chat conversation is great for figuring things out in the moment, but it's a bad place to *store* the answer. If every question you asked also wrote a file, you'd end up with dozens of scattered fragments and no single place that holds "everything a dev needs to know about this feature." What's needed is a clear moment where you say "okay, this is settled — package it up" — and the app does exactly that, on demand, not automatically.

### Two separate things, not one

**Chatting** is for understanding the requirement. You ask questions, the app answers using your source docs, meeting transcripts, and (when genuinely needed) a web search for public/industry-standard information. If you ask for a diagram or a scenario, it shows you one, right there in the chat. None of this writes anything to disk (aside from the conversation itself being saved — see §6). It's a conversation, not a generator.

**Clicking "Generate docs"** is a separate, deliberate action. When you click it, the app looks at everything relevant to the feature you've been discussing — that feature's official source documents, its meeting transcripts, its saved chat conversation (see §6 — it reads the full saved file, not just whatever's currently visible on screen), and web search results used along the way — and produces a small set of files that together explain the feature from a business-rules perspective. This is the moment the knowledge becomes permanent.

### What "Generate docs" actually produces

Each time you click it, a new timestamped folder is created under that feature's `output/`, containing a few focused files rather than one giant document:

```
workspaces/1-click-checkout/output/
└── 2026-06-28_1430/
    ├── business-rules.md     → the objective, the PO-said vs PO-meant translation, key rules and constraints
    ├── scenarios.md          → Gherkin happy-path and edge-case scenarios
    ├── diagram.md            → the Mermaid architecture/flow diagram
    └── open-questions.md     → critical questions still worth raising with the PO
```

Clicking "Generate docs" again later for the same feature — say, after a follow-up meeting clarifies something — creates a **new** timestamped folder rather than overwriting the old one. This means you can see how understanding of a feature evolved over time, and nothing you previously generated is silently lost or replaced.

One file is a little different: `open-questions.md` is built fresh each time by checking against that feature's `input/documents/answered-questions.md` (see §7), so a question you've told the app was answered during chat won't show up in the *next* `open-questions.md` you generate for that feature — even though the older snapshot that originally listed it is left untouched, same as every other past run.

### Why the model does the formatting, not a separate template system

The system prompt used during "Generate docs" tells the model exactly what each of these files should contain and how it should be structured — so the model's output already *is* the finished document for each file. The code that saves it to disk doesn't reformat or re-template anything; its only job is creating the timestamped folder and writing each file with the right name.

### What ends up in a feature's `output/`

Only finished, readable business knowledge for that one feature: a timestamped folder per "Generate docs" click, each holding that feature's business rules, scenarios, diagram, and open questions. Nothing temporary or in-progress lives here — working files like raw transcripts and saved chat history live in that same feature's `progress/` folder instead, so `output/` stays something a developer would actually want to browse to understand the feature, and nothing else.

### Where this fits in the bigger picture

This describes how chatting (Flow 1) and "Generate docs" (Flow 2) sit side by side, both drawing on the same underlying context (docs, meetings, web search) but producing very different things — see §1.
