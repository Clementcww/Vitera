"""Turning a clean render into something that looks like it came off a scanner.

An OCR number measured on a pristine 200 dpi PDF render is not a number about
the product. Real intake is a sheet that was printed, signed, photocopied once,
fed through an MFP at whatever setting it was left on, or photographed on a
phone at an angle under a ceiling light. The gap between those two conditions
is large enough that reporting only the first would be the paper-intake version
of reporting accuracy on balanced classes.

So the accuracy figure in `results/` is measured across the profiles below, and
each one is reported separately rather than averaged into a single headline.
A reader can then see the condition their own hospital is in.

Every profile is deterministic given the seed. The degradations themselves are
ordinary and uncontroversial — resolution loss, blur, skew, sensor noise, JPEG
quantisation, and an illumination gradient for the phone case — and they are
applied in the order a real document acquires them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True, slots=True)
class Profile:
    """One acquisition condition."""

    name: str
    description: str
    scale: float = 1.0  # resolution kept, relative to the render
    rotate_deg: float = 0.0
    blur_radius: float = 0.0
    noise_sigma: float = 0.0  # grey levels, 0-255
    contrast: float = 1.0
    brightness: float = 1.0
    jpeg_quality: int | None = None
    shadow: float = 0.0  # illumination gradient, 0 = flat


PROFILES: tuple[Profile, ...] = (
    Profile(
        "clean",
        "render langsung, tanpa cetak dan pindai",
    ),
    Profile(
        "office",
        "MFP rumah sakit 200 dpi, sekali pindai",
        scale=1.0,
        rotate_deg=0.3,
        blur_radius=0.6,
        noise_sigma=4.0,
        contrast=1.05,
        jpeg_quality=85,
    ),
    Profile(
        "photocopy",
        "fotokopi satu generasi lalu dipindai 150 dpi",
        scale=0.75,
        rotate_deg=0.8,
        blur_radius=0.8,
        noise_sigma=9.0,
        contrast=1.30,
        brightness=0.96,
        jpeg_quality=70,
    ),
    Profile(
        "phone",
        "difoto dengan ponsel, miring dan cahaya tidak rata",
        scale=0.62,
        rotate_deg=1.6,
        blur_radius=1.0,
        noise_sigma=13.0,
        contrast=1.15,
        brightness=1.02,
        jpeg_quality=60,
        shadow=0.22,
    ),
)

BY_NAME = {p.name: p for p in PROFILES}


def _shadow_mask(w: int, h: int, strength: float) -> np.ndarray:
    """A soft diagonal illumination gradient, as a multiplier."""
    ys, xs = np.mgrid[0:h, 0:w]
    g = (xs / max(1, w - 1)) * 0.6 + (ys / max(1, h - 1)) * 0.4
    mask: np.ndarray = (1.0 - strength * g).astype(np.float32)
    return mask


def degrade(src: Path, dst: Path, profile: Profile, *, seed: int = 0) -> Path:
    """Apply one profile to one page image."""
    from PIL import Image, ImageEnhance, ImageFilter

    img = Image.open(src).convert("L")

    if profile.scale != 1.0:
        w, h = img.size
        small = img.resize(
            (max(1, int(w * profile.scale)), max(1, int(h * profile.scale))),
            Image.Resampling.LANCZOS,
        )
        # Back up to the original size: the detail is gone, the pixel count is
        # not, which is what a low-dpi scan of an A4 sheet actually looks like.
        img = small.resize((w, h), Image.Resampling.BICUBIC)

    if profile.rotate_deg:
        img = img.rotate(
            profile.rotate_deg,
            resample=Image.Resampling.BICUBIC,
            fillcolor=255,
            expand=False,
        )

    if profile.blur_radius:
        img = img.filter(ImageFilter.GaussianBlur(profile.blur_radius))

    if profile.contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(profile.contrast)
    if profile.brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(profile.brightness)

    arr = np.asarray(img, dtype=np.float32)
    if profile.shadow:
        arr = arr * _shadow_mask(arr.shape[1], arr.shape[0], profile.shadow)
    if profile.noise_sigma:
        rng = np.random.default_rng(seed)
        arr = arr + rng.normal(0.0, profile.noise_sigma, arr.shape).astype(np.float32)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="L")

    dst.parent.mkdir(parents=True, exist_ok=True)
    if profile.jpeg_quality is None:
        img.save(dst)
        return dst

    # Written as JPEG rather than round-tripped through one and re-saved as
    # PNG. The pixels are identical either way, and the file is a quarter of
    # the size — which matters because a committed sample scan is what makes
    # `make intake` replayable on a machine with no OCR engine.
    out = dst.with_suffix(".jpg")
    img.convert("RGB").save(out, format="JPEG", quality=profile.jpeg_quality)
    return out


__all__ = ["BY_NAME", "PROFILES", "Profile", "degrade"]
