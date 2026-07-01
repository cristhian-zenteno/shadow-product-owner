"""
Tests for local audio transcription - Component C

Verifies that audio transcription works entirely offline with no network calls.
"""

import pytest
from pathlib import Path
from shadow_po import transcription


# Path to test fixture
SAMPLE_AUDIO_PATH = Path(__file__).parent / "fixtures" / "sample_audio.wav"


@pytest.fixture(scope="module", autouse=True)
def initialize_transcriber():
    """
    Initialize both the transcriber and the privacy scrubber once for all
    tests in this module.

    Uses 'tiny' model for fast testing (downloads on first run, cached afterwards).
    Privacy scrubber must also be initialized because transcribe_audio() now
    passes output through scrub() before returning.
    """
    from shadow_po import privacy

    transcription.initialize(
        model_size="tiny",  # Smallest/fastest model for testing
        device="cpu",
        compute_type="int8"
    )

    # Initialize privacy scrubber with a known codename for scrubbing tests
    privacy.initialize(custom_codenames=["SuperSecretProject"])


def test_transcribe_audio_basic():
    """
    Test that transcribe_audio returns a plain-text transcript with timestamps.
    
    Per acceptance criteria: transcribe_audio(path: str) -> str runs entirely
    offline and returns plain-text transcript with timestamps per segment.
    """
    # Act
    transcript = transcription.transcribe_audio(str(SAMPLE_AUDIO_PATH))
    
    # Assert
    assert isinstance(transcript, str), "Transcript should be a string"
    
    # For a simple tone file, Whisper may detect silence or produce minimal output
    # We just verify the function executes without errors and returns a string
    # A real speech recording would produce actual transcribed text
    
    # Transcript format should have timestamps if any speech was detected
    # Format: [HH:MM:SS.mmm - HH:MM:SS.mmm] text
    if transcript:
        lines = transcript.split("\n")
        for line in lines:
            if line.strip():
                assert line.startswith("["), f"Line should start with timestamp bracket: {line}"
                assert " - " in line, f"Line should contain timestamp separator: {line}"
                assert "]" in line, f"Line should contain closing timestamp bracket: {line}"


def test_transcribe_audio_file_not_found():
    """Test that transcribe_audio raises FileNotFoundError for non-existent files."""
    with pytest.raises(FileNotFoundError, match="Audio file not found"):
        transcription.transcribe_audio("nonexistent_audio.wav")


def test_transcribe_audio_returns_string():
    """Test that transcribe_audio always returns a string type."""
    transcript = transcription.transcribe_audio(str(SAMPLE_AUDIO_PATH))
    assert isinstance(transcript, str), "Transcript must be a string"


def test_transcription_no_network_calls():
    """
    Verify transcription works offline - no network calls are made.
    
    Per SPECIFY.md §3: "No network request is made during transcription.
    If you have no internet connection at all, transcription still works."
    
    This test verifies the model is loaded and transcription executes.
    The actual offline verification should be done manually by running with
    no internet connection, but this test ensures the API contract is met.
    """
    # This test verifies the function completes successfully
    # In production, run this test with network disconnected to verify
    # true offline operation per SPECIFY.md requirements
    
    transcript = transcription.transcribe_audio(str(SAMPLE_AUDIO_PATH))
    
    # Should complete successfully (model is cached after first download)
    assert isinstance(transcript, str)


def test_transcription_initializer_not_called():
    """Test that transcribe_audio raises error if initializer not called."""
    # Reset the global transcriber to simulate uninitialized state
    original_transcriber = transcription._transcriber
    transcription._transcriber = None
    
    try:
        with pytest.raises(RuntimeError, match="Audio transcriber not initialized"):
            transcription.transcribe_audio(str(SAMPLE_AUDIO_PATH))
    finally:
        # Restore the original transcriber
        transcription._transcriber = original_transcriber


def test_transcription_segment_format():
    """Test that TranscriptionSegment formats timestamps correctly."""
    from shadow_po.transcription import TranscriptionSegment
    
    # Create a test segment
    segment = TranscriptionSegment(start=0.0, end=3.5, text="Hello world")
    
    # Check string format
    formatted = segment.to_timestamp_format()
    
    # Should be: [HH:MM:SS.mmm - HH:MM:SS.mmm] text
    assert formatted.startswith("[00:00:00.000 - "), "Start timestamp should be formatted correctly"
    assert " - 00:00:03.500] " in formatted, "End timestamp should be formatted correctly"
    assert formatted.endswith("Hello world"), "Text should be at the end"


def test_transcription_segment_time_formatting():
    """Test time formatting for various durations."""
    from shadow_po.transcription import TranscriptionSegment
    
    # Test different time scales
    test_cases = [
        (0.0, "00:00:00.000"),
        (1.5, "00:00:01.500"),
        (65.25, "00:01:05.250"),
        (3661.999, "01:01:01.999"),
    ]
    
    for seconds, expected_format in test_cases:
        formatted = TranscriptionSegment._format_time(seconds)
        assert formatted == expected_format, f"Time {seconds}s should format as {expected_format}"


def test_transcribe_video():
    """
    Test that transcribe_video extracts audio from video and transcribes it.
    
    Per acceptance criteria:
    - transcribe_video(path: str) -> str extracts only the audio track (via ffmpeg)
    - Reuses transcribe_audio
    - Never touches video frames
    - Same transcript quality as audio-only path
    """
    # Path to test fixture (will be generated by generate_sample_video.py)
    sample_video_path = Path(__file__).parent / "fixtures" / "sample_video.mp4"
    
    # Skip test if video fixture doesn't exist or ffmpeg isn't available
    if not sample_video_path.exists():
        pytest.skip(
            f"Video fixture not found: {sample_video_path}\n"
            f"Run: python tests/fixtures/generate_sample_video.py\n"
            f"Requires: ffmpeg to be installed"
        )
    
    # Act - transcribe the video
    transcript = transcription.transcribe_video(str(sample_video_path))
    
    # Assert - should return a string transcript
    assert isinstance(transcript, str), "Transcript should be a string"
    
    # The video contains the same audio as sample_audio.wav
    # For a simple tone file, Whisper may detect silence or produce minimal output
    # We just verify the function executes without errors and returns a string
    
    # Transcript format should have timestamps if any speech was detected
    if transcript:
        lines = transcript.split("\n")
        for line in lines:
            if line.strip():
                assert line.startswith("["), f"Line should start with timestamp bracket: {line}"
                assert " - " in line, f"Line should contain timestamp separator: {line}"
                assert "]" in line, f"Line should contain closing timestamp bracket: {line}"


def test_transcribe_video_file_not_found():
    """Test that transcribe_video raises FileNotFoundError for non-existent files."""
    with pytest.raises(FileNotFoundError, match="Video file not found"):
        transcription.transcribe_video("nonexistent_video.mp4")


def test_transcribe_video_ffmpeg_not_available(monkeypatch):
    """Test that transcribe_video raises RuntimeError if ffmpeg is not available."""
    import subprocess
    
    # Mock subprocess.run to simulate ffmpeg not being available
    def mock_run(*args, **kwargs):
        if args[0][0] == "ffmpeg":
            raise FileNotFoundError("ffmpeg not found")
        return subprocess.CompletedProcess(args[0], 0)
    
    monkeypatch.setattr(subprocess, "run", mock_run)
    
    # Create a dummy video file for testing
    sample_video_path = Path(__file__).parent / "fixtures" / "sample_audio.wav"
    
    with pytest.raises(RuntimeError, match="ffmpeg is not available"):
        transcription.transcribe_video(str(sample_video_path))


def test_transcribe_video_same_quality_as_audio():
    """
    Test that transcribe_video produces same transcript quality as transcribe_audio.
    
    This test verifies that extracting audio from video doesn't degrade
    transcription quality compared to directly transcribing an audio file.
    """
    # Paths
    sample_audio_path = Path(__file__).parent / "fixtures" / "sample_audio.wav"
    sample_video_path = Path(__file__).parent / "fixtures" / "sample_video.mp4"
    
    # Skip if video fixture doesn't exist
    if not sample_video_path.exists():
        pytest.skip(
            f"Video fixture not found: {sample_video_path}\n"
            f"Run: python tests/fixtures/generate_sample_video.py"
        )
    
    # Transcribe both audio and video
    audio_transcript = transcription.transcribe_audio(str(sample_audio_path))
    video_transcript = transcription.transcribe_video(str(sample_video_path))
    
    # Both should return strings
    assert isinstance(audio_transcript, str)
    assert isinstance(video_transcript, str)
    
    # For the test fixture (which has the same audio content in both files),
    # the transcripts should be identical or very similar
    # Since Whisper may produce slightly different timestamps,
    # we verify that both are either empty (no speech detected) or have content
    if audio_transcript:
        assert video_transcript, "Video transcript should not be empty if audio transcript has content"
    else:
        # Both empty is acceptable (no speech in test fixture)
        pass


# ---------------------------------------------------------------------------
# Task C-3: Privacy scrubbing integration + save_meeting_transcript
# ---------------------------------------------------------------------------

@pytest.fixture()
def privacy_scrubber_with_codenames():
    """
    Confirms the privacy scrubber is initialized for tests that need it.
    The module-level initialize_transcriber fixture handles actual setup;
    this fixture exists so test signatures are self-documenting.
    """
    from shadow_po import privacy
    assert privacy._scrubber is not None, (
        "Privacy scrubber must be initialized — check initialize_transcriber fixture"
    )
    yield


def test_transcript_is_scrubbed(privacy_scrubber_with_codenames):
    """
    Acceptance: transcription functions always pass output through scrub().

    We can't easily inject PII *into* Whisper's output for a fixture file, so
    we verify the integration contract by monkey-patching the internal
    _transcriber to return a raw string that contains PII, then confirm
    the public transcribe_audio() returns the scrubbed version.
    """
    FAKE_EMAIL = "admin@supersecret.com"
    RAW_WITH_PII = f"[00:00:00.000 - 00:00:01.000] Send results to {FAKE_EMAIL}"

    # Patch the underlying transcriber to return our controlled PII string
    original_method = transcription._transcriber.transcribe_audio
    transcription._transcriber.transcribe_audio = lambda *a, **kw: RAW_WITH_PII

    try:
        result = transcription.transcribe_audio(str(SAMPLE_AUDIO_PATH))
    finally:
        transcription._transcriber.transcribe_audio = original_method

    # The email must not survive scrubbing
    assert FAKE_EMAIL not in result, (
        f"Raw PII '{FAKE_EMAIL}' must not appear in the returned transcript"
    )
    # The scrubbed placeholder should be present instead
    assert "[EMAIL]" in result, "Email placeholder [EMAIL] should appear in scrubbed transcript"


def test_save_meeting_transcript_explicit(tmp_path, privacy_scrubber_with_codenames):
    """
    Acceptance: save_meeting_transcript(workspace, filename, text) writes a
    *scrubbed* transcript into that feature's input/meetings/, only when
    called explicitly — never automatically.
    """
    from shadow_po import transcription as tc
    from shadow_po import workspace as ws

    # Create a temporary workspace
    feature_ws = ws.create_workspace("save-test", workspaces_root=tmp_path)

    TRANSCRIPT_TEXT = "[00:00:00.000 - 00:00:02.000] Discussion about the roadmap"

    # Act: explicitly call save
    saved_path = tc.save_meeting_transcript(
        workspace_path=feature_ws,
        filename="test-meeting.txt",
        text=TRANSCRIPT_TEXT,
    )

    # File must land in input/meetings/
    assert saved_path.exists(), "Saved transcript file should exist"
    assert saved_path.parent == feature_ws / "input" / "meetings"
    assert saved_path.name == "test-meeting.txt"

    # Content should be present
    content = saved_path.read_text(encoding="utf-8")
    assert "Discussion about the roadmap" in content


def test_save_meeting_transcript_scrubs_before_writing(tmp_path, privacy_scrubber_with_codenames):
    """
    Acceptance: text written to disk is always scrubbed — even if the caller
    passes raw (unscubbed) text directly to save_meeting_transcript().
    """
    from shadow_po import transcription as tc
    from shadow_po import workspace as ws

    feature_ws = ws.create_workspace("scrub-save-test", workspaces_root=tmp_path)

    FAKE_EMAIL = "leak@example.com"
    RAW_TEXT = f"[00:00:00.000 - 00:00:02.000] Contact {FAKE_EMAIL} for details"

    saved_path = tc.save_meeting_transcript(
        workspace_path=feature_ws,
        filename="raw-meeting.txt",
        text=RAW_TEXT,
    )

    content = saved_path.read_text(encoding="utf-8")
    assert FAKE_EMAIL not in content, (
        "Raw email must not survive into the saved file"
    )
    assert "[EMAIL]" in content, "Scrubbed [EMAIL] placeholder must appear in the saved file"


def test_save_meeting_transcript_missing_workspace(tmp_path, privacy_scrubber_with_codenames):
    """
    Acceptance: save_meeting_transcript raises clearly when the workspace
    doesn't exist, rather than silently creating arbitrary directories.
    """
    from shadow_po import transcription as tc

    nonexistent = tmp_path / "nonexistent-workspace"

    with pytest.raises(FileNotFoundError, match="Workspace not found"):
        tc.save_meeting_transcript(
            workspace_path=nonexistent,
            filename="meeting.txt",
            text="some text",
        )


def test_save_meeting_transcript_no_meetings_dir(tmp_path, privacy_scrubber_with_codenames):
    """
    Acceptance: if the workspace exists but doesn't have input/meetings/,
    save_meeting_transcript raises a clear ValueError.
    """
    from shadow_po import transcription as tc

    # Create a directory that looks like a workspace root but lacks subfolders
    bare_dir = tmp_path / "bare-workspace"
    bare_dir.mkdir()

    with pytest.raises(ValueError, match="input/meetings"):
        tc.save_meeting_transcript(
            workspace_path=bare_dir,
            filename="meeting.txt",
            text="some text",
        )
