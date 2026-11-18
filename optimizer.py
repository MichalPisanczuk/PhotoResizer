import os
import shutil
import struct
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageCms, ImageOps, PngImagePlugin


EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


class SkippedImage(Exception):
    pass


@dataclass(frozen=True)
class Options:
    format: str
    lossless: bool
    resize: bool = True
    quality: int = 92


@dataclass(frozen=True)
class Result:
    path: Path
    before: int
    after: int
    dimensions: tuple[int, int]
    copied: bool


def web_dimensions(size):
    width, height = size
    min_width, min_height = (1920, 1080) if width >= height else (1080, 1920)
    if width < min_width or height < min_height:
        return size
    if min_width * height >= min_height * width:
        return min_width, round(height * min_width / width)
    return round(width * min_height / height), min_height


def prepare_pixels(image, options):
    profile = image.info.get("icc_profile")
    if options.format == "PNG" and image.mode == "P" and (options.lossless or not options.resize):
        return image, profile
    if image.mode == "P":
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")

    if options.format == "PNG" and image.mode in {"1", "L", "LA", "RGB", "RGBA", "I;16"}:
        return image, profile

    if options.format == "WEBP" and image.mode in {"RGB", "RGBA"}:
        if image.has_transparency_data and image.mode == "RGB":
            image = image.convert("RGBA")
        return image, profile

    if options.lossless:
        if options.format == "WEBP" and image.mode in {"1", "L", "LA"} and not profile:
            return image.convert("RGBA" if image.has_transparency_data else "RGB"), None
        raise SkippedImage("Ten format docelowy nie zachowa bezstratnie kolorów lub głębi obrazu.")

    if image.mode in {"CMYK", "LAB"} and profile:
        target_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
        image = ImageCms.profileToProfile(image, BytesIO(profile), target_profile, outputMode="RGB")
        profile = target_profile.tobytes()
    elif image.mode in {"1", "L", "LA"}:
        if profile and options.format != "JPEG":
            target_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
            gray = image.convert("L")
            converted = ImageCms.profileToProfile(gray, BytesIO(profile), target_profile, outputMode="RGB")
            if image.has_transparency_data:
                converted.putalpha(image.convert("RGBA").getchannel("A"))
            return converted, target_profile.tobytes()
        if not image.has_transparency_data and options.format == "JPEG":
            return image.convert("L"), profile
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")
        profile = None
    elif image.mode not in {"RGB", "RGBA"}:
        if image.mode.startswith("I;16"):
            image = image.convert("I").point(lambda value: value / 257, "L")
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")
        profile = None
    return image, profile


def publish(temp_path, directory, stem, extension):
    index = 1
    while True:
        suffix = "" if index == 1 else f"_{index}"
        target = directory / f"{stem}_optymalizacja{suffix}{extension}"
        try:
            if os.name == "nt":
                temp_path.rename(target)
            else:
                os.link(temp_path, target)
            return target
        except FileExistsError:
            index += 1


def optimize(source, directory, options):
    before = source.stat().st_size
    with tempfile.NamedTemporaryFile(dir=directory, prefix=".resizer-", suffix=".tmp", delete=False) as temporary:
        temp_path = Path(temporary.name)

    try:
        copied = False
        with Image.open(source) as original:
            if getattr(original, "n_frames", 1) > 1:
                raise SkippedImage("Plik zawiera animację lub wiele stron.")
            orientation = original.getexif().get(274, 1)
            source_format = original.format
            dimensions = original.size
            if orientation in {5, 6, 7, 8}:
                dimensions = dimensions[::-1]
            if options.lossless and options.format == "JPEG":
                if source_format != "JPEG":
                    raise SkippedImage("Zapis tego pliku do JPG wymaga kompresji stratnej. Wybierz PNG lub WebP.")
                original.load()
                copied = True
            else:
                if options.lossless and source_format == "PNG" and original.mode in {"RGB", "RGBA", "LA"}:
                    with source.open("rb") as png:
                        if png.read(25)[24:25] == b"\x10":
                            raise SkippedImage("Źródłowy PNG ma 16 bitów na kanał. Zapis grozi utratą precyzji.")
                if (options.lossless and options.format == "WEBP" and source_format == "PNG"
                        and "icc_profile" not in original.info and "srgb" not in original.info
                        and ("gamma" in original.info or "chromaticity" in original.info)):
                    raise SkippedImage("Wybierz PNG, aby zachować ustawienia kolorów tego obrazu.")
                if options.lossless and source_format == "TIFF" and original.mode in {"RGB", "RGBA", "LA", "CMYK"}:
                    if max(original.tag_v2.get(258, (8,))) > 8:
                        raise SkippedImage("Źródłowy TIFF ma ponad 8 bitów na kanał. Zapis grozi utratą precyzji.")
                # Pillow applies TIFF orientation while decoding.
                image = original.copy() if source_format == "TIFF" else ImageOps.exif_transpose(original)
                if image.mode == "RGB" and image.has_transparency_data and not options.lossless:
                    image = image.convert("RGBA")
                image, profile = prepare_pixels(image, options)
                dimensions = image.size
                if not options.lossless and options.resize:
                    dimensions = web_dimensions(image.size)
                    if image.size != dimensions:
                        if image.mode == "1":
                            image = image.convert("L")
                        if image.mode == "L" and image.has_transparency_data:
                            image = image.convert("LA")
                        image = image.resize(dimensions, Image.Resampling.LANCZOS)

                settings = {"icc_profile": profile} if profile else {}
                if options.format == "JPEG":
                    if image.has_transparency_data:
                        rgba = image.convert("RGBA")
                        background = Image.new("RGB", rgba.size, "white")
                        background.paste(rgba, mask=rgba.getchannel("A"))
                        image = background
                    settings.update(quality=options.quality, subsampling=0, optimize=True, progressive=True)
                elif options.format == "PNG":
                    settings.update(optimize=True)
                    if "transparency" in image.info and image.mode in {"1", "L", "P", "RGB", "I;16"}:
                        settings["transparency"] = image.info["transparency"]
                    if source_format == "PNG":
                        png_info = PngImagePlugin.PngInfo()
                        if "gamma" in original.info:
                            png_info.add(b"gAMA", struct.pack(">I", round(original.info["gamma"] * 100000)))
                        if "chromaticity" in original.info:
                            values = [round(value * 100000) for value in original.info["chromaticity"]]
                            png_info.add(b"cHRM", struct.pack(">8I", *values))
                        if "srgb" in original.info:
                            png_info.add(b"sRGB", bytes([original.info["srgb"]]))
                        for chunk, data in original.private_chunks:
                            if chunk == b"cICP":
                                png_info.add(chunk, data)
                        settings["pnginfo"] = png_info
                else:
                    settings.update(lossless=options.lossless, quality=100 if options.lossless else options.quality,
                                    method=6, exact=options.lossless)
                # EXIF orientation is now in the pixels. Keep the ICC profile for color rendering.
                image.info.clear()
                image.save(temp_path, format=options.format, **settings)
                if source_format == options.format and image.size == original.size and orientation == 1:
                    copied = temp_path.stat().st_size >= before

        if copied:
            shutil.copyfile(source, temp_path)
        after = temp_path.stat().st_size
        target = publish(temp_path, directory, source.stem, EXTENSIONS[options.format])
        return Result(target, before, after, dimensions, copied)
    finally:
        temp_path.unlink(missing_ok=True)
