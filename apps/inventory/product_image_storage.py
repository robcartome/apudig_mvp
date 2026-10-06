"""Cloudflare R2 adapter and product-image processing helpers."""

from io import BytesIO
from dataclasses import dataclass
import logging
import re
import warnings

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError


logger = logging.getLogger(__name__)


class ProductImageStorageError(Exception):
    """Raised when a product image cannot be processed or stored."""


PRODUCT_IMAGE_FILENAMES = {
    "main": "main.webp",
    "secondary": "secondary.webp",
    "tertiary": "tertiary.webp",
}

PRODUCT_THUMBNAIL_FILENAMES = {
    "main": "main-thumbnail.webp",
    "secondary": "secondary-thumbnail.webp",
    "tertiary": "tertiary-thumbnail.webp",
}


@dataclass(frozen=True)
class ProductImageUpload:
    image_key: str
    thumbnail_key: str

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def inspect_product_image(uploaded_file) -> tuple[int, int, str]:
    """Validate image content from Pillow metadata before full decoding."""
    try:
        uploaded_file.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(uploaded_file) as source:
                image_format = (source.format or "").upper()
                if image_format not in ALLOWED_IMAGE_FORMATS:
                    raise ProductImageStorageError(
                        "Formato no permitido. Usa JPEG, PNG o WebP."
                    )

                width, height = source.size
                if width <= 0 or height <= 0:
                    raise ProductImageStorageError("La imagen no tiene dimensiones válidas.")
                if max(width, height) > settings.PRODUCT_IMAGE_MAX_SOURCE_DIMENSION:
                    raise ProductImageStorageError(
                        "La imagen supera la dimensión máxima permitida de "
                        f"{settings.PRODUCT_IMAGE_MAX_SOURCE_DIMENSION} px."
                    )
                if width * height > settings.PRODUCT_IMAGE_MAX_PIXELS:
                    raise ProductImageStorageError(
                        "La imagen contiene demasiados píxeles para procesarla de forma segura."
                    )

                source.verify()
                return width, height, image_format
    except ProductImageStorageError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ProductImageStorageError(
            "La imagen es demasiado grande para procesarla de forma segura."
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError, MemoryError) as exc:
        raise ProductImageStorageError(
            "El archivo no es una imagen válida o está corrupto."
        ) from exc
    finally:
        try:
            uploaded_file.seek(0)
        except (AttributeError, OSError):
            pass


def build_product_image_key(product, slot: str = "main") -> str:
    if not product.company_id or not product.pk:
        raise ProductImageStorageError("El producto y la empresa deben tener un UUID válido.")
    try:
        filename = PRODUCT_IMAGE_FILENAMES[slot]
    except KeyError as exc:
        raise ProductImageStorageError("La posición de imagen no es válida.") from exc
    return f"products/{product.company_id}/{product.pk}/{filename}"


def build_product_thumbnail_key(product, slot: str = "main") -> str:
    if not product.company_id or not product.pk:
        raise ProductImageStorageError("El producto y la empresa deben tener un UUID válido.")
    try:
        filename = PRODUCT_THUMBNAIL_FILENAMES[slot]
    except KeyError as exc:
        raise ProductImageStorageError("La posición de imagen no es válida.") from exc
    return f"products/{product.company_id}/{product.pk}/{filename}"


def build_public_url(image_key: str) -> str:
    if not image_key:
        return ""
    # Keep legacy absolute values readable while new uploads store object keys only.
    if image_key.startswith(("https://", "http://")):
        return image_key
    base_url = settings.R2_PUBLIC_BASE_URL.rstrip("/")
    return f"{base_url}/{image_key.lstrip('/')}" if base_url else ""


def optimize_product_image(uploaded_file, *, max_dimension=None, quality=None) -> bytes:
    inspect_product_image(uploaded_file)
    max_dimension = max_dimension or settings.PRODUCT_IMAGE_MAX_DIMENSION
    quality = quality or settings.PRODUCT_IMAGE_WEBP_QUALITY
    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            image.thumbnail(
                (max_dimension, max_dimension),
                Image.Resampling.LANCZOS,
            )
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")

            output = BytesIO()
            image.save(
                output,
                format="WEBP",
                quality=quality,
                method=6,
            )
            return output.getvalue()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError, MemoryError) as exc:
        raise ProductImageStorageError("No se pudo procesar la imagen seleccionada.") from exc
    finally:
        try:
            uploaded_file.seek(0)
        except (AttributeError, OSError):
            pass


def _get_r2_client():
    required = {
        "R2_ACCOUNT_ID": settings.R2_ACCOUNT_ID,
        "R2_ACCESS_KEY_ID": settings.R2_ACCESS_KEY_ID,
        "R2_SECRET_ACCESS_KEY": settings.R2_SECRET_ACCESS_KEY,
        "R2_BUCKET_NAME": settings.R2_BUCKET_NAME,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ProductImageStorageError(
            "El almacenamiento de imágenes no está configurado correctamente."
        )

    if not re.fullmatch(r"[0-9a-fA-F]{32}", settings.R2_ACCOUNT_ID.strip()):
        raise ProductImageStorageError(
            "R2_ACCOUNT_ID debe contener solo el Account ID de Cloudflare "
            "(32 caracteres), no la URL del endpoint."
        )

    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID.strip()}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(
            connect_timeout=5,
            read_timeout=15,
            retries={"max_attempts": 2, "mode": "standard"},
            signature_version="s3v4",
        ),
    )


def _storage_error_message(exc, operation: str) -> str:
    from botocore.exceptions import ClientError, EndpointConnectionError

    logger.exception("R2 %s failed", operation)
    if isinstance(exc, EndpointConnectionError):
        return "No se pudo conectar con Cloudflare R2. Verifica R2_ACCOUNT_ID y la conexión de red."
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"InvalidAccessKeyId", "SignatureDoesNotMatch", "AccessDenied"}:
            return "Cloudflare R2 rechazó las credenciales o permisos configurados."
        if code in {"NoSuchBucket", "InvalidBucketName"}:
            return "El bucket configurado en R2_BUCKET_NAME no existe o no es válido."
    return f"No se pudo {operation} la imagen. Revisa el log del servidor."


def upload_product_image(product, uploaded_file, slot: str = "main") -> ProductImageUpload:
    image_key = build_product_image_key(product, slot=slot)
    thumbnail_key = build_product_thumbnail_key(product, slot=slot)
    image_body = optimize_product_image(uploaded_file)
    thumbnail_body = optimize_product_image(
        uploaded_file,
        max_dimension=settings.PRODUCT_IMAGE_THUMBNAIL_DIMENSION,
        quality=settings.PRODUCT_IMAGE_THUMBNAIL_QUALITY,
    )
    client = _get_r2_client()
    try:
        client.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=image_key,
            Body=image_body,
            ContentType="image/webp",
            CacheControl="public, max-age=300",
        )
        client.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=thumbnail_key,
            Body=thumbnail_body,
            ContentType="image/webp",
            CacheControl="public, max-age=300",
        )
    except ProductImageStorageError:
        raise
    except Exception as exc:
        # Keys are stable and may already belong to an existing product image.
        # Do not delete here: doing so could remove the previous visible image.
        raise ProductImageStorageError(_storage_error_message(exc, "subir")) from exc
    return ProductImageUpload(image_key=image_key, thumbnail_key=thumbnail_key)


def delete_product_image(image_key: str) -> None:
    if not image_key:
        return
    if image_key.startswith(("https://", "http://")):
        # A legacy external URL is not necessarily owned by this R2 bucket.
        return
    try:
        _get_r2_client().delete_object(Bucket=settings.R2_BUCKET_NAME, Key=image_key)
    except ProductImageStorageError:
        raise
    except Exception as exc:
        raise ProductImageStorageError(_storage_error_message(exc, "eliminar")) from exc
