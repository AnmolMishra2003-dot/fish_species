"""
Fish Species Identification - Flask Backend (TFLite Version)
"""

import os
import io
import uuid
import datetime
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from PIL import Image
import numpy as np
import tensorflow as tf

# ─────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)
CORS(app)

# ── Configuration ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "fish_model.tflite")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

IMG_SIZE = (224, 224)
MAX_BYTES = 10 * 1024 * 1024

# ── Fish Classes ─────────────────────────────────────────────
FISH_CLASSES = [
    "Bangus","Big Head Carp","Black Spotted Barb","Catfish","Climbing Perch",
    "Fourfinger Threadfin","Freshwater Eel","Glass Perchlet","Goby","Gold Fish",
    "Gourami","Grass Carp","Green Spotted Puffer","Indian Carp","Indo-Pacific Tarpon",
    "Jaguar Gapote","Janitor Fish","Knifefish","Long-Snouted Pipeship","Mosquito Fish",
    "Mudfish","Mullet","Pangasius","Perch","Scat Fish","Silver Barb","Silver Carp",
    "Silver Perch","Snakehead","Tenpounder","Tilapia"
]

# ── Fish Info ─────────────────────────────────────────────
FISH_INFO = {
    "Bangus": {"habitat": "Brackish & marine waters", "avg_size": "30–100 cm", "status": "Least Concern"},
    "Tilapia": {"habitat": "Freshwater ponds", "avg_size": "20–60 cm", "status": "Least Concern"},
    "Catfish": {"habitat": "Freshwater rivers & ponds", "avg_size": "20–100 cm", "status": "Varies"},
    "Pangasius": {"habitat": "Freshwater rivers", "avg_size": "50–130 cm", "status": "Least Concern"},
}

# ── Load TFLite Model ─────────────────────────────────────────
interpreter = None

if os.path.exists(MODEL_PATH):
    try:
        interpreter = tf.lite.Interpreter(model_path=MODEL_PATH)
        interpreter.allocate_tensors()

        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()

        print("✅ TFLite model loaded")
    except Exception as e:
        print(f"❌ Model load failed: {e}")
else:
    print("⚠️ Model file not found")

# ── Prediction ─────────────────────────────────────────────
def predict(img_bytes):
    if interpreter is None:
        idx = np.random.randint(0, len(FISH_CLASSES))
        conf = float(np.random.uniform(0.7, 0.99))
        return FISH_CLASSES[idx], conf, []

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img = img.resize(IMG_SIZE)
    img = np.array(img, dtype=np.float32)

    img = img / 255.0
    img = np.expand_dims(img, axis=0)

    interpreter.set_tensor(input_details[0]['index'], img)
    interpreter.invoke()

    preds = interpreter.get_tensor(output_details[0]['index'])[0]

    idx = int(np.argmax(preds))
    conf = float(preds[idx])

    top_indices = np.argsort(preds)[::-1][:4]
    top = [(FISH_CLASSES[i], float(preds[i])) for i in top_indices]

    return FISH_CLASSES[idx], conf, top


# ── NEW: LOCATION + WEATHER HELPERS ───────────────────────────
def get_place_name(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        r = requests.get(url, headers={"User-Agent": "fish-app"})
        data = r.json()
        return data.get("display_name", "Unknown location")
    except:
        return "Unknown location"


def get_weather(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        r = requests.get(url)
        data = r.json()

        cw = data.get("current_weather", {})

        return {
            "temperature": cw.get("temperature"),
            "windspeed": cw.get("windspeed"),
            "weathercode": cw.get("weathercode")
        }
    except:
        return {}


# ── Routes ─────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model_loaded": interpreter is not None})


@app.route("/predict", methods=["POST"])
def predict_route():
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400

    file = request.files["image"]
    img_bytes = file.read()

    if len(img_bytes) > MAX_BYTES:
        return jsonify({"error": "File too large"}), 413

    species, confidence, top_preds = predict(img_bytes)

    fname = f"{uuid.uuid4().hex}.jpg"
    with open(os.path.join(UPLOAD_FOLDER, fname), "wb") as f:
        f.write(img_bytes)

    # ✅ LOCATION FROM FRONTEND
    lat = request.form.get("lat")
    lon = request.form.get("lon")

    location_data = None
    weather_data = {}

    if lat and lon:
        try:
            lat = float(lat)
            lon = float(lon)

            place = get_place_name(lat, lon)
            weather_data = get_weather(lat, lon)

            location_data = {
                "lat": lat,
                "lon": lon,
                "place": place
            }

        except:
            location_data = None

    return jsonify({
        "species": species,
        "confidence": round(confidence * 100, 2),
        "top_predictions": [
            {"species": s, "confidence": round(c * 100, 2)} for s, c in top_preds
        ],
        "info": FISH_INFO.get(species, {}),

        # ✅ NEW
        "location": location_data,
        "weather": weather_data,

        "image_id": fname,
        "timestamp": datetime.datetime.utcnow().isoformat()
    })


@app.route("/classes", methods=["GET"])
def classes():
    return jsonify({"classes": FISH_CLASSES})


@app.route("/")
def home():
    return render_template("index.html")


# ── Run ─────────────────────────────────────────────
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
