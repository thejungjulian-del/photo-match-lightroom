"""
app.py
------
This is the heart of the app. It runs a tiny website with two features:

  STEP 1 (/analyze): upload a reference photo -> get detailed shooting instructions.
  STEP 2 (/match):   upload reference + your photo -> get a Lightroom .xmp preset.

NEW: it can run two different AI "brains" and show them SIDE BY SIDE so you can compare:
  - "claude"  = the paid Claude API (high quality, ~1 cent per photo)
  - "ollama"  = a FREE model running on your own Mac (no key, no cost, more private)

You pick which one(s) to run with the checkboxes at the top of the page.

Start it with:   python3 app.py
Then open:        http://127.0.0.1:5000
"""

import base64
import io
import json
import os

from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from PIL import Image, ImageDraw
import anthropic
import ollama                            # talks to the free local model
from openai import OpenAI                # talks to GPT

from preset import build_xmp


load_dotenv()
app = Flask(__name__)

# --- The two brains ---------------------------------------------------------
# Claude (paid). The client is created lazily so the app still runs with no key
# if you only want to use the free Ollama brain.
CLAUDE_MODEL = "claude-sonnet-4-6"
_claude_client = None

def get_claude():
    global _claude_client
    if _claude_client is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "No Claude API key found. Add it to your .env file, or just "
                "untick the Claude box and use the free Ollama brain."
            )
        _claude_client = anthropic.Anthropic(api_key=key)
    return _claude_client

# Ollama (free, local). Which local model to use — change it in .env if you like.
# Good vision models: "llama3.2-vision" (better) or "llava" (smaller/lighter).
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2-vision")

# GPT (paid). Created lazily, same as Claude, so the app runs without an OpenAI key.
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")              # for analyze/match
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")  # for AI photo edit
_openai_client = None

def get_openai():
    global _openai_client
    if _openai_client is None:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "No OpenAI API key found. Add OPENAI_API_KEY to your .env file, or "
                "untick the GPT box."
            )
        _openai_client = OpenAI(api_key=key)
    return _openai_client


# ---------------------------------------------------------------------------
# The instructions we give the AI. Both brains get the EXACT same prompt, so the
# comparison is fair.
# ---------------------------------------------------------------------------
ANALYZE_PROMPT = (
    "You are an expert photographer and photo coach. Look at this reference photo "
    "and write me clear, detailed, beginner-friendly instructions for how to TAKE a "
    "photo that looks like it. Use short scannable sections with these headers:\n"
    "**Camera angle & height**, **Distance & framing**, **Lens / zoom feel**, "
    "**Lighting** (direction, quality, time of day), **Pose / subject**, "
    "**Background & setting**, **The overall mood**, and finally "
    "**Quick shot checklist** (3-6 bullet points).\n"
    "Be specific and practical. Assume I'm a beginner using a phone camera unless the "
    "photo clearly needs a real camera."
)

MATCH_PROMPT = (
    "You are a Lightroom color-grading expert. Figure out the Lightroom Classic Develop "
    "adjustments that would make MY photo's color, light, and mood match the REFERENCE. "
    "Compare them honestly: if my photo is already brighter, exposure should be negative, etc.\n\n"
    "Reply with ONLY a JSON object (no other text) in exactly this shape:\n"
    "{\n"
    '  "basic": {"exposure": 0.0, "contrast": 0, "highlights": 0, "shadows": 0, '
    '"whites": 0, "blacks": 0, "texture": 0, "clarity": 0, "dehaze": 0, '
    '"vibrance": 0, "saturation": 0},\n'
    '  "hsl": {"red":{"h":0,"s":0,"l":0}, "orange":{"h":0,"s":0,"l":0}, '
    '"yellow":{"h":0,"s":0,"l":0}, "green":{"h":0,"s":0,"l":0}, '
    '"aqua":{"h":0,"s":0,"l":0}, "blue":{"h":0,"s":0,"l":0}, '
    '"purple":{"h":0,"s":0,"l":0}, "magenta":{"h":0,"s":0,"l":0}},\n'
    '  "colorGrade": {"shadowHue":0,"shadowSat":0,"midtoneHue":0,"midtoneSat":0,'
    '"highlightHue":0,"highlightSat":0},\n'
    '  "vignette": 0,\n'
    '  "tweaks": "Plain-language notes on white balance (warmer/cooler) and any manual '
    'sliders to nudge by hand, since the preset cannot set white balance.",\n'
    '  "presetName": "a short descriptive name for this look"\n'
    "}\n\n"
    "Ranges: exposure -5.0 to +5.0; contrast/highlights/shadows/whites/blacks/texture/"
    "clarity/dehaze/vibrance/saturation -100 to +100; HSL h/s/l -100 to +100; colorGrade "
    "hue 0-360 and sat 0-100; vignette -100 to +100. Use 0 for anything that should not "
    "change. Be tasteful, not extreme."
)


# ---------------------------------------------------------------------------
# Image helper: open an uploaded photo, shrink it, and return base64 text.
# Both brains accept base64, so one function feeds both.
# ---------------------------------------------------------------------------
def load_image(file_storage):
    """Open an uploaded photo, make it RGB, and shrink it. Returns a PIL image."""
    img = Image.open(file_storage.stream)
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((1024, 1024))
    return img


def pil_to_b64(img):
    """Turn a PIL image into base64 JPEG text (what both AI brains accept)."""
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")


def combine_side_by_side(ref_img, mine_img):
    """
    Ollama's vision model only accepts ONE image per message. So for the "match"
    step we paste the two photos into a single image: reference on the LEFT,
    your photo on the RIGHT, with labels above each.
    """
    h = 768  # make both photos the same height so they line up
    def fit(im):
        return im.resize((max(1, int(im.width * h / im.height)), h))

    left, right = fit(ref_img), fit(mine_img)
    gap, label_h = 20, 44
    canvas = Image.new("RGB", (left.width + right.width + gap, h + label_h), (20, 20, 20))
    canvas.paste(left, (0, label_h))
    canvas.paste(right, (left.width + gap, label_h))

    draw = ImageDraw.Draw(canvas)
    draw.text((10, 14), "LEFT = REFERENCE (the look I want)", fill=(255, 255, 255))
    draw.text((left.width + gap + 10, 14), "RIGHT = MY PHOTO", fill=(255, 255, 255))
    return canvas


def claude_image_block(b64):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}


def extract_json(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("The AI did not return JSON. It said:\n" + text)
    return json.loads(text[start : end + 1])


# ---------------------------------------------------------------------------
# THE FOUR BRAIN FUNCTIONS — two tasks (analyze / match) x two brains.
# ---------------------------------------------------------------------------
def claude_analyze(ref_b64):
    msg = get_claude().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": [claude_image_block(ref_b64),
                                                {"type": "text", "text": ANALYZE_PROMPT}]}],
    )
    return msg.content[0].text


def ollama_analyze(ref_b64):
    resp = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": ANALYZE_PROMPT, "images": [ref_b64]}],
    )
    return resp["message"]["content"]


def claude_match(ref_b64, mine_b64):
    msg = get_claude().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": "REFERENCE photo:"}, claude_image_block(ref_b64),
            {"type": "text", "text": "MY photo:"}, claude_image_block(mine_b64),
            {"type": "text", "text": MATCH_PROMPT},
        ]}],
    )
    return extract_json(msg.content[0].text)


def gpt_analyze(ref_b64):
    resp = get_openai().chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": ANALYZE_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{ref_b64}"}},
        ]}],
    )
    return resp.choices[0].message.content


def gpt_match(ref_b64, mine_b64):
    resp = get_openai().chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=1500,
        response_format={"type": "json_object"},  # force clean JSON back
        messages=[{"role": "user", "content": [
            {"type": "text", "text": "The FIRST image is the REFERENCE look I want. "
                                     "The SECOND image is MY photo.\n\n" + MATCH_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{ref_b64}"}},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{mine_b64}"}},
        ]}],
    )
    return extract_json(resp.choices[0].message.content)


def gpt_edit(ref_img, mine_img):
    """
    OPTION B — the AI photo editor. GPT's image model actually re-draws MY photo so
    its look matches the REFERENCE. Returns base64 PNG text.
    """
    def to_png_file(img, name):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        buf.name = name  # the API needs a filename to know the format
        return buf

    prompt = (
        "Re-edit the FIRST image (my photo) so its lighting, color grade, white balance, "
        "and overall mood match the SECOND image (the reference look). Keep the subject, "
        "pose, framing and composition of the FIRST image exactly the same — only change "
        "the photographic style/look, not the content."
    )
    result = get_openai().images.edit(
        model=OPENAI_IMAGE_MODEL,
        image=[to_png_file(mine_img, "mine.png"), to_png_file(ref_img, "reference.png")],
        prompt=prompt,
        size="auto",
    )
    return result.data[0].b64_json


def ollama_match(combined_b64):
    # One stitched image (left = reference, right = mine) because this model
    # only supports a single image per message.
    resp = ollama.chat(
        model=OLLAMA_MODEL,
        format="json",  # ask the local model to stick to clean JSON
        messages=[{"role": "user",
                   "content": ("This single image shows TWO photos: the LEFT half is the "
                               "REFERENCE look I want, the RIGHT half is MY photo.\n\n" + MATCH_PROMPT),
                   "images": [combined_b64]}],
    )
    return extract_json(resp["message"]["content"])


# Turn a raw Ollama error into a friendly, beginner-readable message.
def friendly_ollama_error(err):
    text = str(err).lower()
    if "connection" in text or "refused" in text or "11434" in text:
        return ("Couldn't reach Ollama. Open the Ollama app (or run `ollama serve` in a "
                "terminal), then try again.")
    if "not found" in text or "pull" in text:
        return (f"The model '{OLLAMA_MODEL}' isn't downloaded yet. In a terminal run: "
                f"`ollama pull {OLLAMA_MODEL}`  (one-time download), then try again.")
    return "Ollama error: " + str(err)


def which_engines():
    """Read the checkboxes the page sent us; default to both."""
    raw = request.form.get("engines", "claude,gpt,ollama")
    chosen = [e.strip() for e in raw.split(",") if e.strip() in ("claude", "gpt", "ollama")]
    return chosen or ["claude"]


# ---------------------------------------------------------------------------
# Web routes
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    if "reference" not in request.files:
        return jsonify({"error": "Please upload a reference photo."}), 400

    ref_b64 = pil_to_b64(load_image(request.files["reference"]))
    results = {}

    for engine in which_engines():
        try:
            if engine == "claude":
                text = claude_analyze(ref_b64)
            elif engine == "gpt":
                text = gpt_analyze(ref_b64)
            else:
                text = ollama_analyze(ref_b64)
            results[engine] = {"instructions": text}
        except Exception as e:
            msg = friendly_ollama_error(e) if engine == "ollama" else str(e)
            results[engine] = {"error": msg}

    return jsonify(results)


@app.route("/match", methods=["POST"])
def match():
    if "reference" not in request.files or "mine" not in request.files:
        return jsonify({"error": "Please upload BOTH the reference and your own photo."}), 400

    ref_img = load_image(request.files["reference"])
    mine_img = load_image(request.files["mine"])
    ref_b64 = pil_to_b64(ref_img)
    mine_b64 = pil_to_b64(mine_img)
    combined_b64 = pil_to_b64(combine_side_by_side(ref_img, mine_img))
    results = {}

    for engine in which_engines():
        try:
            if engine == "claude":
                values = claude_match(ref_b64, mine_b64)
            elif engine == "gpt":
                values = gpt_match(ref_b64, mine_b64)
            else:
                values = ollama_match(combined_b64)
            preset_name = values.get("presetName", "Photo Match")
            results[engine] = {
                "tweaks": values.get("tweaks", ""),
                "presetName": preset_name,
                "xmp": build_xmp(values, preset_name=preset_name),
            }
        except Exception as e:
            msg = friendly_ollama_error(e) if engine == "ollama" else str(e)
            results[engine] = {"error": msg}

    return jsonify(results)


@app.route("/edit", methods=["POST"])
def edit():
    """OPTION B — GPT actually re-edits your photo to match the reference look."""
    if "reference" not in request.files or "mine" not in request.files:
        return jsonify({"error": "Please upload BOTH the reference and your own photo."}), 400

    ref_img = load_image(request.files["reference"])
    mine_img = load_image(request.files["mine"])
    try:
        b64png = gpt_edit(ref_img, mine_img)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Hand the image back as a data URL so the page can show + download it directly.
    return jsonify({"image": "data:image/png;base64," + b64png})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
