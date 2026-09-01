from __future__ import annotations

import base64
import binascii
import struct
from dataclasses import dataclass


SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 6 * 1024 * 1024


@dataclass(frozen=True)
class DecodedImage:
    data: bytes
    mime_type: str
    extension: str
    width: int | None
    height: int | None


def decode_image_data_url(value: str) -> DecodedImage:
    try:
        header, encoded = value.split(",", 1)
    except ValueError as exc:
        raise ValueError("photo must be a base64 image data URL") from exc
    if not header.startswith("data:") or ";base64" not in header:
        raise ValueError("photo must be a base64 image data URL")
    mime_type = header[5:].split(";", 1)[0].lower()
    if mime_type not in SUPPORTED_MIME_TYPES:
        raise ValueError("photo must be JPEG, PNG, or WebP")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("photo contains invalid base64 data") from exc
    if not data:
        raise ValueError("photo is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("photo exceeds the 6 MB upload limit")
    detected = detect_mime_type(data)
    if detected != mime_type:
        raise ValueError("photo content does not match its declared image type")
    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[mime_type]
    width, height = image_dimensions(data, mime_type)
    return DecodedImage(data, mime_type, extension, width, height)


def detect_mime_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def image_dimensions(data: bytes, mime_type: str) -> tuple[int | None, int | None]:
    if mime_type == "image/png" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if mime_type == "image/jpeg":
        offset = 2
        while offset + 9 < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            marker = data[offset + 1]
            offset += 2
            if marker in {0xD8, 0xD9}:
                continue
            if offset + 2 > len(data):
                break
            segment_len = int.from_bytes(data[offset : offset + 2], "big")
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and offset + 7 < len(data):
                return (
                    int.from_bytes(data[offset + 5 : offset + 7], "big"),
                    int.from_bytes(data[offset + 3 : offset + 5], "big"),
                )
            if segment_len < 2:
                break
            offset += segment_len
    if mime_type == "image/webp" and len(data) >= 30 and data[12:16] == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    return None, None


def score_image_quality(image: DecodedImage) -> float:
    score = 0.15
    if len(image.data) >= 20_000:
        score += 0.2
    if len(image.data) >= 100_000:
        score += 0.15
    if image.width and image.height:
        shortest = min(image.width, image.height)
        longest = max(image.width, image.height)
        if shortest >= 480:
            score += 0.25
        elif shortest >= 320:
            score += 0.12
        if longest >= 640:
            score += 0.15
        if longest >= 960:
            score += 0.25
    return round(min(score, 1.0), 3)
