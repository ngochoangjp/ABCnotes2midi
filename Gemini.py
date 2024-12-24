import gradio as gr
import google.generativeai as genai
import mido
from mido import MidiFile, MidiTrack, Message
from music21 import converter, instrument, note, chord, stream, duration, environment, roman
from midi2audio import FluidSynth
import tempfile
import os
import re  # import regex for cleaning the abc string
from datetime import datetime
import shutil  # import the shutil library for moving files
import random

# Set the music21 environment to find MuseScore (if available)
us = environment.UserSettings()
# us['musescoreDirectPNGPath'] = '/path/to/musescore'  # Replace with your MuseScore path if needed
# us['musicxmlPath'] = '/path/to/musescore'  # Replace with your MuseScore path if needed

# API Key File Setup
API_KEY_FILE = "api_key.txt"

# Data folder setup
DATA_FOLDER = "UserData"
PROMPT_FOLDER = os.path.join(DATA_FOLDER, "Prompts")
MIDI_FOLDER = os.path.join(DATA_FOLDER, "Midi")
AUDIO_FOLDER = os.path.join(DATA_FOLDER, "Audio")

# Create folders if they don't exist
os.makedirs(PROMPT_FOLDER, exist_ok=True)
os.makedirs(MIDI_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)

# Default "Surprise Me" prompts
surprise_me_prompts = [
    "a happy melody in C major, 120 bpm",
    "a sad melody in A minor, 80 bpm",
    "a lively jazz tune in G major, 140 bpm",
    "a mysterious melody in E minor, 90 bpm",
    "a calm and peaceful melody in F major, 100 bpm"
]


# Load API Key from File
def load_api_key():
    try:
        with open(API_KEY_FILE, "r") as f:
            api_key = f.readline().strip()  # Read the first line and strip leading/trailing spaces
            return api_key
    except FileNotFoundError:
        raise gr.Error(
            f"Error: API key file '{API_KEY_FILE}' not found. Please create this file in the same directory as your script.")
    except Exception as e:
        raise gr.Error(f"Error reading API key from file: {e}")


# Load API Key
GOOGLE_API_KEY = load_api_key()

# Configure Gemini API
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-pro")


def generate_abc_with_gemini(prompt):
    """Generates ABC notation using Gemini API."""
    try:
        response = model.generate_content(
            f"Generate ABC notation based on the following description: {prompt} Please provide ABC format that can be used for generating MIDI files, and dont use lyrics in the output (W: tag)."
        )
        response.resolve()  # Force full resolve to catch errors

        if response.text:
            return response.text
        else:
            raise gr.Error("Gemini returned an empty response")
    except Exception as e:
        raise gr.Error(f"Error generating ABC with Gemini: {e}")


def abc_to_midi(abc_code, tempo):
    """Converts ABC notation to a MIDI file and returns the MIDI file path."""
    try:
        if not abc_code.strip():
            raise gr.Error("Received empty ABC code, please try again")

        abc_code = abc_code.strip()  # remove any empty space at start and end
        # Force add L: 1/8 if it is not there.
        if not re.search(r"^L:\s*1/8", abc_code, re.MULTILINE):
            abc_code = "L: 1/8\n" + abc_code

        # Set the tempo using Q:
        if not re.search(r"^Q:", abc_code, re.MULTILINE):
            abc_code = f"Q:1/4={tempo}\n" + abc_code # set the correct tempo at the ABC string

        # close any open repeats at the end of the line (before the pipe char)
        abc_code = re.sub(r"\|(?=[^\|]*)", r":|", abc_code)

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
        raise gr.Error(f"Error converting ABC to MIDI: {e}. The ABC code was:\n {abc_code}")


def play_midi(midi_file_path):
    """Plays the MIDI file using FluidSynth and returns the audio file path."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".FLAC", delete=False) as temp_audio_file:
            audio_file_path = temp_audio_file.name
        fs = FluidSynth()
        fs.midi_to_audio(midi_file_path, audio_file_path)
        return audio_file_path
    except Exception as e:
        raise gr.Error(f"Error playing MIDI: {e}")


def save_files(prompt, midi_file_path, audio_file_path):
    """Saves prompt, MIDI file, and audio file to data folders."""
    # Get the current count to name the files
    file_count = len(os.listdir(PROMPT_FOLDER)) + 1

    # Save prompt
    prompt_file_name = f"{file_count}.txt"
    prompt_file_path = os.path.join(PROMPT_FOLDER, prompt_file_name)
    with open(prompt_file_path, "w", encoding="utf-8") as f:
        f.write(f"Generated on: {datetime.now()}\n")
        f.write(prompt)

    # Save midi file
    midi_file_name = f"{file_count}.mid"
    new_midi_path = os.path.join(MIDI_FOLDER, midi_file_name)
    shutil.move(midi_file_path, new_midi_path)  # use shutil.move instead of os.rename

    # Save audio file
    audio_file_name = f"{file_count}.FLAC"
    new_audio_path = os.path.join(AUDIO_FOLDER, audio_file_name)
    shutil.move(audio_file_path, new_audio_path)  # use shutil.move instead of os.rename

    return new_midi_path, new_audio_path


def generate_midi_and_play(key, tempo, time_signature, melody_style, range_desc, rhythm_desc,
                           emotion_desc, instrument_desc, prompt_description, bars_number):
    """Handles the full process: Gemini -> ABC -> MIDI -> Audio."""
    # if any field is empty, then use a random prompt
    if not any([key, tempo, time_signature, melody_style, range_desc, rhythm_desc,
            emotion_desc, instrument_desc, prompt_description]):
        random_prompt = random.choice(surprise_me_prompts)
        key = random_prompt.split(",")[0].split("in ")[1].strip() if "in " in random_prompt else ""
        tempo = random_prompt.split(",")[1].strip().split(" ")[0] if "," in random_prompt else ""
        prompt = random_prompt
    else:
        prompt = f"Generate a melody with the following characteristics:"
        if key:
            prompt += f" key: {key},"
        if tempo:
            prompt += f" tempo: {tempo},"
        if time_signature:
            prompt += f" time signature: {time_signature},"
        if melody_style:
            prompt += f" melody style: {melody_style},"
        if range_desc:
            prompt += f" range: {range_desc},"

        if rhythm_desc:
            # Add duration explicitly to the prompt
            if rhythm_desc:
                prompt += f" rhythm: {rhythm_desc}, including a mix of long and short notes, and proper rests, explicitly mark the duration of the notes (e.g., 'a2','b/2', 'c3') , using quarter, eight, and sixteenth notes,"
            else:
                prompt += f" rhythm: with a mix of long and short notes, and proper rests, explicitly mark the duration of the notes (e.g., 'a2','b/2', 'c3') , using quarter, eight, and sixteenth notes,"

        if emotion_desc:
            prompt += f" emotion: {emotion_desc},"
        if instrument_desc:
            prompt += f" instrument: {instrument_desc},"
        if prompt_description:
            prompt += f" additional: {prompt_description}"
        if bars_number:
            prompt += f" and the melody must be of {bars_number} bars" # add bars to the prompt

    try:
        abc_code = generate_abc_with_gemini(prompt)
        midi_file_path = abc_to_midi(abc_code, tempo)
        audio_file_path = play_midi(midi_file_path)
        # Save the data
        midi_file_path, audio_file_path = save_files(prompt, midi_file_path, audio_file_path)
        print("Generated ABC Code: ", abc_code)
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
        Fill out the following parameters to generate a melody.
        If any field is left empty, a suprise will be generated!
        """
    )
    with gr.Column():
        with gr.Row():
            key_input = gr.Textbox(label="Key (e.g., C major, A minor)", placeholder="e.g., C major")
            tempo_input = gr.Textbox(label="Tempo (BPM)", placeholder="e.g., 120")
            time_signature_input = gr.Textbox(label="Time Signature (e.g., 4/4)", placeholder="e.g., 4/4")
        with gr.Row():
            melody_style_input = gr.Textbox(label="Melody Style (e.g., pop, jazz)", placeholder="e.g., pop")
            range_input = gr.Textbox(label="Range (e.g., narrow, wide)", placeholder="e.g., narrow")
        with gr.Row():
            rhythm_input = gr.Textbox(label="Rhythm (e.g., simple, syncopated)", placeholder="e.g., simple")
            emotion_input = gr.Textbox(label="Emotion (e.g., happy, sad)", placeholder="e.g., happy")
            instrument_input = gr.Textbox(label="Instrument (e.g., piano, flute)", placeholder="e.g., piano")
        with gr.Row():
            bars_number_input = gr.Number(label="Number of bars", precision=0)
        prompt_input = gr.Textbox(
            label="Additional description for your prompt", placeholder="Any other information you would like to add",
            lines=3
        )

        with gr.Row():
            midi_output = gr.File(label="Generated MIDI File")
            audio_output = gr.Audio(label="Generated Audio", autoplay=False)
        generate_button = gr.Button("Generate Music")

    generate_button.click(
        generate_midi_and_play,
        inputs=[key_input, tempo_input, time_signature_input, melody_style_input, range_input, rhythm_input,
                emotion_input, instrument_input, prompt_input, bars_number_input],
        outputs=[midi_output, audio_output]
    )

iface.launch()