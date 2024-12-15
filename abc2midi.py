import gradio as gr
import mido
from mido import MidiFile, MidiTrack, Message
from music21 import converter, instrument, note, chord, stream
from midi2audio import FluidSynth
import tempfile
import os

def abc_to_midi(abc_code):
    """Converts ABC notation to a MIDI file and returns the MIDI file path."""
    try:
        # Parse ABC notation using music21
        s = converter.parse(abc_code, format='abc')

        # Create a temporary MIDI file
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as temp_midi_file:
            midi_file_path = temp_midi_file.name

            # Write the music21 stream to the MIDI file
            s.write('midi', fp=midi_file_path)

        return midi_file_path

    except Exception as e:
        raise gr.Error(f"Error converting ABC to MIDI: {e}")

def play_midi(midi_file_path):
    """Plays the MIDI file using FluidSynth and returns the audio file path."""
    try:
        # Create a temporary audio file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio_file:
            audio_file_path = temp_audio_file.name
        
        # Convert MIDI to audio using FluidSynth
        fs = FluidSynth()  # You may need to specify the path to a soundfont file
        fs.midi_to_audio(midi_file_path, audio_file_path)

        return audio_file_path

    except Exception as e:
        raise gr.Error(f"Error playing MIDI: {e}")

def convert_and_play(abc_code):
    """Converts ABC to MIDI, plays it, and returns both MIDI and audio file paths."""
    midi_file_path = abc_to_midi(abc_code)
    if midi_file_path:
        audio_file_path = play_midi(midi_file_path)
        return midi_file_path, audio_file_path
    else:
        return None, None

# Gradio interface
iface = gr.Interface(
    fn=convert_and_play,
    inputs=gr.Textbox(placeholder="Enter ABC notation here...", lines=7, label="ABC Notation"),
    outputs=[
        gr.File(label="MIDI File"),
        gr.Audio(label="Audio Playback", autoplay=True)
    ],
    title="ABC to MIDI Converter",
    description="""
    Enter your ABC notation in the textbox and click "Submit" to convert it to MIDI and hear it played back.
    
    **Example ABC Notation (Twinkle Twinkle Little Star):**
    ```
    X: 1
    T: Twinkle Twinkle Little Star
    M: 4/4
    L: 1/4
    K: C
    C C G G | A A G2 | F F E E | D D C2 |
    G G F F | E E D2 | G G F F | E E D2 |
    C C G G | A A G2 | F F E E | D D C2 |
    ```
    """,
    allow_flagging="never",  # Disable flagging since we're using temporary files
)

iface.launch()