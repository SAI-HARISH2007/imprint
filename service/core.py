"""Image side of Imprint: add an invisible ID, read it back, fingerprint how an image looks.

Nothing here stores images. The functions take bytes and return values.
"""
import base64
import io
import secrets
import threading
from functools import lru_cache

import imagehash
from PIL import Image
from trustmark import TrustMark

HASH_SIZE = 16          # 16x16 pHash = 256 bits, 64 hex chars, fits a bytes32
MAX_PIXELS = 25_000_000


TM_LOCK = threading.RLock()  # one model, one caller at a time


class BadImage(ValueError):
    pass


@lru_cache(maxsize=1)
def _tm() -> TrustMark:
    return TrustMark(verbose=False, model_type="Q", encoding_type=TrustMark.Encoding.BCH_5)


def payload_bits() -> int:
    return _tm().schemaCapacity()


def load_image(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:
        raise BadImage("could not read that file as an image") from e
    if img.width * img.height > MAX_PIXELS:
        raise BadImage("image is too large (limit 25 megapixels)")
    return img.convert("RGB")


def bits_to_id(bits: str) -> str:
    """Watermark payload bits -> 0x-prefixed bytes32 hex, the key used in the registry."""
    return "0x" + int(bits, 2).to_bytes(32, "big").hex()


def fingerprint(img: Image.Image) -> str:
    """256-bit perceptual hash as 64 hex chars (no 0x)."""
    return str(imagehash.phash(img, hash_size=HASH_SIZE))


def distance(a: str, b: str) -> int:
    return int(imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b))


def mark(data: bytes) -> dict:
    """Embed a fresh random ID. Returns the marked PNG (base64), the ID, and the marked image's fingerprint."""
    img = load_image(data)
    bits = "".join(secrets.choice("01") for _ in range(payload_bits()))
    with TM_LOCK:
        marked = _tm().encode(img, bits, MODE="binary").convert("RGB")
    buf = io.BytesIO()
    marked.save(buf, "PNG")
    return {
        "watermark_id": bits_to_id(bits),
        "fingerprint": fingerprint(marked),
        "width": marked.width,
        "height": marked.height,
        "image_png_base64": base64.b64encode(buf.getvalue()).decode(),
    }


def read(data: bytes) -> dict:
    """Try to read the hidden ID and fingerprint the image as it looks now."""
    img = load_image(data)
    try:
        with TM_LOCK:
            secret, present, _ = _tm().decode(img, MODE="binary")
    except Exception:
        secret, present = "", False
    present = bool(present) and bool(secret)
    return {
        "watermark_present": present,
        "watermark_id": bits_to_id(secret) if present else None,
        "fingerprint": fingerprint(img),
    }
