"""
Generate a short sample video file with audio for testing video transcription.

This script creates a minimal MP4 video by combining the existing sample_audio.wav
with a black screen video using ffmpeg.

Requirements:
- ffmpeg must be installed and available in PATH
- sample_audio.wav must exist in the same directory

Usage:
    python generate_sample_video.py
"""

import subprocess
import sys
from pathlib import Path


def generate_sample_video():
    """
    Generate a short MP4 video with black screen and audio from sample_audio.wav.
    
    Output: sample_video.mp4 in the same directory as this script.
    """
    fixtures_dir = Path(__file__).parent
    audio_path = fixtures_dir / "sample_audio.wav"
    output_path = fixtures_dir / "sample_video.mp4"
    
    # Check if sample_audio.wav exists
    if not audio_path.exists():
        print(f"ERROR: {audio_path} not found.")
        print("Run generate_sample_audio.py first to create the audio fixture.")
        sys.exit(1)
    
    # Check if ffmpeg is available
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: ffmpeg is not available.")
        print("Install ffmpeg:")
        print("  Windows: Download from https://ffmpeg.org/ or use 'choco install ffmpeg'")
        print("  Linux: sudo apt install ffmpeg")
        print("  macOS: brew install ffmpeg")
        sys.exit(1)
    
    print(f"Generating sample video: {output_path}")
    print(f"Using audio from: {audio_path}")
    
    # Get audio duration
    probe_command = [
        "ffmpeg",
        "-i", str(audio_path),
        "-f", "null",
        "-"
    ]
    
    try:
        probe_result = subprocess.run(
            probe_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        # Parse duration from stderr (ffmpeg outputs to stderr)
        duration = 3  # Default to 3 seconds
        for line in probe_result.stderr.split('\n'):
            if 'Duration:' in line:
                # Extract duration from format "Duration: 00:00:03.00"
                time_str = line.split('Duration:')[1].split(',')[0].strip()
                print(f"  Audio duration: {time_str}")
                break
    except Exception:
        duration = 3  # Fallback
    
    # Generate MP4 video:
    # - Video: black screen, 1280x720, matching audio duration
    # - Audio: from sample_audio.wav
    ffmpeg_command = [
        "ffmpeg",
        "-f", "lavfi",  # Use libavfilter virtual input
        "-i", f"color=c=black:s=1280x720:r=1",  # Black video, 1fps
        "-i", str(audio_path),  # Audio input
        "-c:v", "libx264",  # H.264 video codec
        "-c:a", "aac",  # AAC audio codec
        "-shortest",  # End when shortest stream ends
        "-pix_fmt", "yuv420p",  # Compatibility pixel format
        "-y",  # Overwrite without asking
        str(output_path)
    ]
    
    try:
        result = subprocess.run(
            ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )
        
        print(f"✓ Sample video generated successfully: {output_path}")
        print(f"  Video: 1280x720, black screen")
        print(f"  Audio: From sample_audio.wav")
        print(f"  Codec: H.264 + AAC")
        
    except subprocess.CalledProcessError as e:
        print(f"ERROR: ffmpeg failed to generate video")
        print(f"Command: {' '.join(ffmpeg_command)}")
        print(f"stderr: {e.stderr}")
        sys.exit(1)


if __name__ == "__main__":
    generate_sample_video()
