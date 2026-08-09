"""Export one intake run for the workbench — `make ui-intake`.

Same contract as `api/export.py`: the UI renders what the pipeline produced and
recomputes nothing. It applies with more force here, because the screen is
about to draw boxes on a photograph and claim the machine read a value out of
that exact rectangle. If the browser were re-deriving any of it, that claim
would be decoration.

So everything the scan view shows is written here, from the run:

    pages          the scanned images, copied next to the bundle, with the
                   page size the boxes are normalised against
    observations   every recognised line with its box and confidence, INCLUDING
                   the ones no field used. A view that only draws the boxes we
                   liked would hide the reads we got wrong.
    fields         the extracted values, each with the box it came from, so a
                   koder can click a value and see where on the paper it was
    gate           the validation result, verbatim, failures and all
    correction     what the pipeline then found, and the grouper's two figures

The images are copied rather than linked. The workbench is served as a static
bundle with no server of its own; a path into `data/intake/` would 404 the
moment anyone opened `dist/` from somewhere else.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from vitera import config
from vitera.generator.corpus import load_jsonl
from vitera.intake import degrade as deg
from vitera.intake import extract as ex
from vitera.intake import scan as sc
from vitera.intake import validate as val
from vitera.intake.correct import CorrectionRun, run_corrections
from vitera.intake.form import FPKForm

DEFAULT_OUT = Path("src/vitera/ui/public/data/intake.json")
DEFAULT_SCAN = Path("data/intake/scan_rs009_maret2026")


def _page_json(page: sc.Page, src: Path, dst_dir: Path) -> dict[str, Any]:
    from PIL import Image

    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        shutil.copyfile(src, dst)
    with Image.open(src) as im:
        w, h = im.size
    return {
        "index": page.index,
        "src": f"./data/scan/{src.name}",
        "w": w,
        "h": h,
        # Short keys: there are a few hundred of these per page and the file is
        # fetched on every load.
        "obs": [
            {
                "t": o.text,
                "c": round(o.confidence, 3),
                "x": round(o.x0, 5),
                "y": round(o.y0, 5),
                "w": round(o.x1 - o.x0, 5),
                "h": round(o.y1 - o.y0, 5),
            }
            for o in page.observations
        ],
    }


def _fields_json(x: ex.ExtractedFPK) -> list[dict[str, Any]]:
    return [
        {
            "name": f.name,
            "value": f.value,
            "confidence": round(f.confidence, 3),
            "anchor_similarity": f.anchor_similarity,
            "suspect": f.suspect,
            "page": f.page,
            "bbox": [round(v, 5) for v in f.bbox],
        }
        for _, f in sorted(x.fields.items())
    ]


def _lines_json(x: ex.ExtractedFPK, matched: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "index": ln.index,
            "sep": ln.sep_number,
            "episode_id": matched.get(ln.sep_number or ""),
            "nama": ln.nama,
            "kartu": ln.no_kartu,
            "tanggal": ln.tanggal_masuk.isoformat() if ln.tanggal_masuk else None,
            "hari": ln.hari,
            "cbg": ln.cbg_code,
            "biaya_idr": ln.biaya_idr,
            "confidence": round(ln.confidence, 3),
            # Which cells the reader could not get. The screen marks these
            # rather than leaving a blank that reads as a zero.
            "unread": [
                k
                for k, v in (
                    ("kartu", ln.no_kartu),
                    ("tanggal", ln.tanggal_masuk),
                    ("hari", ln.hari),
                    ("cbg", ln.cbg_code),
                    ("biaya", ln.biaya_idr),
                )
                if v is None
            ],
        }
        for ln in x.lines
    ]


def _correction_json(run: CorrectionRun) -> dict[str, Any]:
    return {
        "episodes": len(run.corrections),
        "findings_count": len(run.findings),
        "advisory": run.advisory,
        "errors": run.errors,
        # Rule 7 — every one of these came from `Grouper`, via
        # `export.money_view`, which is the same call the queue screen renders.
        "total_before_idr": run.total_before,
        "total_after_idr": run.total_after,
        "total_if_confirmed_idr": run.total_if_confirmed,
        "source": "grouper",
        "corrections": [
            {
                "sep": c.sep_number,
                "episode_id": c.episode_id,
                "cbg_before": c.cbg_before,
                "cbg_after": c.cbg_after,
                "biaya_before": c.biaya_before,
                "biaya_after": c.biaya_after,
                "biaya_if_confirmed": c.biaya_if_confirmed,
                "delta_idr": c.delta,
                "flags": c.flags,
            }
            for c in run.corrections
        ],
        "findings": run.findings,
    }


def _form_json(form: FPKForm) -> dict[str, Any]:
    return {
        "cabang": form.cabang,
        "nama_ppk": form.nama_ppk,
        "kode_ppk": form.kode_ppk,
        "bulan_pelayanan": form.bulan_pelayanan,
        "jenis_pelayanan": form.jenis_pelayanan,
        "kasus": form.jumlah_kasus,
        "hari": form.jumlah_hari,
        "biaya_idr": form.jumlah_biaya,
        "ungroupable": len(form.ungroupable),
    }


def build(
    scan_dir: Path,
    *,
    data: Path,
    split: str,
    model_dir: Path,
    profile: str,
) -> dict[str, Any]:
    images = sorted(
        p for p in scan_dir.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")
    )
    if not images:
        raise SystemExit(f"tidak ada berkas gambar di {scan_dir}")

    pages: list[sc.Page] = []
    srcs: list[Path] = []
    for i, img in enumerate(images):
        page = sc.read_image(img)
        pages.append(
            sc.Page(index=i, engine=page.engine, observations=page.observations)
        )
        srcs.append(img)

    x = ex.extract(pages)
    rows = load_jsonl(data / f"{split}.jsonl")
    index = val.build_index(rows)
    intake = val.validate(x, index)

    correction: dict[str, Any] | None = None
    form_json: dict[str, Any] | None = None
    if intake.passed:
        from vitera.intake.cli import _site_meta
        from vitera.intake.render import forms_for_cohort

        run = run_corrections(intake, index, model_dir=model_dir)
        correction = _correction_json(run)
        pairs = [index[s] for s in intake.matched]
        form_json = _form_json(
            forms_for_cohort([(ep, cl) for ep, cl in pairs], site_meta=_site_meta())[0]
        )

    return {
        "generated": {
            "engine": x.engine,
            "profile": profile,
            "seed": config.DEFAULT_SEED,
            "scan_dir": str(scan_dir),
            "note": (
                "Lembar pindaian sintetis, dibaca oleh mesin OCR lokal. "
                "Kotak pada halaman adalah posisi asli hasil pembacaan, bukan "
                "gambar ulang. Semua angka rupiah berasal dari grouper INA-CBG."
            ),
        },
        "pages": [
            _page_json(p, s, DEFAULT_OUT.parent / "scan")
            for p, s in zip(pages, srcs, strict=True)
        ],
        "fields": _fields_json(x),
        "missing": list(x.missing),
        "totals": x.totals,
        "lines": _lines_json(x, intake.matched),
        "gate": {
            **intake.summary(),
            "failures_detail": [
                {
                    "check": f.check,
                    "detail": f.detail,
                    "severity": f.severity,
                    "subject": f.subject,
                }
                for f in intake.failures
            ],
        },
        "form": form_json,
        "correction": correction,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("scan", type=Path, nargs="?", default=DEFAULT_SCAN)
    p.add_argument("--data", type=Path, default=Path("data/generated"))
    p.add_argument("--split", default="test")
    p.add_argument("--model", type=Path, default=Path("models/cross_encoder"))
    p.add_argument("--profile", default="office", choices=list(deg.BY_NAME))
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = p.parse_args()

    payload = build(
        a.scan, data=a.data, split=a.split, model_dir=a.model, profile=a.profile
    )
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    gate = payload["gate"]
    corr = payload["correction"]
    print(f"engine        : {payload['generated']['engine']}")
    print(f"halaman       : {len(payload['pages'])}")
    print(f"observasi     : {sum(len(p['obs']) for p in payload['pages'])}")
    print(f"kolom terbaca : {len(payload['fields'])} (hilang: {payload['missing']})")
    print(f"baris rincian : {len(payload['lines'])}")
    print(f"gerbang       : {'LULUS' if gate['passed'] else 'DITAHAN'}")
    if corr:
        print(
            f"temuan        : {corr['findings_count']} pada {corr['episodes']} episode"
        )
    print(f"wrote {a.out}  ({a.out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
