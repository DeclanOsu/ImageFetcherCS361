"""
ImageFetcher Microservice Test Suite
Tests all three user stories: basic fetch, resize, and caching.

Usage:
    1. Start the microservice: python app.py
    2. Run this file: python test_image_fetcher.py

Requirements:
    pip install requests Pillow
"""

import base64
import json
import os
import sys
import tempfile
import time
import requests

BASE_URL = "http://localhost:5100/fetch"
TEST_IMAGE_URL = "https://img.pokemondb.net/sprites/ruby-sapphire/normal/torkoal.png"
CACHE_IMAGE_URL = "https://img.pokemondb.net/sprites/ruby-sapphire/shiny/torkoal.png"

NETWORK_TIMEOUT_MS = 5000
CACHE_TIMEOUT_MS = 100

SESSION = requests.Session()

# --- helpers -----------------------------------------------------------------

def section(title):
    print("\n" + "=" * 60)
    print("  " + title)
    print("=" * 60)

def ok(msg):
    print("  [PASS]  " + msg)

def fail(msg):
    print("  [FAIL]  " + msg)

def check(condition, msg_pass, msg_fail):
    if condition:
        ok(msg_pass)
    else:
        fail(msg_fail)
    return condition

def get_timed(params):
    t0 = time.time()
    r = SESSION.get(BASE_URL, params=params)
    return r, (time.time() - t0) * 1000

def print_response_info(r, elapsed_ms=None):
    print(f"     Status : {r.status_code}")
    if elapsed_ms is not None:
        print(f"     Latency: {elapsed_ms:.0f} ms")
    print(f"     Headers: X-Cache={r.headers.get('X-Cache', '(none)')}, "
          f"Content-Type={r.headers.get('Content-Type', '(none)')}")
    if r.status_code != 200:
        try:
            print(f"     Body   : {json.dumps(r.json())}")
        except Exception:
            print(f"     Body   : {r.text[:200]}")


# --- preview ----------------------------------------------------------------

def preview_image(url):
    """Fetch an image and open it in the default viewer."""
    print(f"\n  Fetching {url} for preview...")
    r, elapsed = get_timed({"image_url": url})
    if r.status_code != 200:
        print(f"  Could not fetch image: {r.status_code}")
        return
    content_type = r.headers.get("Content-Type", "image/png")
    ext = content_type.split("/")[-1].split(";")[0].strip()
    if ext == "jpeg":
        ext = "jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix="." + ext)
    tmp.write(r.content)
    tmp.close()
    print(f"  Saved to {tmp.name} - opening in default viewer...")
    os.startfile(tmp.name)


# --- save to preview folder ------------------------------------------------

PREVIEW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview")

def save_image(response, filename):
    """Save a successful image response to the preview folder."""
    if response.status_code != 200:
        return
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    content_type = response.headers.get("Content-Type", "image/png")
    ext = content_type.split("/")[-1].split(";")[0].strip()
    if ext == "jpeg":
        ext = "jpg"
    path = os.path.join(PREVIEW_DIR, filename + "." + ext)
    with open(path, "wb") as f:
        f.write(response.content)
    print(f"     Saved : {path}")


# --- Story 1: Basic fetch ----------------------------------------------------

def test_story1_basic_fetch():
    section("Story 1 - Basic image fetch")

    print("\n  [1a] Valid URL -> 200 + image bytes")
    r, elapsed = get_timed({"image_url": TEST_IMAGE_URL})
    print_response_info(r, elapsed)
    save_image(r, "1a_basic_fetch")
    check(r.status_code == 200, "Status 200", f"Expected 200, got {r.status_code}")
    check(len(r.content) > 0, "Response body is non-empty", "Response body is empty")
    check(elapsed < NETWORK_TIMEOUT_MS,
          f"Loaded in {elapsed:.0f} ms (under {NETWORK_TIMEOUT_MS} ms)",
          f"Too slow: {elapsed:.0f} ms")
    if r.status_code == 200:
        magic = r.content[:4]
        is_image = (magic[:3] == b'\xff\xd8\xff'
                    or magic[:4] == b'\x89PNG'
                    or magic[:4] == b'GIF8'
                    or magic[:4] == b'RIFF')
        check(is_image, "Content looks like a valid image binary",
              "Content does not look like an image")

    print("\n  [1b] Missing image_url -> 400")
    r, _ = get_timed({})
    print_response_info(r)
    check(r.status_code == 400, "Status 400 for missing image_url",
          f"Expected 400, got {r.status_code}")
    check("error" in r.json(), "JSON body contains error key",
          "No error key in response")

    print("\n  [1c] Unreachable URL -> 502")
    r, _ = get_timed({"image_url": "http://localhost:19999/img.png"})
    print_response_info(r)
    check(r.status_code == 502, "Status 502 for unreachable URL",
          f"Expected 502, got {r.status_code}")
    check("error" in r.json(), "JSON body contains error key",
          "No error key in response")


# --- Story 2: Resize on fetch ------------------------------------------------

def test_story2_resize():
    section("Story 2 - Resize image on fetch")

    print("\n  [2a] Width + height -> 200 + correctly sized image")
    TARGET_W, TARGET_H = 100, 80
    r, elapsed = get_timed({"image_url": TEST_IMAGE_URL,
                             "width": TARGET_W, "height": TARGET_H, "fit": "cover",
                             "bypass_cache": "true"})
    print_response_info(r, elapsed)
    save_image(r, f"2a_resize_{TARGET_W}x{TARGET_H}_cover")
    check(r.status_code == 200, "Status 200", f"Expected 200, got {r.status_code}")
    check(elapsed < NETWORK_TIMEOUT_MS,
          f"Resized in {elapsed:.0f} ms (under {NETWORK_TIMEOUT_MS} ms)",
          f"Too slow: {elapsed:.0f} ms")
    if r.status_code == 200:
        try:
            from PIL import Image as _Image
        except ImportError:
            _Image = None
        if _Image is None:
            print("     (Pillow not installed - skipping dimension check)")
        else:
            import io
            img = _Image.open(io.BytesIO(r.content))
            w, h = img.size
            check(w == TARGET_W and h == TARGET_H,
                  f"Dimensions correct: {w}x{h}",
                  f"Dimensions wrong: expected {TARGET_W}x{TARGET_H}, got {w}x{h}")

    print("\n  [2b] Width only -> 200")
    r, _ = get_timed({"image_url": TEST_IMAGE_URL, "width": 50})
    save_image(r, "2b_resize_width50_only")
    check(r.status_code == 200, "Status 200 for width-only request",
          f"Expected 200, got {r.status_code}")

    print("\n  [2c] Oversized dimension -> 400")
    r, _ = get_timed({"image_url": TEST_IMAGE_URL, "width": 99999})
    print_response_info(r)
    check(r.status_code == 400, "Status 400 for oversized width",
          f"Expected 400, got {r.status_code}")


# --- Story 3: Caching --------------------------------------------------------

def test_story3_caching():
    section("Story 3 - Image caching")

    print("\n  [3a] First request - prime the cache (fresh fetch)")
    r, elapsed = get_timed({"image_url": CACHE_IMAGE_URL, "bypass_cache": "true"})
    print_response_info(r, elapsed)
    check(r.status_code == 200, "First request succeeded", f"Unexpected {r.status_code}")
    check(r.headers.get("X-Cache", "").upper() == "MISS",
          "X-Cache is MISS on fresh fetch",
          f"Expected MISS, got {r.headers.get('X-Cache', '(none)')}")
    first_bytes = r.content

    print("\n  [3b] Second request - should be served from cache")
    r, elapsed = get_timed({"image_url": CACHE_IMAGE_URL})
    print_response_info(r, elapsed)
    save_image(r, "3b_cache_hit")
    check(r.status_code == 200, "Status 200 from cache",
          f"Expected 200, got {r.status_code}")
    check(r.headers.get("X-Cache", "").upper() == "HIT",
          f"X-Cache is HIT: {r.headers.get('X-Cache', '(none)')}",
          f"Expected HIT, got {r.headers.get('X-Cache', '(none)')}")
    check(elapsed < CACHE_TIMEOUT_MS,
          f"Cache responded in {elapsed:.0f} ms (under {CACHE_TIMEOUT_MS} ms)",
          f"Too slow for cache hit: {elapsed:.0f} ms")
    check(r.content == first_bytes,
          "Cached bytes identical to original fetch",
          "Cached bytes differ from original")

    print("\n  [3c] bypass_cache=true -> fresh fetch, X-Cache MISS")
    r, elapsed = get_timed({"image_url": CACHE_IMAGE_URL, "bypass_cache": "true"})
    print_response_info(r, elapsed)
    save_image(r, "3c_cache_bypass")
    check(r.status_code == 200, "Status 200 on cache bypass",
          f"Expected 200, got {r.status_code}")
    check(r.headers.get("X-Cache", "").upper() == "MISS",
          f"X-Cache is MISS on bypass: {r.headers.get('X-Cache', '(none)')}",
          f"Expected MISS, got {r.headers.get('X-Cache', '(none)')}")


# --- Bonus -------------------------------------------------------------------

def test_bonus_base64_usage():
    section("Bonus - Base64 encoding (as shown in spec)")
    print("\n  Fetching image and encoding to base64...")
    r, _ = get_timed({"image_url": TEST_IMAGE_URL})
    if r.status_code == 200:
        encoded = base64.b64encode(r.content).decode("utf-8")
        check(len(encoded) > 0, f"base64 string is {len(encoded)} chars",
              "base64 encoding failed")
        print(f"     Preview: {encoded[:60]}...")
    else:
        print(f"     Skipped - fetch returned {r.status_code}")


# --- Main --------------------------------------------------------------------

if __name__ == "__main__":
    print("\nImageFetcher Microservice - Test Suite")
    print(f"Target: {BASE_URL}")
    print(f"Image : {TEST_IMAGE_URL}")

    try:
        SESSION.get(BASE_URL, timeout=3)
    except requests.exceptions.ConnectionError:
        print(f"\n  ERROR: Cannot reach {BASE_URL}")
        print("  Make sure the microservice is running before running this test.\n")
        raise SystemExit(1)

    if "--preview" in sys.argv:
        preview_image(TEST_IMAGE_URL)
        raise SystemExit(0)

    test_story1_basic_fetch()
    test_story2_resize()
    test_story3_caching()
    test_bonus_base64_usage()

    print("\n" + "=" * 60)
    print("  All tests complete.")
    print("=" * 60 + "\n")
