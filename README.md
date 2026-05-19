# ImageFetcher Microservice

Fetches images from URLs, optionally resizes them, and caches results so repeated
requests are fast. Other programs talk to it over HTTP on localhost.

---

## How to run it

    pip install flask requests Pillow waitress
    python app.py

The service is now listening at http://localhost:5100

---

## How to request data

Send an HTTP GET to http://localhost:5100/fetch with these query parameters:

| Parameter      | Required | Description                                          |
|----------------|----------|------------------------------------------------------|
| image_url      | yes      | Full URL of the image to fetch                       |
| width          | no       | Resize to this width in pixels (max 4096)            |
| height         | no       | Resize to this height in pixels (max 4096)           |
| fit            | no       | cover, contain, fill, inside, outside (default: cover) |
| bypass_cache   | no       | Set to true to skip the cache and force a fresh fetch |

Example calls:

    import requests

    # Basic fetch
    response = requests.get("http://localhost:5100/fetch", params={
        "image_url": "https://example.com/photo.jpg"
    })

    # Fetch and resize
    response = requests.get("http://localhost:5100/fetch", params={
        "image_url": "https://example.com/photo.jpg",
        "width": 300,
        "height": 200,
        "fit": "cover"
    })

    # Force a fresh fetch, bypassing the cache
    response = requests.get("http://localhost:5100/fetch", params={
        "image_url": "https://example.com/photo.jpg",
        "bypass_cache": "true"
    })

---

## How to receive data

The service returns one of two things depending on whether the request succeeded.

**Success - 200**
- Body: raw image bytes
- Header X-Cache: HIT if served from cache, MISS if freshly fetched

**Errors**
- 400: bad or missing parameters - body is JSON: {"error": "..."}
- 502: could not reach the source URL - body is JSON: {"error": "..."}

Example:

    import base64, requests

    response = requests.get("http://localhost:5100/fetch", params={
        "image_url": "https://example.com/photo.png",
        "width": 300
    })

    if response.status_code == 200:
        image_bytes = response.content
        cache_status = response.headers.get("X-Cache")  # "HIT" or "MISS"

        # Encode to base64 for embedding in a web page
        encoded = base64.b64encode(image_bytes).decode("utf-8")

    else:
        error = response.json()
        print(error["error"])

---

## UML Sequence Diagram

    Caller                  ImageFetcher            Origin URL
      |                          |                       |
      | GET /fetch?image_url=... |                       |
      |------------------------->|                       |
      |                          |                       |
      |                          | Validate params       |
      |                          |----------             |
      |                          |         |             |
      |      400 {"error":"..."} |<---------             |
      |<-------------------------|  (if invalid)         |
      |                          |                       |
      |                          | Check cache           |
      |                          |----------             |
      |                          |         |             |
      |    200 X-Cache: HIT      |<---------             |
      |<-------------------------|  (if cached)          |
      |                          |                       |
      |                          | GET image_url ------->|
      |                          |                       |
      |                          |        200 + bytes    |
      |                          |<----------------------|
      |                          |                       |
      |                          | (or error)            |
      |      502 {"error":"..."} |<------- error         |
      |<-------------------------|                       |
      |                          |                       |
      |                          | Resize (if requested) |
      |                          |----------             |
      |                          |         |             |
      |                          |<---------             |
      |                          |                       |
      |                          | Store in cache        |
      |                          |----------             |
      |                          |         |             |
      |                          |<---------             |
      |                          |                       |
      |    200 X-Cache: MISS     |                       |
      |<-------------------------|                       |
      |                          |                       |

---

Authors: Declan, Mirna
Repository: https://github.com/DeclanOsu/ImageFetcherCS361
