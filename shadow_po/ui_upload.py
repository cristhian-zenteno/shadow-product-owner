"""
Streamlit UI — File Upload Panel (Component J)

Handles document and audio/video upload into the active workspace.
- Documents → input/documents/ + triggers indexing
- Audio/video → transcription → preview → explicit save to input/meetings/
"""

import streamlit as st
from pathlib import Path
import tempfile
import os


def render_upload_panel(workspace_path: Path) -> None:
    """
    Render the file upload panel for a feature workspace.

    Args:
        workspace_path: Path to the currently active workspace root
    """
    st.subheader("📎 Upload Files")

    tab_docs, tab_media = st.tabs(["📄 Documents", "🎤 Meetings / Recordings"])

    # -----------------------------------------------------------------------
    # Documents tab
    # -----------------------------------------------------------------------
    with tab_docs:
        st.markdown(
            "Upload PDFs, Word documents, PowerPoints, or Markdown files. "
            "They will be indexed immediately and become retrievable in chat."
        )

        uploaded_docs = st.file_uploader(
            "Choose document(s)",
            accept_multiple_files=True,
            type=["pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls", "md", "txt"],
            key="doc_uploader",
        )

        if uploaded_docs:
            if st.button("📥 Save & Index documents", key="save_docs_btn"):
                _save_and_index_documents(workspace_path, uploaded_docs)

    # -----------------------------------------------------------------------
    # Recordings tab
    # -----------------------------------------------------------------------
    with tab_media:
        st.markdown(
            "Upload an audio or video recording. "
            "It will be transcribed locally — no audio leaves your machine."
        )

        uploaded_media = st.file_uploader(
            "Choose audio or video file",
            accept_multiple_files=False,
            type=["wav", "mp3", "m4a", "mp4", "mov", "avi", "mkv", "webm"],
            key="media_uploader",
        )

        if uploaded_media:
            _handle_media_upload(workspace_path, uploaded_media)


def _save_and_index_documents(workspace_path: Path, uploaded_files) -> None:
    """Save uploaded documents and trigger indexing."""
    from shadow_po import knowledge_base as kb, privacy

    docs_dir = workspace_path / "input" / "documents"

    with st.spinner("Saving and indexing documents…"):
        saved = []
        for uf in uploaded_files:
            dest = docs_dir / uf.name
            dest.write_bytes(uf.read())
            saved.append(uf.name)

        # Ensure privacy scrubber is initialised
        if privacy._scrubber is None:
            from shadow_po.config import load_settings
            settings = load_settings()
            codenames = settings.privacy.codenames if settings.privacy else []
            privacy.initialize(custom_codenames=codenames)

        try:
            count = kb.index_workspace_documents(workspace_path)
            st.success(
                f"Saved {len(saved)} file(s) and indexed {count} chunks.\n"
                + "\n".join(f"  ✓ {n}" for n in saved)
            )
        except Exception as exc:
            st.error(f"Indexing failed: {exc}")


def _handle_media_upload(workspace_path: Path, uploaded_file) -> None:
    """Transcribe uploaded audio/video and offer to save it."""
    from shadow_po import transcription, privacy

    # Ensure scrubber + transcriber are initialised
    if privacy._scrubber is None:
        from shadow_po.config import load_settings
        settings = load_settings()
        codenames = settings.privacy.codenames if settings.privacy else []
        privacy.initialize(custom_codenames=codenames)

    if transcription._transcriber is None:
        from shadow_po.config import load_settings
        settings = load_settings()
        transcription.initialize(
            model_size=settings.whisper.model_size,
            device=settings.whisper.device,
            compute_type=settings.whisper.compute_type,
        )

    transcript_key = f"transcript_{uploaded_file.name}"

    if transcript_key not in st.session_state:
        with st.spinner(f"Transcribing '{uploaded_file.name}' locally…"):
            suffix = Path(uploaded_file.name).suffix.lower()
            with tempfile.NamedTemporaryFile(
                suffix=suffix, delete=False
            ) as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name

            try:
                if suffix in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
                    transcript = transcription.transcribe_video(tmp_path)
                else:
                    transcript = transcription.transcribe_audio(tmp_path)
                st.session_state[transcript_key] = transcript
            except Exception as exc:
                st.error(f"Transcription failed: {exc}")
                return
            finally:
                os.unlink(tmp_path)

    transcript = st.session_state.get(transcript_key, "")

    if transcript:
        st.text_area(
            "Transcript preview (scrubbed)",
            value=transcript,
            height=200,
            key=f"preview_{uploaded_file.name}",
            disabled=True,
        )

        save_name = st.text_input(
            "Save transcript as",
            value=Path(uploaded_file.name).stem + ".txt",
            key=f"save_name_{uploaded_file.name}",
        )

        if st.button("💾 Save transcript to meetings/", key=f"save_transcript_{uploaded_file.name}"):
            try:
                saved_path = transcription.save_meeting_transcript(
                    workspace_path=workspace_path,
                    filename=save_name,
                    text=transcript,
                )
                st.success(f"Saved: {saved_path.name}")
                # Clear cached transcript so re-upload works cleanly
                del st.session_state[transcript_key]
            except Exception as exc:
                st.error(f"Save failed: {exc}")
    else:
        st.warning("No speech detected in the recording.")
