"""Bounded, metadata-free pet portraits. No user-supplied paths or public files."""
import base64
import binascii
import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PHOTO_BYTES = 2 * 1024 * 1024


def normalize_photo(data_url: str) -> str:
    header, separator, encoded = data_url.partition(',')
    if not separator or header not in {'data:image/jpeg;base64', 'data:image/png;base64', 'data:image/webp;base64'}:
        raise ValueError('pet_photo_invalid')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('pet_photo_invalid') from exc
    if len(raw) > MAX_PHOTO_BYTES:
        raise ValueError('pet_photo_too_large')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'} or source.width * source.height > 16_000_000:
                    raise ValueError('pet_photo_invalid')
                source.load()
                portrait = ImageOps.fit(ImageOps.exif_transpose(source).convert('RGB'), (512, 512))
                result = io.BytesIO()
                portrait.save(result, format='JPEG', quality=85, optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('pet_photo_invalid') from exc
    return 'data:image/jpeg;base64,' + base64.b64encode(result.getvalue()).decode('ascii')
