"""
core/imagegen.py
================
Image generation layer for the A+ Content Studio.

Claude writes the gpt-image prompts; THIS module turns them into actual images by
calling the OpenAI image API (default model 'gpt-image-1', configurable in
Settings). When you upload one or more product reference images, they are passed
to the images.edit endpoint so the generated scene keeps the product's identity;
with no reference image it falls back to images.generate.

Key + model come from Settings (DB). Every call returns (png_bytes|None, status)
and never raises into the UI.

Note: the public image API renders up to 1536px; the A+ prompts ask for 2000px so
the designer upscales/crops after. Choose 1024x1024 (1:1) here to match the A+
square ratio.
"""

from __future__ import annotations
import io
import base64

from core import db

# Sizes the OpenAI image API supports (square first = matches A+ 1:1).
SUPPORTED_SIZES = ["1024x1024", "1536x1024", "1024x1536"]
DEFAULT_MODEL = "gpt-image-1"


def image_model() -> str:
    return db.get_setting("image_model", DEFAULT_MODEL) or DEFAULT_MODEL


def has_image_key() -> bool:
    return bool(db.get_setting("openai_api_key", ""))


def generate_image(prompt: str, reference_images: list[bytes] | None = None,
                   size: str = "1024x1024") -> tuple[bytes | None, str]:
    """Generate one image from a prompt (+ optional reference images).

    reference_images: list of raw image bytes (PNG/JPG). If provided, uses the
    edit endpoint so the product identity is preserved.
    Returns (png_bytes, status). status: 'ok' | 'no_key' | 'error: ...'.
    """
    key = db.get_setting("openai_api_key", "")
    if not key:
        return None, "no_key"
    model = image_model()
    import time
    import openai
    # Longer per-request timeout + SDK retries; image generation is slow and the
    # connection can drop mid-call ("Connection error").
    client = openai.OpenAI(api_key=key, timeout=240.0, max_retries=2)
    last = ""
    for attempt in range(4):
        try:
            if reference_images:
                files = []
                for i, b in enumerate(reference_images):
                    bio = io.BytesIO(b)
                    bio.name = f"reference_{i}.png"
                    files.append(bio)
                base = dict(model=model, image=files if len(files) > 1 else files[0],
                            prompt=prompt, size=size)
                # input_fidelity='high' makes the model preserve the product's EXACT
                # details (dials, buttons, branding, proportions) while still changing
                # the camera angle and scene. Fall back if the API rejects the param.
                try:
                    resp = client.images.edit(**base, input_fidelity="high")
                except TypeError:
                    resp = client.images.edit(**base)
                except Exception as e:
                    if "input_fidelity" in str(e):
                        resp = client.images.edit(**base)
                    else:
                        raise
            else:
                resp = client.images.generate(model=model, prompt=prompt, size=size)
            item = resp.data[0]
            if getattr(item, "b64_json", None):
                return base64.b64decode(item.b64_json), "ok"
            if getattr(item, "url", None):
                import requests
                return requests.get(item.url, timeout=60).content, "ok"
            return None, "error: no image data returned"
        except Exception as e:
            last = str(e)
            transient = any(k in last.lower() for k in (
                "connection", "timeout", "timed out", "temporarily", "rate limit",
                "429", "500", "502", "503", "504", "overloaded", "apiconnection"))
            if attempt < 3 and transient:
                time.sleep(2.5 * (attempt + 1))
                continue
            return None, f"error: {last[:140]}"
    return None, f"error: {last[:140]}"
