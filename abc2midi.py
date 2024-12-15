import gradio as gr
import mido
from mido import MidiFile, MidiTrack, Message
from music21 import converter, instrument, note, chord, stream, duration, environment
from midi2audio import FluidSynth
import tempfile
import os
import subprocess

# Set the music21 environment to find MuseScore (if available)
us = environment.UserSettings()
# us['musescoreDirectPNGPath'] = '/path/to/musescore'  # Replace with your MuseScore path if needed
# us['musicxmlPath'] = '/path/to/musescore'  # Replace with your MuseScore path if needed

def abc_to_midi(abc_code):
    """Converts ABC notation to a MIDI file and returns the MIDI file path."""
    try:
        # Create a temporary file for the ABC code
        with tempfile.NamedTemporaryFile(suffix='.abc', mode='w', delete=False) as temp_abc:
            temp_abc.write(abc_code)
            abc_file_path = temp_abc.name

        # Parse the ABC file
        s = converter.parse(abc_file_path, format='abc')
        
        # Remove any duplicate time signatures
        for p in s.parts:
            ts_found = False
            for m in p.getElementsByClass('Measure'):
                for ts in m.getElementsByClass('TimeSignature'):
                    if ts_found:
                        m.remove(ts)
                    else:
                        ts_found = True

        # Create MIDI file
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as temp_midi_file:
            midi_file_path = temp_midi_file.name
            s.write('midi', fp=midi_file_path)
            
        # Clean up the temporary ABC file
        os.remove(abc_file_path)
        
        return midi_file_path
    except Exception as e:
        raise gr.Error(f"Error converting ABC to MIDI: {e}")

def play_midi(midi_file_path):
    """Plays the MIDI file using FluidSynth and returns the audio file path."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio_file:
            audio_file_path = temp_audio_file.name
        fs = FluidSynth()
        fs.midi_to_audio(midi_file_path, audio_file_path)
        return audio_file_path
    except Exception as e:
        raise gr.Error(f"Error playing MIDI: {e}")

def convert_abc_and_play(abc_code):
    """Converts ABC to MIDI, plays it, and returns both MIDI and audio file paths."""
    midi_file_path = abc_to_midi(abc_code)
    if midi_file_path:
        audio_file_path = play_midi(midi_file_path)
        return midi_file_path, audio_file_path
    else:
        return None, None

def midi_to_abc(midi_file):
    """Converts a MIDI file to ABC notation and returns the ABC code."""
    try:
        # Use music21 to parse the MIDI file
        midi_stream = converter.parse(midi_file.name)
        
        # Get tempo from the MIDI file
        tempo = None
        for element in midi_stream.recurse():
            if 'TempoIndication' in element.classes:
                tempo = int(element.number)
                break
        
        # If no tempo found, default to 120 BPM
        if tempo is None:
            tempo = 120
        
        # Initialize ABC header
        abc_code = [
            "X:1",
            "T:Converted from MIDI",
            f"Q:1/4={tempo}",  # Add tempo marking
            "M:4/4",
            "L:1/4",  # Base length is quarter note
            "K:C",
            ""  # Empty line before notes
        ]
        
        def duration_to_abc(dur):
            """Convert music21 duration to ABC notation duration."""
            # Get duration in terms of quarter notes
            qlen = dur.quarterLength
            
            # Handle special cases for common note lengths
            if qlen == 0.25:  # Sixteenth note
                return "/4"
            elif qlen == 0.5:  # Eighth note
                return "/2"
            elif qlen == 1.0:  # Quarter note (base length)
                return ""
            elif qlen == 1.5:  # Dotted quarter note
                return "3/2"
            elif qlen == 2.0:  # Half note
                return "2"
            elif qlen == 3.0:  # Dotted half note
                return "3"
            elif qlen == 4.0:  # Whole note
                return "4"
            
            # For other durations, calculate the ratio to quarter note
            ratio = int(qlen * 4) / 4
            if ratio.is_integer():
                return str(int(ratio))
            else:
                return f"{int(qlen * 4)}/4"
        
        # Extract notes and chords
        for element in midi_stream.recurse().notes:
            if isinstance(element, note.Note):
                # Convert note to ABC notation with duration
                pitch_name = element.nameWithOctave
                # Convert music21 pitch name to ABC notation
                abc_note = pitch_name.replace('4', '').replace('5', "'").replace('3', ',')
                # Add duration
                abc_note += duration_to_abc(element.duration)
                abc_code.append(abc_note)
            elif isinstance(element, chord.Chord):
                # Convert chord to ABC notation with duration
                chord_notes = [n.nameWithOctave for n in element.notes]
                # Convert music21 chord to ABC notation
                abc_chord = "[" + " ".join(n.replace('4', '').replace('5', "'").replace('3', ',') for n in chord_notes) + "]"
                # Add duration
                abc_chord += duration_to_abc(element.duration)
                abc_code.append(abc_chord)
        
        # Join all parts with proper line breaks and add bar lines
        notes_list = abc_code[7:]  # Get all notes after the header
        measures = []
        current_measure = []
        current_length = 0
        
        # Split into measures (assuming 4/4 time, each measure is 4 quarter notes)
        for note_str in notes_list:
            current_measure.append(note_str)
            # Calculate duration based on ABC notation
            dur = 1.0  # Default to quarter note
            if '/' in note_str:
                if '/4' in note_str:
                    dur = 0.25  # Sixteenth note
                elif '/2' in note_str:
                    dur = 0.5  # Eighth note
            elif any(str(i) in note_str for i in range(2, 9)):
                # Get the duration number
                num = int(''.join(c for c in note_str if c.isdigit()))
                dur = float(num)
            
            current_length += dur
            if current_length >= 4.0:  # Full measure (4 quarter notes)
                measures.append(" ".join(current_measure) + " |")
                current_measure = []
                current_length = 0
        
        # Add any remaining notes
        if current_measure:
            measures.append(" ".join(current_measure) + " |")
        
        # Combine header with measures
        return "\n".join(abc_code[:7] + [" ".join(measures)])

    except Exception as e:
        raise gr.Error(f"Error converting MIDI to ABC: {e}")

def chord_to_midi(chord_name):
    """Converts a chord name to a MIDI file and returns the MIDI file path."""
    try:
        c = chord.Chord(chord_name)
        c.duration = duration.Duration(4)  # Set duration to 4 quarter notes (adjust as needed)
        s = stream.Stream()
        s.append(c)
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as temp_midi_file:
            midi_file_path = temp_midi_file.name
            s.write('midi', fp=midi_file_path)
        return midi_file_path

    except Exception as e:
        raise gr.Error(f"Error converting chord to MIDI: {e}")

# Gradio interface
with gr.Blocks(title="ABC to MIDI Converter") as iface:
    gr.Markdown(
        """
        # ABC to MIDI Converter and MIDI to ABC Converter
        This app allows you to convert between ABC notation and MIDI files, play MIDI files, and even generate MIDI from chord names!
        """
    )

    with gr.Tab("ABC to MIDI"):
        abc_input = gr.Textbox(placeholder="Enter ABC notation here...", lines=7, label="ABC Notation")
        with gr.Row():
            abc_midi_output = gr.File(label="MIDI File")
            abc_audio_output = gr.Audio(label="Audio Playback", autoplay=False)  # Autoplay set to False
        abc_button = gr.Button("Convert and Play")

    with gr.Tab("MIDI to ABC"):
        midi_input = gr.File(label="Upload MIDI File", file_types=[".mid", ".midi"])
        midi_abc_output = gr.Textbox(label="ABC Notation", lines=7)
        midi_button = gr.Button("Convert to ABC")

    with gr.Tab("Chord to MIDI"):
        chord_input = gr.Textbox(placeholder="Enter chord name (e.g., Cmaj7, Dm, G7)...", label="Chord Name")
        with gr.Row():
            chord_midi_output = gr.File(label="MIDI File")
            chord_audio_output = gr.Audio(label="Audio Playback")
        chord_button = gr.Button("Convert and Play")

    abc_button.click(convert_abc_and_play, inputs=abc_input, outputs=[abc_midi_output, abc_audio_output])
    midi_button.click(midi_to_abc, inputs=midi_input, outputs=midi_abc_output)
    chord_button.click(lambda chord_name: (chord_to_midi(chord_name), play_midi(chord_to_midi(chord_name))), inputs=chord_input, outputs=[chord_midi_output, chord_audio_output])

iface.launch()