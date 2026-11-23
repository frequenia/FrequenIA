"""Avatares privados: imagem reprocessada, sem EXIF e sem uso biométrico."""
from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_STORED_BYTES = 256 * 1024
MAX_PIXELS = 16_000_000


def normalize_profile_photo(content):
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError('Escolha uma imagem JPG, PNG ou WebP de até 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise ValueError('Formato não aceito. Use JPG, PNG ou WebP.')
                if source.width * source.height > MAX_PIXELS or min(source.size) < 64:
                    raise ValueError('A imagem deve ter pelo menos 64 × 64 e no máximo 16 milhões de pixels.')
                if getattr(source, 'is_animated', False):
                    raise ValueError('Escolha uma imagem sem animação.')
                source.load()
                oriented = ImageOps.exif_transpose(source).convert('RGBA')
                square = ImageOps.fit(oriented, (512, 512), method=Image.Resampling.LANCZOS)
                clean = Image.new('RGB', square.size, 'white')
                clean.paste(square, mask=square.getchannel('A'))
                output = BytesIO()
                clean.save(output, format='JPEG', quality=85, optimize=True)
                result = output.getvalue()
                if len(result) > MAX_STORED_BYTES:
                    raise ValueError('Não foi possível reduzir a imagem. Escolha outra foto.')
                return result
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('Não foi possível ler a imagem. Escolha um JPG, PNG ou WebP válido.') from exc
