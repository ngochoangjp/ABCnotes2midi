import gradio as gr
import google.generativeai as genai
import mido
from mido import MidiFile, MidiTrack, Message
from music21 import converter, instrument, note, chord, stream, duration, environment, roman
from midi2audio import FluidSynth
import tempfile
import os

# Set the music21 environment to find MuseScore (if available)
us = environment.UserSettings()
# us['musescoreDirectPNGPath'] = '/path/to/musescore'  # Replace with your MuseScore path if needed
# us['musicxmlPath'] = '/path/to/musescore'  # Replace with your MuseScore path if needed


# Configure Gemini API
GOOGLE_API_KEY = "AIzaSyB0eYkAM9n4C26Uer2VX7PIQd60c_jVGKY"  # Replace with your actual API key
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-pro")


def generate_abc_with_gemini(prompt):
    """Generates ABC notation using Gemini API."""
    try:
        response = model.generate_content(f"Generate ABC notation based on the following description: {prompt}")
        response.resolve()  # Force full resolve to catch errors
        
        if response.text:
          return response.text
        else:
            raise gr.Error("Gemini returned an empty response")
    except Exception as e:
        raise gr.Error(f"Error generating ABC with Gemini: {e}")


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


def generate_midi_and_play(prompt):
    """Handles the full process: Gemini -> ABC -> MIDI -> Audio."""
    try:
        abc_code = generate_abc_with_gemini(prompt)
        midi_file_path = abc_to_midi(abc_code)
        audio_file_path = play_midi(midi_file_path)
        return midi_file_path, audio_file_path
    except gr.Error as e:
        raise e  # Re-raise Gradio errors to be displayed by the UI
    except Exception as e:
        raise gr.Error(f"An unexpected error occurred: {e}")


# --- Gradio Interface ---
with gr.Blocks(title="AI Music Generator") as iface:
    gr.Markdown(
        """
        # AI Music Generator
        Describe your desired melody, and I'll generate a MIDI and audio demo for you!
        """
    )
    with gr.Column():
      prompt_input = gr.Textbox(
          placeholder="Describe your melody (e.g., 'a happy melody in C major, 120 bpm')",
          label="Melody Description",
          lines=3
      )
      with gr.Row():
        midi_output = gr.File(label="Generated MIDI File")
        audio_output = gr.Audio(label="Generated Audio", autoplay=False)
      generate_button = gr.Button("Generate Music")

    generate_button.click(generate_midi_and_play, inputs=prompt_input, outputs=[midi_output, audio_output])

iface.launch()