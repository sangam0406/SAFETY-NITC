import os
from flask import Flask, render_template, request, jsonify, session
import openai
import re
from translate import Translator
from pydub import AudioSegment
import speech_recognition as sr
import logging

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key')
openai.api_key = "sk-proj-BU33AuO1Kl6BPni5Mw9zT3BlbkFJLoI4e0wnuKUCCzFUjAyx"

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def extract_locations(user_input):
    logging.debug(f"Extracting locations from user input: {user_input}")
    
    patterns = {
        "source_destination": re.compile(r"\bfrom\s+([\w\s,]+)\s+to\s+([\w\s,]+)\b", re.IGNORECASE),
        "travel_to": re.compile(r"\b(?:travel|go|take me)\s+to\s+([\w\s,]+)\b", re.IGNORECASE),
        "travel_to_inappropriate": re.compile(r"\bmake love in\s+([\w\s,]+)\b", re.IGNORECASE),
        "die_in": re.compile(r"\bdie in\s+([\w\s,]+)\b", re.IGNORECASE),
        "hate": re.compile(r"\bhate\s+([\w\s,]+)\b", re.IGNORECASE),
        "single": re.compile(r"^\s*([\w\s,]+)\s*$", re.IGNORECASE),
        "yes": re.compile(r"\b(yes)\b", re.IGNORECASE)
    }

    if match := patterns["source_destination"].search(user_input):
        return "source_destination", (match.group(1).strip(), match.group(2).strip())
    elif match := patterns["travel_to"].search(user_input):
        return "travel_to", match.group(1).strip()
    elif match := patterns["travel_to_inappropriate"].search(user_input):
        return "travel_to_inappropriate", match.group(1).strip()
    elif match := patterns["die_in"].search(user_input):
        return "die_in", match.group(1).strip()
    elif match := patterns["hate"].search(user_input):
        return "hate", match.group(1).strip()
    elif patterns["yes"].search(user_input):
        return "yes", None
    elif match := patterns["single"].match(user_input):
        return "", match.group(1).strip()

    return None, None

def generate_route_description(start_location, end_location):
    prompt = f"Provide a detailed driving route from {start_location} to {end_location}. Include major turns, landmarks, and distances."
    logging.debug(f"Generating route description with prompt: {prompt}")

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )

    route_description = response.choices[0].message['content'].strip()
    logging.debug(f"Generated route description: {route_description}")
    return route_description

def translate_description(route_description, target_language):
    if target_language == 'en':
        return route_description

    translator = Translator(to_lang=target_language)
    sentences = route_description.split('. ')
    translated_sentences = []

    for sentence in sentences:
        translated_chunk = translator.translate(sentence)
        translated_sentences.append(translated_chunk)

    translated_description = '. '.join(translated_sentences)
    return translated_description

def transcribe_audio(audio_path):
    recognizer = sr.Recognizer()
    audio = AudioSegment.from_file(audio_path)
    audio.export("temp.wav", format="wav")
    with sr.AudioFile("temp.wav") as source:
        audio_data = recognizer.record(source)
        text = recognizer.recognize_google(audio_data)
    return text

def split_chunks(text, max_length=500):
    chunks = []
    current_chunk = ""
    
    sentences = text.split('. ')
    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_length:
            current_chunk += sentence + '. '
        else:
            chunks.append(current_chunk.strip())
            current_chunk = sentence + '. '
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/get_response", methods=["POST"])
def get_response():
    input_type = request.form.get("input_type")
    user_input = request.form.get("user_input")
    target_language = request.form.get("target_language")

    session_data = session.get('data', {'source': '', 'destination': ''})
    location_type, location_value = extract_locations(user_input)

    if input_type == 'text':
        if location_type == "source_destination":
            source, destination = location_value
            session['data'] = {'source': source, 'destination': destination}
            route_description = generate_route_description(source, destination)
            translated_description = translate_description(route_description, target_language)
            return jsonify({
                "source": source,
                "destination": destination,
                "message": f"Sure, Here is the path from {source} to {destination}!",
                "route": translated_description
            })
        elif location_type == "travel_to":
            source = "current_location"  # Assuming current location
            destination = location_value
            route_description = generate_route_description(source, destination)
            translated_description = translate_description(route_description, target_language)
            return jsonify({
                "source": source,
                "destination": destination,
                "message": f"Sure, Here is the path from {source} to {destination}!",
                "route": translated_description
            })
        elif location_type == "travel_to_inappropriate":
            session['data'] = {'source': '', 'destination': location_value}
            return jsonify({
                "source": "",
                "destination": location_value,
                "message": f"hahaha! what about travelling to {location_value}?"
            })
        elif location_type == "die_in":
            return jsonify({
                "message": "This is against our guidelines, please seek appropriate help.",
                "source": "",
                "destination": ""
            })
        elif location_type == "hate":
            return jsonify({
                "message": "Sorry, would you like to elaborate or contact our customer care?",
                "source": "",
                "destination": ""
            })
        elif location_type == "yes":
            session_data = session.get('data', {'source': '', 'destination': ''})
            if session_data['destination']:
                source = "current_location"  # Assuming current location
                destination = session_data['destination']
                return jsonify({
                    "source": source,
                    "destination": destination,
                    "message": "Great!"
                })
            else:
                return jsonify({
                    "message": "Please provide more details.",
                    "source": "",
                    "destination": ""
                })
        elif not location_type and location_value:
            return jsonify({
                "message": f"{location_value} is a great place! Would you like to go there?",
                "source": "",
                "destination": ""
            })
        else:
            return jsonify({"error": "Invalid input format."})

    elif input_type == 'audio':
        audio_data = request.files["audio_data"]
        audio_path = "temp_audio.wav"
        audio_data.save(audio_path)

        try:
            user_input = transcribe_audio(audio_path)
            location_type, location_value = extract_locations(user_input)
            session_data = session.get('data', {'source': '', 'destination': ''})

            if location_type == "source_destination":
                source, destination = location_value
                session['data'] = {'source': source, 'destination': destination}
                route_description = generate_route_description(source, destination)
                translated_description = translate_description(route_description, target_language)
                return jsonify({
                    "source": source,
                    "destination": destination,
                    "message": f"Sure, Here is the path from {source} to {destination}!",
                    "route": translated_description
                })
            elif location_type == "travel_to":
                source = "current_location"  # Assuming current location
                destination = location_value
                route_description = generate_route_description(source, destination)
                translated_description = translate_description(route_description, target_language)
                return jsonify({
                    "source": source,
                    "destination": destination,
                    "message": f"Sure, Here is the path from {source} to {destination}!",
                    "route": translated_description
                })
            elif location_type == "travel_to_inappropriate":
                session['data'] = {'source': '', 'destination': location_value}
                return jsonify({
                    "source": "",
                    "destination": location_value,
                    "message": f"hahaha! what about travelling to {location_value}?"
                })
            elif location_type == "die_in":
                return jsonify({
                    "message": "This is against our guidelines, please seek appropriate help.",
                    "source": "",
                    "destination": ""
                })
            elif location_type == "hate":
                return jsonify({
                    "message": "Sorry, would you like to elaborate or contact our customer care?",
                    "source": "",
                    "destination": ""
                })
            elif location_type == "yes":
                session_data = session.get('data', {'source': '', 'destination': ''})
                if session_data['destination']:
                    source = "current_location"  # Assuming current location
                    destination = session_data['destination']
                    return jsonify({
                        "source": source,
                        "destination": destination,
                        "message": "Great!"
                    })
                else:
                    return jsonify({
                        "message": "Please provide more details.",
                        "source": "",
                        "destination": ""
                    })
            elif not location_type and location_value:
                return jsonify({
                    "message": f"{location_value} is a great place! Would you like to go there?",
                    "source": "",
                    "destination": ""
                })
            else:
                return jsonify({"error": "Invalid input format from audio transcription."})

        except Exception as e:
            return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(debug=True)
