"""Image storage.

Uploads are validated and normalised with Pillow: re-encoded as WebP (smaller files,
and re-encoding drops anything hidden in the original file such as scripts or
metadata), resized so the longer side is at most IMAGE_MAX_SIDE, and saved under a
random name in UPLOAD_DIR.

Everything outside this module only deals with the returned `filename` key and
`url_for_image()`, so moving to cloud storage later means changing this file only.
"""
import os
import secrets

from flask import current_app, url_for
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "MPO"}  # MPO = multi-picture JPEG from some cameras
Image.MAX_IMAGE_PIXELS = 60_000_000                     # refuse "decompression bomb" images


class ImageRejected(ValueError):
    """The upload isn't a usable image. The message is shown to the admin (Hebrew)."""


def _upload_dir() -> str:
    path = current_app.config["UPLOAD_DIR"]
    os.makedirs(path, exist_ok=True)
    return path


def save_image(file_storage) -> tuple[str, int, int]:
    """Validate, normalise and store an uploaded image. Returns (filename, width, height)."""
    data = file_storage.stream
    data.seek(0, os.SEEK_END)
    size = data.tell()
    data.seek(0)
    if size == 0:
        raise ImageRejected("הקובץ ריק")
    if size > current_app.config["MAX_IMAGE_BYTES"]:
        limit_mb = current_app.config["MAX_IMAGE_BYTES"] // (1024 * 1024)
        raise ImageRejected(f"הקובץ גדול מ-{limit_mb}MB")

    try:
        with Image.open(data) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise ImageRejected("סוג הקובץ אינו נתמך. אפשר להעלות JPG, PNG או WEBP")
            probe.verify()  # structural check; the image must be reopened afterwards
        data.seek(0)
        with Image.open(data) as img:
            img = ImageOps.exif_transpose(img)  # respect phone camera rotation
            img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
            img.thumbnail((current_app.config["IMAGE_MAX_SIDE"],) * 2, Image.Resampling.LANCZOS)
            filename = f"{secrets.token_hex(12)}.webp"
            img.save(os.path.join(_upload_dir(), filename), "WEBP", quality=86, method=6)
            return filename, img.width, img.height
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as exc:
        raise ImageRejected("הקובץ אינו תמונה תקינה") from exc


def delete_image(filename: str) -> None:
    path = os.path.join(_upload_dir(), os.path.basename(filename))
    if os.path.exists(path):
        os.remove(path)


def url_for_image(filename: str) -> str:
    return url_for("media", filename=filename)
