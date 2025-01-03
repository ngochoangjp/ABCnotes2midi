import gradio as gr
import mido
from mido import MidiFile, MidiTrack, Message
from music21 import converter, instrument, note, chord, stream, duration, environment, roman
import pretty_midi
from midi2audio import FluidSynth
import tempfile
import os
import io

# Set the music21 environment to find MuseScore (if available)
# us = environment.UserSettings()
# us['musescoreDirectPNGPath'] = '/path/to/musescore'  # Replace with your MuseScore path if needed
# us['musicxmlPath'] = '/path/to/musescore'  # Replace with your MuseScore path if needed

# --- Functions from Code 1 (MIDI to ABC Notes and related) ---

def midi_to_abc_notes(midi_file):
    """Converts a MIDI file to a list of notes in the specified format."""
    midi_data = pretty_midi.PrettyMIDI(midi_file.name)
    notes_data = []
    instrument_midi = midi_data.instruments[0]

    # Metadata
    title = "Untitled Score"  # You can try to extract from MIDI metadata if available
    time_signature = midi_data.time_signature_changes[0] if midi_data.time_signature_changes else pretty_midi.TimeSignature(4, 4, 0)
    bpm = midi_data.get_tempo_changes()[1][0] if midi_data.get_tempo_changes() else 120.0 # if no tempo changes, default to 120 bpm
    
    # Analyze key signature (using music21 for more robust key analysis)
    try:
        s = converter.parse(midi_file.name)
        key = s.analyze('key')
        key_quality = key.mode
        key_signature = key.sharps
    except:
        key_quality = "Major"  # Default
        key_signature = 0      # Default

    # Get longest and shortest durations
    all_durations = [note.end - note.start for note in instrument_midi.notes]
    longest_duration = max(all_durations) if all_durations else 0.0
    shortest_duration = min(all_durations) if all_durations else 0.0

    notes_data.append(f"#Title:\n{title}")
    notes_data.append(f"#Time Signature:\n{time_signature.numerator}/{time_signature.denominator}")
    notes_data.append(f"#Beats per Minute:\n{bpm}")
    notes_data.append(f"#Key Quality:\n{key_quality}")
    notes_data.append(f"#Key Signature:\n{key_signature}")
    notes_data.append(f"#Longest Rhythm Value:\n{longest_duration}")
    notes_data.append(f"#Shortest Rhythm Value:\n{shortest_duration}")
    notes_data.append("#Start Time - Pitch - Duration - Dynamic - Pitch Name")
    notes_data.append("#Part:\nUntitled Part")
    notes_data.append(f"#Instrument:\n{instrument_midi.program}")
    notes_data.append("#New Phrase:")  # Initial "New Phrase"

    current_phrase_start = 0
    is_drum = instrument_midi.is_drum

    for note in instrument_midi.notes:
        start_time = note.start
        pitch = note.pitch if not is_drum else -2147483648
        duration = note.end - note.start
        dynamic = note.velocity
        
        if is_drum:
            pitch_name = "Drum"
        else:
            pitch_name = pretty_midi.note_number_to_name(note.pitch)

        # Add "New Phrase:" if start time is significantly different
        if start_time - current_phrase_start > 4:  # Adjust threshold as needed
            notes_data.append("#New Phrase:")
            current_phrase_start = start_time
        
        # Format the note data with 3 decimal places for duration
        note_line = f"{start_time:.2f} {pitch} {duration:.3f} {dynamic} {pitch_name}"
        notes_data.append(note_line)

    return "\n".join(notes_data)

def abc_notes_to_midi(abc_notes_string):
    """Converts ABC notes to a MIDI file."""
    print("Received ABC notes string:", abc_notes_string)  # Debug print
    
    # Parse metadata and notes
    lines = [line.strip() for line in abc_notes_string.strip().split("\n") if line.strip()]
    notes = []

    # Parse each line that looks like note data (starts with a number)
    for line in lines:
        if line.startswith("#"):
            continue
        try:
            parts = line.strip().split()
            if len(parts) >= 5 and parts[0][0].isdigit():  # Check if line starts with a number
                start_time = float(parts[0])
                pitch = int(parts[1])
                duration = float(parts[2])
                velocity = int(parts[3])
                notes.append((start_time, pitch, duration, velocity))
                print(f"Added note: start={start_time}, pitch={pitch}, duration={duration}, velocity={velocity}")
        except (ValueError, IndexError) as e:
            print(f"Skipping invalid line: {line}, error: {e}")
            continue

    if not notes:
        print("No valid notes found in input")
        return None

    # Create a PrettyMIDI object with default tempo
    pm = pretty_midi.PrettyMIDI(initial_tempo=120.0)

    # Set time signature to 4/4
    pm.time_signature_changes = [pretty_midi.TimeSignature(4, 4, 0)]

    # Create a piano instrument
    instrument = pretty_midi.Instrument(program=0)  # program 0 is acoustic grand piano

    # Find the earliest start time to normalize times
    min_start_time = min(note[0] for note in notes)
    print(f"Normalizing times by subtracting {min_start_time}")

    # Add notes to the instrument
    notes_added = 0
    for start_time, pitch, duration, velocity in notes:
        # Skip drum notes
        if pitch == -2147483648:
            print(f"Skipping drum note: pitch={pitch}")
            continue
            
        # Normalize start time
        normalized_start = start_time - min_start_time
        
        note = pretty_midi.Note(
            velocity=velocity,
            pitch=pitch,
            start=normalized_start,
            end=normalized_start + duration
        )
        instrument.notes.append(note)
        notes_added += 1
        print(f"Added normalized note: pitch={pitch}, start={normalized_start}, duration={duration}, velocity={velocity}")

    print(f"Total notes added to MIDI: {notes_added}")

    # Add the instrument to the PrettyMIDI object
    pm.instruments.append(instrument)

    # Save to a temporary file
    temp_file = tempfile.NamedTemporaryFile(suffix='.mid', delete=False)
    pm.write(temp_file.name)
    temp_file.close()
    print(f"Saved MIDI file to: {temp_file.name}")
    return temp_file.name

# --- Functions from Code 2 (ABC to MIDI and related) ---

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

def convert_abc_and_play(abc_code):
    """Converts ABC to MIDI, plays it, and returns both MIDI and audio file paths."""
    midi_file_path = abc_to_midi(abc_code)
    if midi_file_path:
        audio_file_path = play_midi(midi_file_path)
        return midi_file_path, audio_file_path
    else:
        return None, None

def pitch_to_abc(pitch_name):
    """Convert music21 pitch name to ABC notation."""
    # Extract note name and octave
    base_note = pitch_name[0].upper()  # Keep uppercase for ABC notation
    octave = int(pitch_name[-1])
    
    # Handle accidentals - ABC uses ^ for sharp and _ for flat
    if '#' in pitch_name:
        base_note = f"^{base_note}"
    elif '-' in pitch_name or 'b' in pitch_name:
        base_note = f"_{base_note}"
    
    # Handle octaves relative to middle C (C4)
    # In ABC: C is in octave 4, c is in octave 5, C, is in octave 3
    if octave == 4:
        return base_note
    elif octave == 5:
        return base_note.lower()
    elif octave > 5:
        return base_note.lower() + "'" * (octave - 5)
    elif octave == 3:
        return base_note + ","
    else:
        return base_note + "," * (4 - octave)

def duration_to_abc(dur):
    """Convert music21 duration to ABC notation."""
    qlen = dur.quarterLength
    if qlen.is_integer():
        return str(int(qlen)) if qlen != 1 else ""
    # Handle dotted notes
    if qlen * 2 % 1 == 0:
        return f"{int(qlen * 2)}/2"
    if qlen * 4 % 1 == 0:
        return f"{int(qlen * 4)}/4"
    # For more complex durations
    return f"{int(qlen * 8)}/8"

def midi_note_to_abc(midi_number):
    """Convert MIDI note number to ABC notation."""
    # MIDI note 60 is middle C (C4)
    notes = ['C', '^C', 'D', '^D', 'E', 'F', '^F', 'G', '^G', 'A', '^A', 'B']
    octave = (midi_number // 12) - 1
    note_index = midi_number % 12
    note_name = notes[note_index]
    
    # Handle octaves relative to middle C (C4 = MIDI 60)
    if octave == 4:  # Middle octave
        return note_name
    elif octave == 5:  # One octave up
        return note_name.lower()
    elif octave > 5:  # More than one octave up
        return note_name.lower() + "'" * (octave - 5)
    elif octave == 3:  # One octave down
        return note_name + ","
    else:  # More than one octave down
        return note_name + "," * (4 - octave)

def midi_to_abc(midi_file):
    """Converts a MIDI file to ABC notation and returns the ABC code."""
    try:
        # Parse MIDI file using mido for direct MIDI access
        mid = MidiFile(midi_file)
        ticks_per_beat = mid.ticks_per_beat
        
        # Initialize variables
        tempo = 120  # default tempo in BPM
        microseconds_per_beat = 500000  # default tempo (120 BPM)
        current_time = 0
        notes = []
        time_sig_num = 4
        time_sig_den = 4
        
        # First pass: collect tempo and time signature
        for track in mid.tracks:
            for msg in track:
                if msg.type == 'set_tempo':
                    microseconds_per_beat = msg.tempo
                    tempo = int(60000000 / microseconds_per_beat)
                    print(f"Tempo set to {tempo} BPM (microseconds per beat: {microseconds_per_beat})")
                elif msg.type == 'time_signature':
                    time_sig_num = msg.numerator
                    time_sig_den = msg.denominator
                    print(f"Time signature set to {time_sig_num}/{time_sig_den}")
        
        # Calculate ticks per quarter note for duration conversion
        ticks_per_quarter = ticks_per_beat
        seconds_per_tick = microseconds_per_beat / (ticks_per_beat * 1000000)
        print(f"Ticks per quarter note: {ticks_per_quarter}, Seconds per tick: {seconds_per_tick}")
        
        # Second pass: collect notes with proper timing
        active_notes = {}
        for track in mid.tracks:
            current_ticks = 0
            for msg in track:
                current_ticks += msg.time
                if msg.type == 'note_on' and msg.velocity > 0:
                    # Store start time of note
                    active_notes[msg.note] = current_ticks
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    if msg.note in active_notes:
                        start_ticks = active_notes[msg.note]
                        duration_ticks = current_ticks - start_ticks
                        # Convert ticks to quarter note duration
                        duration = duration_ticks / ticks_per_quarter
                        notes.append(('note', msg.note, duration))
                        del active_notes[msg.note]
                        print(f"Note {msg.note}: duration {duration} quarters ({duration_ticks} ticks)")
        
        # Create ABC header
        abc_code = [
            "X:1",
            "T:Converted from MIDI",
            f"Q:1/4={tempo}",  # Set tempo in quarter notes per minute
            f"M:{time_sig_num}/{time_sig_den}",
            "L:1/4",  # Set default note length to quarter note
            "K:C",  # Use C major as default
            ""
        ]
        
        # Convert notes to ABC notation with proper durations
        current_measure_duration = 0
        beats_per_measure = float(time_sig_num)
        
        for note_type, midi_num, duration in notes:
            # Convert MIDI note to ABC notation
            abc_note = midi_note_to_abc(midi_num)
            
            # Add duration marking
            if duration != 1.0:  # Only add duration if not a quarter note
                if duration.is_integer():
                    abc_note += str(int(duration))
                else:
                    # Handle common fraction cases
                    if abs(duration - 0.5) < 0.01:  # eighth note
                        abc_note += "/2"
                    elif abs(duration - 0.25) < 0.01:  # sixteenth note
                        abc_note += "/4"
                    elif abs(duration - 1.5) < 0.01:  # dotted quarter
                        abc_note += "3/2"
                    elif abs(duration - 0.75) < 0.01:  # dotted eighth
                        abc_note += "3/4"
                    else:
                        # For other durations, use the closest fraction
                        abc_note += f"{int(duration * 4)}/4"
            
            abc_code.append(abc_note)
            current_measure_duration += duration
            
            # Add bar lines at measure boundaries
            if current_measure_duration >= beats_per_measure:
                abc_code.append("|")
                current_measure_duration = 0
        
        # Add final bar line if needed
        if abc_code[-1] != "|":
            abc_code.append("|")
        
        return "\n".join(abc_code)
    except Exception as e:
        print(f"Error converting MIDI to ABC: {str(e)}")
        raise gr.Error(f"Error converting MIDI to ABC: {str(e)}")

# --- Common Functions (Chord to MIDI, analyze melody, etc.) ---

def play_midi(midi_file_path):
    """Plays the MIDI file using FluidSynth and returns the audio file path."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as temp_audio_file:
            audio_file_path = temp_audio_file.name
        fs = FluidSynth()
        fs.midi_to_audio(midi_file_path, audio_file_path)
        return audio_file_path
    except Exception as e:
        raise gr.Error(f"Error playing MIDI: {e}")

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

def analyze_melody_segment(notes, key):
    """Analyze a segment of melody notes to determine the best chord."""
    if not notes:
        return None
    
    # Get the scale degrees of the notes in the current key (skip rests)
    scale_degrees = []
    for n in notes:
        if isinstance(n, note.Note):  # Only process Notes, not Rests
            pitch_class = n.pitch.pitchClass
            scale_degree = (pitch_class - key.tonic.pitchClass) % 12
            scale_degrees.append(scale_degree)
    
    # If no valid notes found (only rests), return tonic chord
    if not scale_degrees:
        return 'I'
    
    # Common chord progressions in the key
    chord_options = {
        0: ['I', 'vi'],  # Tonic
        2: ['ii', 'V7'],  # Supertonic
        4: ['iii', 'I'],  # Mediant
        5: ['IV', 'ii'],  # Subdominant
        7: ['V', 'vii°'],  # Dominant
        9: ['vi', 'IV'],  # Submediant
        11: ['vii°', 'V']  # Leading tone
    }
    
    # Count occurrence of each scale degree
    degree_counts = {}
    for deg in scale_degrees:
        degree_counts[deg] = degree_counts.get(deg, 0) + 1
    
    # Find the most common scale degree
    if degree_counts:
        main_degree = max(degree_counts.items(), key=lambda x: x[1])[0]
        return chord_options.get(main_degree, ['I'])[0]
    
    return 'I'  # Default to tonic if no clear choice

def create_chord_from_roman(roman_numeral, key):
    """Create a chord from Roman numeral notation in the given key."""
    try:
        rn = roman.RomanNumeral(roman_numeral, key)
        return chord.Chord(rn.pitches)
    except Exception as e:
        print(f"Error creating chord: {e}")
        # Fallback to tonic chord if there's an error
        return chord.Chord(key.tonic.pitches)

def process_midi_with_chords(midi_file_path):
    """
    Process a MIDI file to detect scale and generate two versions with chords.
    Returns paths to two MIDI files: melody+chords and chords-only versions.
    """
    try:
        # Load and parse the MIDI file
        score = converter.parse(midi_file_path)
        
        # Extract the melody (assume it's in the first part)
        melody_part = score.parts[0]
        
        # Analyze the key
        key = score.analyze('key')
        print(f"Detected key: {key}")
        
        # Create new scores
        melody_with_chords = stream.Score()
        chords_only = stream.Score()
        
        # Create parts
        melody_part_new = stream.Part()
        chord_part = stream.Part()
        
        # Set instruments
        melody_part_new.insert(0, instrument.Piano())
        chord_part.insert(0, instrument.Piano())
        
        # Copy time signature from original part
        ts = melody_part.getTimeSignatures()[0]
        melody_part_new.insert(0, ts)
        chord_part.insert(0, ts)
        
        # Process each measure
        for measure in melody_part.getElementsByClass('Measure'):
            # Create new measures for both parts
            new_measure_melody = stream.Measure(number=measure.number)
            new_measure_chord = stream.Measure(number=measure.number)
            
            # Get notes and rests in this measure
            measure_elements = list(measure.getElementsByClass(['Note', 'Rest']))
            
            if measure_elements:
                # Analyze measure for chord (only using notes, not rests)
                roman_numeral = analyze_melody_segment(measure_elements, key)
                if roman_numeral:
                    print(f"Measure {measure.number}: Using chord {roman_numeral}")
                    
                    # Create chord for this measure
                    current_chord = create_chord_from_roman(roman_numeral, key)
                    current_chord.duration = duration.Duration(4.0)  # Full measure
                    
                    # Transpose chord down two octaves for better harmony
                    for p in current_chord.pitches:
                        p.octave -= 2
                    
                    # Add chord to chord measure
                    new_measure_chord.append(current_chord)
                else:
                    # If no chord determined, add a rest
                    new_measure_chord.append(note.Rest(duration=duration.Duration(4.0)))
            
            # Add all original elements to melody measure
            for elem in measure_elements:
                new_measure_melody.append(elem)
            
            # Add measures to parts
            melody_part_new.append(new_measure_melody)
            chord_part.append(new_measure_chord)
        
        # Create the combined version (melody + chords)
        melody_with_chords.append(melody_part_new)
        melody_with_chords.append(chord_part)
        
        # Create the chords-only version
        chords_only.append(chord_part)
        
        # Save both versions to temporary files
        with tempfile.NamedTemporaryFile(suffix="_with_chords.mid", delete=False) as temp_combined:
            combined_path = temp_combined.name
            melody_with_chords.write('midi', fp=combined_path)
            
        with tempfile.NamedTemporaryFile(suffix="_chords_only.mid", delete=False) as temp_chords:
            chords_path = temp_chords.name
            chords_only.write('midi', fp=chords_path)
            
        return combined_path, chords_path, str(key)
        
    except Exception as e:
        print(f"Error processing MIDI file: {e}")
        raise gr.Error(f"Error processing MIDI file: {e}")

def process_and_play_midi_with_chords(midi_file):
    """
    Process MIDI file and return both MIDI files and their audio versions
    """
    if midi_file is None:
        raise gr.Error("Please upload a MIDI file first")
        
    # Process the MIDI file
    combined_path, chords_path, key = process_midi_with_chords(midi_file.name)
    
    # Generate audio for both versions
    combined_audio = play_midi(combined_path)
    chords_audio = play_midi(chords_path)
    
    return combined_path, combined_audio, chords_path, chords_audio, key

# --- Gradio Interface ---

with gr.Blocks(title="MIDI and ABC Music Processing App") as iface:
    gr.Markdown(
        """
        # MIDI and ABC Music Processing App
        This app provides a suite of tools for working with MIDI and ABC music formats.
        """
    )

    with gr.Tab("MIDI to ABC Notes"):
        midi_input_notes = gr.File(label="Upload MIDI File", file_types=[".mid", ".midi"])
        midi_abc_notes_output = gr.Textbox(label="ABC Notes", lines=15)
        midi_notes_button = gr.Button("Convert to ABC Notes")

    with gr.Tab("ABC Notes to MIDI"):
        example_abc = """51.0 62 0.5 80 D4
51.5 60 0.5 80 C4
52.0 57 0.5 80 A3
52.5 57 0.5 80 A3
53.0 62 0.5 80 D4
53.5 60 0.5 80 C4
54.0 57 1.0 80 A3
55.0 58 0.5 80 A#3
55.5 60 0.5 80 C4
56.0 62 1.0 80 D4"""
        abc_notes_input = gr.Textbox(label="ABC Notes", value=example_abc, lines=15)
        with gr.Row():
            abc_notes_midi_output = gr.File(label="MIDI File")
            abc_notes_audio_output = gr.Audio(label="Audio Playback", autoplay=False)
        abc_notes_button = gr.Button("Convert and Play")

    with gr.Tab("ABC to MIDI"):
        abc_input = gr.Textbox(placeholder="Enter ABC notation here...", lines=7, label="ABC Notation")
        with gr.Row():
            abc_midi_output = gr.File(label="MIDI File")
            abc_audio_output = gr.Audio(label="Audio Playback", autoplay=False)
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

    with gr.Tab("MIDI with Chords"):
        with gr.Column():
            midi_with_chords_input = gr.File(label="Upload MIDI File", file_types=[".mid", ".midi"])
            midi_with_chords_key_output = gr.Textbox(label="Detected Key")
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Melody with Chords")
                    midi_with_chords_output = gr.File(label="Download MIDI")
                    midi_with_chords_audio = gr.Audio(label="Play")
                with gr.Column():
                    gr.Markdown("### Chords Only")
                    midi_with_chords_chords_only_output = gr.File(label="Download MIDI")
                    midi_with_chords_chords_audio = gr.Audio(label="Play")
            midi_with_chords_button = gr.Button("Process and Play")

    # Connect buttons to functions
    midi_notes_button.click(midi_to_abc_notes, inputs=midi_input_notes, outputs=midi_abc_notes_output)
    abc_notes_button.click(lambda abc_notes_string: (abc_notes_to_midi(abc_notes_string), play_midi(abc_notes_to_midi(abc_notes_string))), inputs=abc_notes_input, outputs=[abc_notes_midi_output, abc_notes_audio_output])
    abc_button.click(convert_abc_and_play, inputs=abc_input, outputs=[abc_midi_output, abc_audio_output])
    midi_button.click(midi_to_abc, inputs=midi_input, outputs=midi_abc_output)
    chord_button.click(lambda chord_name: (chord_to_midi(chord_name), play_midi(chord_to_midi(chord_name))), inputs=chord_input, outputs=[chord_midi_output, chord_audio_output])
    midi_with_chords_button.click(
        process_and_play_midi_with_chords,
        inputs=[midi_with_chords_input],
        outputs=[
            midi_with_chords_output,
            midi_with_chords_audio,
            midi_with_chords_chords_only_output,
            midi_with_chords_chords_audio,
            midi_with_chords_key_output
        ]
    )

iface.launch(server_name="127.0.0.1", server_port=7862)