"""Utilidades para que el contenido visible del logo aproveche el área imprimible."""

from io import BytesIO

from PIL import Image, ImageChops, ImageOps


def normalized_logo_stream(source, *, padding_ratio=0.025):
    """Devuelve un PNG recortado alrededor del contenido visible del logo.

    Admite transparencia y fondos uniformes claros u oscuros. Se conserva un
    pequeño margen para evitar que trazos del logo queden pegados al borde.
    """
    with Image.open(source) as opened_image:
        image = ImageOps.exif_transpose(opened_image).convert("RGBA")
    full_box = (0, 0, image.width, image.height)
    alpha = image.getchannel("A")
    alpha_box = alpha.getbbox()

    if alpha.getextrema()[0] < 255 and alpha_box and alpha_box != full_box:
        content_box = alpha_box
    else:
        rgb = image.convert("RGB")
        corners = (
            rgb.getpixel((0, 0)),
            rgb.getpixel((max(rgb.width - 1, 0), 0)),
            rgb.getpixel((0, max(rgb.height - 1, 0))),
            rgb.getpixel((max(rgb.width - 1, 0), max(rgb.height - 1, 0))),
        )
        background = tuple(sum(pixel[channel] for pixel in corners) // 4 for channel in range(3))
        difference = ImageChops.difference(rgb, Image.new("RGB", rgb.size, background))
        mask = difference.convert("L").point(lambda value: 255 if value > 12 else 0)
        content_box = mask.getbbox() or full_box

    left, top, right, bottom = content_box
    padding = max(2, round(max(right - left, bottom - top) * padding_ratio))
    crop_box = (
        max(0, left - padding),
        max(0, top - padding),
        min(image.width, right + padding),
        min(image.height, bottom + padding),
    )
    normalized = image.crop(crop_box)
    output = BytesIO()
    normalized.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output
