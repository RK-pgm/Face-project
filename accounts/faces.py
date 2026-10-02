import base64
import binascii
import math
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

DESCRIPTOR_LENGTH = 128
MAX_PHOTO_BYTES = 3 * 1024 * 1024     
MAX_PHOTO_PIXELS = 4_000_000          
SAVED_PHOTO_MAX_SIDE = 480            


class FaceDataError(ValueError):
    """ข้อมูลใบหน้าที่ส่งมาไม่ถูกต้อง"""
def parse_descriptor(value):
    if not isinstance(value, (list, tuple)) or len(value) != DESCRIPTOR_LENGTH:
        raise FaceDataError("descriptor need word 128")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise FaceDataError("descriptor is number")
        if not math.isfinite(item) or abs(item) > 10:
            raise FaceDataError("Value descriptor error")
        result.append(float(item))
    if sum(x * x for x in result) < 1e-6:
        raise FaceDataError("descriptor free")
    return result


def face_distance(a, b):
    return math.dist(a, b)


def is_same_person(distance):
    return distance < settings.FACE_MATCH_THRESHOLD


def photo_from_data_url(data_url):
    if not isinstance(data_url, str) or not data_url.startswith("data:image/") or "," not in data_url:
        raise FaceDataError("Image error")
    _, _, b64 = data_url.partition(",")
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise FaceDataError("Image Error")
    if not raw or len(raw) > MAX_PHOTO_BYTES:
        raise FaceDataError("file image don't have or too large")

    try:
        probe = Image.open(BytesIO(raw))
        if probe.format not in ("JPEG", "PNG"):
            raise FaceDataError("Support image is JPEG/PNG")
        if probe.width * probe.height > MAX_PHOTO_PIXELS:
            raise FaceDataError("Image so too large")
        probe.verify() 
        image = Image.open(BytesIO(raw)).convert("RGB")  
    except FaceDataError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise FaceDataError("Cannot file image")

    image.thumbnail((SAVED_PHOTO_MAX_SIDE, SAVED_PHOTO_MAX_SIDE))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return ContentFile(buffer.getvalue(), name="face.jpg")
