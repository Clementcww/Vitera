"""OCR: pixels in, located text out. Perception only, no interpretation.

This module's whole output is a list of `Observation` — a string, a confidence,
and where on the page it was found. It never decides what a string *means*;
that is `extract.py`, and it is deterministic. Keeping the two apart is what
lets the extraction be auditable: a wrong field is either a bad read (visible
in the confidence and the box) or a bad rule (visible in one screen of code),
and you can always tell which.

Three backends, tried in order:

    vision      Apple Vision, via pyobjc. Offline, no API key, handles
                `id-ID`, and good on photographs of paper — which is what a
                casemix unit will actually hand it.
    tesseract   if the binary is installed. Present so the path is not
                macOS-only for a judge on Linux.
    cache       replay of a recorded read, keyed on the hash of the image
                bytes. This is why the Make targets are reproducible on a
                machine with neither engine installed.

Any real backend also *writes* the cache, so running the demo once on a Mac
produces the artifact that makes it replayable everywhere. Same shape as
`VITERA_LLM_MODE`, for the same reason.

    VITERA_OCR_MODE = auto | live | cache      (default: auto)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

CACHE_DIR = Path("data/generated/ocr_cache")


class OCRUnavailable(RuntimeError):
    """No backend could read this image. The caller degrades; it never guesses."""


@dataclass(frozen=True, slots=True)
class Observation:
    """One recognised line, with where it came from.

    Coordinates are page-normalised with the origin at the TOP left, because
    every rule in `extract.py` is written in reading order and Vision's
    bottom-left origin would invert half of them.
    """

    text: str
    confidence: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def same_band(self, other: Observation, tol: float = 0.5) -> bool:
        """True when two observations sit on the same printed line.

        Centre distance rather than extent overlap, and with a height-ratio
        guard. Both clauses are there because of one real artifact: a rotated
        watermark is recognised as a single observation spanning most of the
        page, it vertically overlaps every row completely, and under an
        overlap rule it joins — and therefore merges — all of them.
        """
        h = min(self.height, other.height)
        if h <= 0:
            return False
        if max(self.height, other.height) / h > 3.0:
            return False
        return abs(self.cy - other.cy) <= tol * h

    def to_json(self) -> dict[str, float | str]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
        }

    @staticmethod
    def from_json(d: dict[str, object]) -> Observation:
        return Observation(
            text=str(d["text"]),
            confidence=float(d["confidence"]),  # type: ignore[arg-type]
            x0=float(d["x0"]),  # type: ignore[arg-type]
            y0=float(d["y0"]),  # type: ignore[arg-type]
            x1=float(d["x1"]),  # type: ignore[arg-type]
            y1=float(d["y1"]),  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class Page:
    index: int
    engine: str
    observations: tuple[Observation, ...]


def ocr_mode() -> str:
    return os.environ.get("VITERA_OCR_MODE", "auto").strip().lower()


# ---------------------------------------------------------------------------
# Rasterisation
# ---------------------------------------------------------------------------


def rasterise(pdf: Path, out_dir: Path, *, dpi: int = 200) -> list[Path]:
    """PDF -> PNG per page, via poppler.

    200 dpi is chosen, not default: it is roughly what a hospital MFP produces
    and low enough that the OCR numbers we report are not flattered by a
    resolution nobody scans at.
    """
    if shutil.which("pdftoppm") is None:
        raise OCRUnavailable(
            "pdftoppm tidak ditemukan. Pasang poppler (brew install poppler) "
            "atau berikan berkas gambar (PNG/JPG) langsung."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / pdf.stem
    subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(prefix)],
        check=True,
        capture_output=True,
    )
    return sorted(out_dir.glob(f"{pdf.stem}-*.png"))


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


def _vision_pass(image: Path, level: int) -> list[Observation]:
    import Vision
    from Foundation import NSURL

    url = NSURL.fileURLWithPath_(str(image))
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(level)  # 0 accurate, 1 fast
    request.setRecognitionLanguages_(["id-ID", "en-US"])
    # Language correction is OFF on purpose. It is tuned for prose and would
    # happily turn RITL into RITEL and a kode PPK into a word.
    request.setUsesLanguageCorrection_(False)

    ok, err = handler.performRequests_error_([request], None)
    if not ok:
        raise OCRUnavailable(f"Vision gagal membaca {image.name}: {err}")

    out: list[Observation] = []
    for obs in request.results() or []:
        candidates = obs.topCandidates_(1)
        if not candidates:
            continue
        best = candidates[0]
        text = str(best.string()).strip()
        if not text:
            continue
        box = obs.boundingBox()
        x0 = float(box.origin.x)
        w = float(box.size.width)
        h = float(box.size.height)
        y_bottom = float(box.origin.y)
        out.append(
            Observation(
                text=text,
                confidence=float(best.confidence()),
                x0=x0,
                # Vision's origin is bottom-left; flip to reading order.
                y0=1.0 - (y_bottom + h),
                x1=x0 + w,
                y1=1.0 - y_bottom,
            )
        )
    return out


def _covers(a: Observation, b: Observation) -> bool:
    """True when `a` already contains the centre of `b`."""
    cx = (b.x0 + b.x1) / 2
    return a.x0 <= cx <= a.x1 and a.y0 <= b.cy <= a.y1


def _vision(image: Path) -> tuple[Observation, ...]:
    """Two passes, accurate then fast, with the fast one filling gaps.

    Not belt-and-braces — a measured defect. On a full-page rincian the
    accurate recogniser silently drops the entire KODE INA-CBG column, while
    reading every neighbouring column correctly; the same column crops out and
    reads perfectly on its own, and the fast recogniser gets it on the full
    page. Rather than tune around that, both passes run and any fast
    observation whose centre falls in no accurate box is kept.

    The merge is one-directional on purpose: accurate wins wherever the two
    disagree, so the second pass can only add coverage, never overwrite a
    better read.
    """
    accurate = _vision_pass(image, 0)
    extra = [
        o for o in _vision_pass(image, 1) if not any(_covers(a, o) for a in accurate)
    ]
    return tuple(sorted(accurate + extra, key=lambda o: (round(o.cy, 3), o.x0)))


def _tesseract(image: Path) -> tuple[Observation, ...]:
    """TSV output, grouped to lines. Kept deliberately small — it is the
    portability backend, not the one the numbers are reported on."""
    from PIL import Image

    with Image.open(image) as im:
        width, height = im.size
    proc = subprocess.run(
        ["tesseract", str(image), "stdout", "-l", "ind+eng", "--psm", "6", "tsv"],
        check=True,
        capture_output=True,
        text=True,
    )
    lines: dict[tuple[str, ...], list[list[str]]] = {}
    for row in proc.stdout.splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12 or not f[11].strip():
            continue
        lines.setdefault(tuple(f[1:5]), []).append(f)
    out: list[Observation] = []
    for words in lines.values():
        text = " ".join(w[11] for w in words).strip()
        if not text:
            continue
        x0 = min(int(w[6]) for w in words)
        y0 = min(int(w[7]) for w in words)
        x1 = max(int(w[6]) + int(w[8]) for w in words)
        y1 = max(int(w[7]) + int(w[9]) for w in words)
        conf = [float(w[10]) for w in words if float(w[10]) >= 0]
        out.append(
            Observation(
                text=text,
                confidence=(sum(conf) / len(conf) / 100.0) if conf else 0.0,
                x0=x0 / width,
                y0=y0 / height,
                x1=x1 / width,
                y1=y1 / height,
            )
        )
    return tuple(sorted(out, key=lambda o: (round(o.y0, 3), o.x0)))


_BACKENDS = (("vision", _vision), ("tesseract", _tesseract))


def available_backends() -> list[str]:
    names = []
    try:
        import Vision  # noqa: F401

        names.append("vision")
    except Exception:
        pass
    if shutil.which("tesseract"):
        names.append("tesseract")
    return names


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _key(image: Path) -> str:
    return hashlib.sha256(image.read_bytes()).hexdigest()[:24]


def _cache_path(image: Path) -> Path:
    return CACHE_DIR / f"{_key(image)}.json"


def read_image(image: Path, *, cache_dir: Path | None = None) -> Page:
    """OCR one image, honouring `VITERA_OCR_MODE`."""
    global CACHE_DIR
    if cache_dir is not None:
        CACHE_DIR = cache_dir
    mode = ocr_mode()
    cached = _cache_path(image)

    if mode == "cache" or (mode == "auto" and cached.exists()):
        if not cached.exists():
            raise OCRUnavailable(
                f"VITERA_OCR_MODE=cache dan tidak ada rekaman untuk {image.name}. "
                "Jalankan sekali dengan VITERA_OCR_MODE=live pada mesin yang "
                "punya mesin OCR untuk merekamnya."
            )
        blob = json.loads(cached.read_text(encoding="utf-8"))
        return Page(
            index=int(blob["index"]),
            engine=f"{blob['engine']} (cache)",
            observations=tuple(Observation.from_json(o) for o in blob["observations"]),
        )

    last: Exception | None = None
    for name, fn in _BACKENDS:
        if name not in available_backends():
            continue
        try:
            obs = fn(image)
        except Exception as exc:  # try the next backend before giving up
            last = exc
            continue
        page = Page(index=0, engine=name, observations=obs)
        _write_cache(cached, page)
        return page

    raise OCRUnavailable(
        "tidak ada mesin OCR yang tersedia (vision / tesseract) dan tidak ada "
        f"rekaman cache untuk {image.name}"
        + (f"; kesalahan terakhir: {last}" if last else "")
    )


def _write_cache(path: Path, page: Page) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "index": page.index,
                "engine": page.engine,
                "observations": [o.to_json() for o in page.observations],
            },
            indent=1,
        ),
        encoding="utf-8",
    )


def read(path: Path, *, work_dir: Path | None = None, dpi: int = 200) -> list[Page]:
    """OCR a PDF or an image. Returns one `Page` per page, in order."""
    if path.suffix.lower() == ".pdf":
        work = work_dir or (path.parent / f".{path.stem}_pages")
        images = rasterise(path, work, dpi=dpi)
    else:
        images = [path]
    pages = []
    for i, img in enumerate(images):
        page = read_image(img)
        pages.append(Page(index=i, engine=page.engine, observations=page.observations))
    return pages


__all__ = [
    "CACHE_DIR",
    "OCRUnavailable",
    "Observation",
    "Page",
    "available_backends",
    "ocr_mode",
    "rasterise",
    "read",
    "read_image",
]
