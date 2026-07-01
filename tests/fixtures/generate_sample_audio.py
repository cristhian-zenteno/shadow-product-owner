"""
Generate a sample WAV audio file for testing transcription.

This script generates a simple sine wave audio file that can be used
for testing the transcription module. While the transcription won't
produce meaningful text (it's just a tone), it verifies the technical
pipeline works.

For realistic testing, we'll need an actual speech recording.
"""

import wave
import math
import struct

def generate_tone_wav(filename: str, frequency: float = 440.0, duration: float = 3.0, sample_rate: int = 16000):
    """
    Generate a simple sine wave tone as a WAV file.
    
    Args:
        filename: Output WAV file path
        frequency: Frequency in Hz (default: 440Hz = A4 note)
        duration: Duration in seconds
        sample_rate: Sample rate in Hz (16kHz is standard for speech)
    """
    num_samples = int(sample_rate * duration)
    
    # Generate sine wave samples
    samples = []
    for i in range(num_samples):
        # Generate sine wave value (-1 to 1)
        value = math.sin(2.0 * math.pi * frequency * i / sample_rate)
        # Convert to 16-bit integer (-32768 to 32767)
        sample = int(value * 32767)
        samples.append(sample)
    
    # Write WAV file
    with wave.open(filename, 'w') as wav_file:
        # Set WAV parameters: 1 channel (mono), 2 bytes per sample (16-bit), sample rate
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        
        # Pack samples as binary data
        for sample in samples:
            wav_file.writeframes(struct.pack('<h', sample))
    
    print(f"Generated {filename}: {duration}s @ {sample_rate}Hz")


if __name__ == "__main__":
    # Generate a 3-second test tone
    generate_tone_wav("sample_audio.wav", frequency=440.0, duration=3.0)
