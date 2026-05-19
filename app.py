"""
ImageFetcher Microservice - CS 361
Authors: Declan, Mirna

Listens on http://localhost:5100/fetch
See README.md for usage details.

Usage:
    pip install flask requests Pillow waitress
    python app.py
"""

import io
import time
import hashlib
import logging

import requests
from flask import Flask, request, Response, jsonify
from PIL import Image
from waitress import serve

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

# --- In-memory cache ---------------------------------------------------------
# Each entry: { "data": bytes, "content_type": str }
_cache = {}

MAX_DIMENSION = 4096
REQUEST_TIMEOUT = 10


def _cache_key(image_url, width, height, fit):
    raw = f"{image_url}|{width}|{height}|{fit}"
    return hashlib.sha256(raw.encode()).hexdigest()


# --- Route -------------------------------------------------------------------

@app.route("/fetch", methods=["GET"])
def fetch():
    # 1. Parse and validate parameters
    image_url = request.args.get("image_url", "").strip()
    if not image_url:
        return jsonify({"error": "image_url parameter is required"}), 400

    width = height = None
    fit = request.args.get("fit", "cover").strip().lower()
    bypass_cache = request.args.get("bypass_cache", "false").lower() == "true"

    if "width" in request.args:
        try:
            width = int(request.args["width"])
            if not (1 <= width <= MAX_DIMENSION):
                raise ValueError
        except (ValueError, TypeError):
            return jsonify({
                "error": f"width must be an integer between 1 and {MAX_DIMENSION}"
            }), 400

    if "height" in request.args:
        try:
            height = int(request.args["height"])
            if not (1 <= height <= MAX_DIMENSION):
                raise ValueError
        except (ValueError, TypeError):
            return jsonify({
                "error": f"height must be an integer between 1 and {MAX_DIMENSION}"
            }), 400

    valid_fits = {"cover", "contain", "fill", "inside", "outside"}
    if fit not in valid_fits:
        return jsonify({
            "error": f"fit must be one of: {', '.join(sorted(valid_fits))}"
        }), 400

    # 2. Cache lookup
    key = _cache_key(image_url, width, height, fit)
    if not bypass_cache and key in _cache:
        entry = _cache[key]
        log.info("CACHE HIT  %s", image_url)
        return Response(entry["data"], status=200,
                        mimetype=entry["content_type"],
                        headers={"X-Cache": "HIT"})

    # 3. Fetch from origin
    try:
        resp = requests.get(image_url, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.ConnectionError:
        return jsonify({"error": f"Could not connect to: {image_url}"}), 502
    except requests.exceptions.Timeout:
        return jsonify({"error": f"Request timed out after {REQUEST_TIMEOUT}s"}), 502
    except requests.exceptions.RequestException as exc:
        return jsonify({"error": f"Upstream request failed: {exc}"}), 502

    if resp.status_code != 200:
        return jsonify({
            "error": f"{resp.status_code} was returned for the provided URL"
        }), 502

    raw_bytes = resp.content
    content_type = resp.headers.get("Content-Type", "application/octet-stream").split(";")[0]

    # 4. Resize if requested
    if width or height:
        try:
            img = Image.open(io.BytesIO(raw_bytes))
            orig_w, orig_h = img.size
            target_w = width or orig_w
            target_h = height or orig_h

            if fit == "fill":
                resized = img.resize((target_w, target_h), Image.LANCZOS)
            elif fit == "contain":
                img.thumbnail((target_w, target_h), Image.LANCZOS)
                canvas = Image.new("RGBA" if img.mode == "RGBA" else "RGB",
                                   (target_w, target_h), (255, 255, 255))
                offset = ((target_w - img.width) // 2, (target_h - img.height) // 2)
                canvas.paste(img, offset)
                resized = canvas
            elif fit == "inside":
                img.thumbnail((target_w, target_h), Image.LANCZOS)
                resized = img
            elif fit == "outside":
                ratio = max(target_w / orig_w, target_h / orig_h)
                resized = img.resize((int(orig_w * ratio), int(orig_h * ratio)), Image.LANCZOS)
            else:  # cover (default)
                ratio = max(target_w / orig_w, target_h / orig_h)
                new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
                resized = img.resize((new_w, new_h), Image.LANCZOS)
                left = (new_w - target_w) // 2
                top = (new_h - target_h) // 2
                resized = resized.crop((left, top, left + target_w, top + target_h))

            fmt = _pil_format(content_type)
            buf = io.BytesIO()
            if fmt == "JPEG" and resized.mode in ("RGBA", "P"):
                resized = resized.convert("RGB")
            resized.save(buf, format=fmt)
            raw_bytes = buf.getvalue()

        except Exception as exc:
            log.warning("Resize failed: %s", exc)
            return jsonify({"error": f"Could not process image: {exc}"}), 502

    # 5. Store in cache and return
    _cache[key] = {"data": raw_bytes, "content_type": content_type}
    log.info("CACHE MISS  %s  (stored)", image_url)
    return Response(raw_bytes, status=200, mimetype=content_type,
                    headers={"X-Cache": "MISS"})


def _pil_format(content_type):
    return {
        "image/jpeg": "JPEG", "image/jpg": "JPEG",
        "image/png":  "PNG",  "image/gif": "GIF",
        "image/webp": "WEBP", "image/bmp": "BMP",
        "image/tiff": "TIFF",
    }.get(content_type.lower(), "PNG")


# --- Entrypoint --------------------------------------------------------------

if __name__ == "__main__":
    print("ImageFetcher starting on http://localhost:5100")
    serve(app, host="0.0.0.0", port=5100)
