"""
Local Audio Transcription - Component C

Wraps faster-whisper for offline audio/video → text transcription.
No network calls during transcription (per SPECIFY.md §3).

This component depends on:
- Component A (workspace manager) - needs input/meetings/ to exist
- Component B (privacy scrubber) - output must pass through scrubbing

Returns plain-text transcript with timestamps per segment.
Raw (unscrubbed) transcripts are temporary - scrubbing happens downstream.
"""

from pathlib import Path
from typing import Optional, List, Union
import logging
import subprocess
import tempfile
import os

from faster_whisper import WhisperModel

# Configure logger
logger = logging.getLogger(__name__)


class TranscriptionSegment:
    """
    Represents a single transcription segment with timing information.
    
    Attributes:
        start: Start time in seconds
        end: End time in seconds
        text: Transcribed text for this segment
    """
    
    def __init__(self, start: float, end: float, text: str):
        self.start = start
        self.end = end
        self.text = text.strip()
    
    def __repr__(self) -> str:
        return f"TranscriptionSegment(start={self.start:.2f}s, end={self.end:.2f}s, text='{self.text[:50]}...')"
    
    def to_timestamp_format(self) -> str:
        """
        Format segment as timestamped text line.
        
        Returns:
            String in format: "[HH:MM:SS.mmm - HH:MM:SS.mmm] text"
        """
        start_formatted = self._format_time(self.start)
        end_formatted = self._format_time(self.end)
        return f"[{start_formatted} - {end_formatted}] {self.text}"
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        """
        Format seconds as HH:MM:SS.mmm timestamp.
        
        Args:
            seconds: Time in seconds (float)
            
        Returns:
            Formatted timestamp string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


class AudioTranscriber:
    """
    Wraps faster-whisper for local offline audio transcription.
    
    All transcription runs entirely offline with no network calls.
    Model is downloaded once on first use, then cached locally.
    """
    
    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8"
    ):
        """
        Initialize the Whisper transcription model.
        
        Args:
            model_size: Whisper model size (tiny, base, small, medium, large-v3)
            device: Device to run on (cpu or cuda)
            compute_type: Compute type for inference (int8, float16, float32)
            
        Note:
            Model will be downloaded on first use if not already cached.
            After download, all transcription runs offline.
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        
        logger.info(
            f"Initializing Whisper model: size={model_size}, "
            f"device={device}, compute_type={compute_type}"
        )
        
        # Initialize the model (downloads if needed, then cached locally)
        try:
            self.model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type
            )
            logger.info("Whisper model initialized successfully")
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize Whisper model '{model_size}': {str(e)}\n"
                f"Ensure faster-whisper is installed: uv add faster-whisper"
            ) from e
    
    def transcribe_audio(
        self,
        audio_path: str,
        language: Optional[str] = None,
        beam_size: int = 5,
        vad_filter: bool = True
    ) -> str:
        """
        Transcribe audio file to plain-text with timestamps per segment.
        
        This function runs entirely offline - no network calls are made.
        
        Args:
            audio_path: Path to audio/video file (WAV, MP3, MP4, etc.)
            language: Language code (e.g., 'en', 'es'). None for auto-detection.
            beam_size: Beam size for decoding (higher = more accurate but slower)
            vad_filter: Enable Voice Activity Detection to filter silence
            
        Returns:
            Plain-text transcript with timestamps per segment, one segment per line
            Format: "[HH:MM:SS.mmm - HH:MM:SS.mmm] transcribed text"
            
        Raises:
            FileNotFoundError: If audio file does not exist
            RuntimeError: If transcription fails
            
        Example:
            >>> transcriber = AudioTranscriber(model_size="base")
            >>> transcript = transcriber.transcribe_audio("meeting.wav")
            >>> print(transcript)
            [00:00:00.000 - 00:00:03.500] Welcome to the product planning meeting.
            [00:00:03.500 - 00:00:07.200] Today we'll discuss the new checkout feature.
        """
        audio_file = Path(audio_path)
        
        if not audio_file.exists():
            raise FileNotFoundError(
                f"Audio file not found: {audio_path}\n"
                f"Ensure the file exists before calling transcribe_audio()."
            )
        
        logger.info(f"Starting transcription: {audio_path}")
        
        try:
            # Transcribe the audio file
            # Note: faster-whisper returns (segments, info) tuple
            segments, info = self.model.transcribe(
                str(audio_file),
                language=language,
                beam_size=beam_size,
                vad_filter=vad_filter,
                word_timestamps=False  # We only need segment-level timestamps
            )
            
            # Log detected language
            detected_language = info.language if hasattr(info, 'language') else 'unknown'
            language_prob = info.language_probability if hasattr(info, 'language_probability') else 0.0
            logger.info(
                f"Detected language: {detected_language} "
                f"(probability: {language_prob:.2f})"
            )
            
            # Convert segments to timestamped text format
            transcript_lines: List[str] = []
            segment_count = 0
            
            for segment in segments:
                ts_segment = TranscriptionSegment(
                    start=segment.start,
                    end=segment.end,
                    text=segment.text
                )
                transcript_lines.append(ts_segment.to_timestamp_format())
                segment_count += 1
            
            if segment_count == 0:
                logger.warning(
                    f"No speech detected in audio file: {audio_path}\n"
                    f"The file may be empty, silent, or corrupted."
                )
                return ""
            
            logger.info(
                f"Transcription complete: {segment_count} segments, "
                f"{len(' '.join(transcript_lines).split())} words"
            )
            
            # Join all segments with newlines
            return "\n".join(transcript_lines)
            
        except Exception as e:
            raise RuntimeError(
                f"Transcription failed for {audio_path}: {str(e)}\n"
                f"Ensure the file is a valid audio/video format."
            ) from e


# Global transcriber instance (initialized with settings at app startup)
_transcriber: Optional[AudioTranscriber] = None


def initialize(
    model_size: str = "base",
    device: str = "cpu",
    compute_type: str = "int8"
) -> None:
    """
    Initialize the global audio transcriber instance.
    
    Must be called once at application startup before any transcribe_audio() calls.
    
    Args:
        model_size: Whisper model size (tiny, base, small, medium, large-v3)
        device: Device to run on (cpu or cuda)
        compute_type: Compute type for inference (int8, float16, float32)
    """
    global _transcriber
    _transcriber = AudioTranscriber(
        model_size=model_size,
        device=device,
        compute_type=compute_type
    )


def initialize_from_settings(settings_path: str = "settings.yaml") -> None:
    """
    Initialize the global transcriber from settings.yaml configuration.
    
    This is the recommended initialization method for application startup.
    Loads Whisper configuration from the 'whisper' section in settings.yaml.
    
    Args:
        settings_path: Path to settings.yaml file (default: "settings.yaml")
        
    Raises:
        FileNotFoundError: If settings.yaml does not exist
        ValueError: If settings.yaml is invalid
    """
    from shadow_po.config import load_settings
    
    settings = load_settings(settings_path)
    
    initialize(
        model_size=settings.whisper.model_size,
        device=settings.whisper.device,
        compute_type=settings.whisper.compute_type
    )


def transcribe_audio(path: str) -> str:
    """
    One-call transcription function - the public API.

    Transcribes audio/video file to plain-text with timestamps per segment,
    then passes the result through the privacy scrubber before returning.
    Runs entirely offline - no network calls are made during transcription.

    Args:
        path: Path to audio/video file

    Returns:
        Scrubbed plain-text transcript with timestamps per segment.
        Format: "[HH:MM:SS.mmm - HH:MM:SS.mmm] transcribed text"

    Raises:
        RuntimeError: If transcriber not initialized
        FileNotFoundError: If audio file does not exist

    Example:
        >>> from shadow_po import transcription
        >>> transcription.initialize_from_settings()
        >>> transcript = transcription.transcribe_audio("meeting.wav")
    """
    if _transcriber is None:
        raise RuntimeError(
            "Audio transcriber not initialized. "
            "Call transcription.initialize() or transcription.initialize_from_settings() "
            "at app startup."
        )

    raw_transcript = _transcriber.transcribe_audio(path)
    return _scrub_transcript(raw_transcript)


def transcribe_audio_raw(path: str) -> str:
    """
    Internal helper: transcribe without scrubbing.

    Used by transcribe_video to avoid double-scrubbing when video extraction
    delegates to this function before the final scrub is applied.
    Should not be called directly by application code.

    Args:
        path: Path to audio file (temporary extracted audio from video)

    Returns:
        Raw (unscrubbed) plain-text transcript with timestamps per segment.
    """
    if _transcriber is None:
        raise RuntimeError(
            "Audio transcriber not initialized. "
            "Call transcription.initialize() or transcription.initialize_from_settings() "
            "at app startup."
        )

    return _transcriber.transcribe_audio(path)


def _scrub_transcript(raw_text: str) -> str:
    """
    Pass transcript text through the privacy scrubber.

    Imports lazily to avoid circular imports at module load time.
    Falls back gracefully if privacy module is not yet initialized,
    raising loudly so callers are aware scrubbing was skipped.

    Args:
        raw_text: Unscrubbed transcript text

    Returns:
        Scrubbed transcript text

    Raises:
        RuntimeError: If privacy scrubber is not initialized
    """
    from shadow_po import privacy  # lazy import to avoid circular deps

    try:
        return privacy.scrub(raw_text)
    except RuntimeError as e:
        # Re-raise with extra context so caller knows this is a scrubbing failure
        raise RuntimeError(
            f"Transcription output could not be scrubbed: {e}\n"
            "Initialize the privacy scrubber before calling transcription functions."
        ) from e


def transcribe_video(path: str) -> str:
    """
    Transcribe video file by extracting audio track and reusing transcribe_audio.
    
    This function extracts only the audio track from video files using ffmpeg
    and delegates transcription to transcribe_audio(). Per SPECIFY.md §3:
    "the app extracts just the audio track from video — it never looks at 
    video frames, slides, or screen-shares."
    
    The extracted audio is temporary and cleaned up after transcription.
    Runs entirely offline - no network calls are made.
    
    Args:
        path: Path to video file (MP4, AVI, MOV, MKV, etc.)
        
    Returns:
        Plain-text transcript with timestamps per segment
        Format: "[HH:MM:SS.mmm - HH:MM:SS.mmm] transcribed text"
        
    Raises:
        RuntimeError: If transcriber not initialized or ffmpeg not available
        FileNotFoundError: If video file does not exist
        
    Example:
        >>> from shadow_po import transcription
        >>> transcription.initialize_from_settings()
        >>> transcript = transcription.transcribe_video("meeting.mp4")
    """
    if _transcriber is None:
        raise RuntimeError(
            "Audio transcriber not initialized. "
            "Call transcription.initialize() or transcription.initialize_from_settings() "
            "at app startup."
        )
    
    video_file = Path(path)
    
    if not video_file.exists():
        raise FileNotFoundError(
            f"Video file not found: {path}\n"
            f"Ensure the file exists before calling transcribe_video()."
        )
    
    logger.info(f"Extracting audio from video: {path}")
    
    # Check if ffmpeg is available
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(
            "ffmpeg is not available. Install ffmpeg to transcribe video files.\n"
            "Windows: Download from https://ffmpeg.org/ or use 'choco install ffmpeg'\n"
            "Linux: sudo apt install ffmpeg\n"
            "macOS: brew install ffmpeg"
        ) from e
    
    # Create temporary file for extracted audio
    temp_audio_fd, temp_audio_path = tempfile.mkstemp(suffix=".wav", prefix="shadow_po_audio_")
    
    try:
        # Close the file descriptor immediately (we just need the path)
        os.close(temp_audio_fd)
        
        # Extract audio using ffmpeg
        # -i: input video file
        # -vn: no video (audio only)
        # -acodec pcm_s16le: convert to WAV PCM format
        # -ar 16000: 16kHz sample rate (good for speech, Whisper-friendly)
        # -ac 1: mono audio
        # -y: overwrite output file without asking
        ffmpeg_command = [
            "ffmpeg",
            "-i", str(video_file),
            "-vn",  # No video
            "-acodec", "pcm_s16le",  # WAV PCM format
            "-ar", "16000",  # 16kHz sample rate
            "-ac", "1",  # Mono
            "-y",  # Overwrite
            temp_audio_path
        ]
        
        logger.info(f"Running ffmpeg to extract audio to {temp_audio_path}")
        
        result = subprocess.run(
            ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )
        
        logger.info("Audio extraction complete")
        
        # Verify the extracted audio file exists and has content
        if not os.path.exists(temp_audio_path) or os.path.getsize(temp_audio_path) == 0:
            raise RuntimeError(
                f"Failed to extract audio from video: {path}\n"
                f"The video may not contain an audio track or may be corrupted."
            )
        
        # Transcribe the extracted audio (raw, without scrubbing yet)
        logger.info(f"Transcribing extracted audio from video: {path}")
        raw_transcript = transcribe_audio_raw(temp_audio_path)

        # Scrub once, here, before returning — never double-scrub
        transcript = _scrub_transcript(raw_transcript)

        logger.info(f"Video transcription complete: {path}")

        return transcript
        
    except subprocess.CalledProcessError as e:
        error_message = e.stderr if e.stderr else str(e)
        raise RuntimeError(
            f"ffmpeg failed to extract audio from {path}:\n{error_message}\n"
            f"The video file may be corrupted or in an unsupported format."
        ) from e
    
    finally:
        # Clean up temporary audio file
        try:
            if os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)
                logger.info(f"Cleaned up temporary audio file: {temp_audio_path}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to clean up temporary file {temp_audio_path}: {cleanup_error}")


def save_meeting_transcript(
    workspace_path: Union[str, Path],
    filename: str,
    text: str
) -> Path:
    """
    Explicitly save a scrubbed transcript into the workspace's input/meetings/ folder.

    This function is intentionally NOT called automatically by transcribe_audio()
    or transcribe_video(). The caller decides when to persist a transcript.
    Per SPECIFY.md §3: saving is always a deliberate, user-triggered action.

    The ``text`` argument is expected to already be scrubbed (it comes from
    transcribe_audio() or transcribe_video(), both of which pass output through
    the privacy scrubber). As a defence-in-depth measure this function scrubs
    the text a second time only if the privacy module is initialized; if it is
    not initialized it refuses to write and raises loudly.

    Args:
        workspace_path: Path to the feature workspace root
                        (e.g. "workspaces/1-click-checkout")
        filename: Filename for the saved transcript (e.g. "sprint-planning.txt")
        text: Scrubbed transcript text to save

    Returns:
        Path: Full path to the saved file

    Raises:
        RuntimeError: If privacy scrubber is not initialized (fail-loud)
        ValueError: If workspace does not have the expected input/meetings/ folder
        FileNotFoundError: If the workspace path does not exist

    Example:
        >>> from shadow_po import transcription
        >>> transcript = transcription.transcribe_audio("meeting.wav")
        >>> saved = transcription.save_meeting_transcript(
        ...     "workspaces/1-click-checkout", "sprint-planning.txt", transcript
        ... )
    """
    workspace = Path(workspace_path)

    if not workspace.exists():
        raise FileNotFoundError(
            f"Workspace not found: {workspace_path}\n"
            "Create the workspace with workspace.create_workspace() before saving transcripts."
        )

    meetings_dir = workspace / "input" / "meetings"

    if not meetings_dir.exists():
        raise ValueError(
            f"Expected 'input/meetings/' folder not found in workspace: {workspace_path}\n"
            "Ensure the workspace was created with workspace.create_workspace()."
        )

    # Defence-in-depth: scrub the text before writing to disk.
    # This catches cases where a caller passes a raw (unscubbed) string directly.
    scrubbed_text = _scrub_transcript(text)

    dest = meetings_dir / filename
    dest.write_text(scrubbed_text, encoding="utf-8")

    logger.info(f"Meeting transcript saved: {dest}")

    return dest
