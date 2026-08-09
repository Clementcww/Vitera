"""`make fpk`, `make intake`, `make intake-eval` — the paper path end to end.

    render   corpus            -> FPK PDFs
    scan     a PDF or image    -> fields, confidences, validation gate
    correct  a scanned FPK     -> pipeline -> DRAF FPK with the findings
    eval     render + degrade  -> measured OCR accuracy per scan profile

`correct` is the one that answers the question the rest of the package exists
for: a hospital hands us paper, and gets back paper a koder can act on, with
every figure traceable to the grouper and every finding to a verbatim span.

Reproducibility works exactly as it does for the LLM layer. `VITERA_OCR_MODE`
is `auto` by default: a real engine runs if the machine has one, and its output
is recorded to `data/generated/ocr_cache/`. Set it to `cache` and the same
commands replay from that recording, so a judge with no OCR engine still gets
byte-identical output.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from vitera import config
from vitera.generator.corpus import claim_from_dict, episode_from_dict, load_jsonl
from vitera.intake import degrade as deg
from vitera.intake import extract as ex
from vitera.intake import scan as sc
from vitera.intake import validate as val
from vitera.intake.correct import run_corrections, write_corrected_fpk
from vitera.intake.form import FPKForm, format_idr
from vitera.intake.render import forms_for_cohort, render_fpk

DEFAULT_DATA = Path("data/generated")
DEFAULT_OUT = Path("results/intake")


def _site_meta() -> dict[str, dict[str, str]]:
    return {s["id"]: {"region": s["region"]} for s in config.sites()["sites"]}


def _cohort(data: Path, split: str) -> list[tuple[Any, Any]]:
    rows = load_jsonl(data / f"{split}.jsonl")
    return [
        (episode_from_dict(r["episode"]), claim_from_dict(r["claim"])) for r in rows
    ]


def _forms(data: Path, split: str) -> list[FPKForm]:
    return forms_for_cohort(_cohort(data, split), site_meta=_site_meta())


_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff")


def _pages_from(path: Path, *, work: Path, dpi: int) -> list[sc.Page]:
    """A PDF, a single image, or a directory of page images in name order.

    The directory form is what a hospital scanner actually produces, and it is
    what `data/intake/` ships: committed page images mean the OCR cache key —
    the hash of the image bytes — is stable across machines, so `make intake`
    replays for a judge who has no OCR engine installed.
    """
    if path.is_dir():
        images = sorted(
            p for p in path.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES
        )
        if not images:
            raise SystemExit(f"tidak ada berkas gambar di {path}")
    elif path.suffix.lower() == ".pdf":
        images = sc.rasterise(path, work, dpi=dpi)
    else:
        images = [path]
    out = []
    for i, img in enumerate(images):
        page = sc.read_image(img)
        out.append(sc.Page(index=i, engine=page.engine, observations=page.observations))
    return out


# ---------------------------------------------------------------------------


def cmd_render(a: argparse.Namespace) -> None:
    forms = _forms(a.data, a.split)[: a.n]
    a.out.mkdir(parents=True, exist_ok=True)
    for f in forms:
        name = f"FPK_{f.nama_ppk.split()[-1]}_{f.bulan_pelayanan.replace('/ ', '')}"
        path = render_fpk(f, a.out / f"{name}.pdf")
        print(
            f"  {path}  {f.jumlah_kasus} kasus  {f.jumlah_hari} hari  "
            f"{format_idr(f.jumlah_biaya)}"
            + (f"  ({len(f.ungroupable)} UNGROUPABLE)" if f.ungroupable else "")
        )
    print(f"\n{len(forms)} FPK ditulis ke {a.out}")


def cmd_scan(a: argparse.Namespace) -> None:
    t0 = time.monotonic()
    pages = _pages_from(a.path, work=a.out / ".pages", dpi=a.dpi)
    x = ex.extract(pages)
    index = val.build_index(load_jsonl(a.data / f"{a.split}.jsonl"))
    result = val.validate(x, index)
    elapsed = time.monotonic() - t0

    print(f"OCR: {x.engine}, {x.pages} halaman, {elapsed:.1f} s\n")
    for name, f in sorted(x.fields.items()):
        mark = "?" if f.suspect else " "
        print(f" {mark} {name:20} {f.confidence:.2f}  {f.value}")
    for name in x.missing:
        print(f" ! {name:20} tidak terbaca")

    print(f"\nrincian: {len(x.lines)} baris, {result.rows_complete:.0%} lengkap")
    print(f"jumlah pada formulir: {x.totals}")
    print(f"\ngerbang validasi: {'LULUS' if result.passed else 'DITAHAN'}")
    for fail in result.failures:
        print(f"  [{fail.severity:16}] {fail.check:24} {fail.detail}")

    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "scan.json").write_text(
        json.dumps(result.summary(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nwrote {a.out / 'scan.json'}")
    if not result.passed:
        raise SystemExit("berkas ditahan di gerbang validasi; tidak diteruskan")


def cmd_correct(a: argparse.Namespace) -> None:
    """The full loop. Renders a batch, scans it back, corrects it."""
    a.out.mkdir(parents=True, exist_ok=True)
    forms = _forms(a.data, a.split)
    form = forms[0] if a.path is None else None

    if a.path is None:
        assert form is not None
        source = render_fpk(form, a.out / "fpk_diajukan.pdf")
        print(f"FPK diajukan   : {source}")
        if a.profile != "clean":
            images = sc.rasterise(source, a.out / ".pages", dpi=a.dpi)
            profile = deg.BY_NAME[a.profile]
            source_images = [
                deg.degrade(p, a.out / ".scanned" / p.name, profile, seed=a.seed + i)
                for i, p in enumerate(images)
            ]
            print(f"disimulasikan  : {profile.name} — {profile.description}")
            pages = [
                sc.Page(
                    index=i,
                    engine=sc.read_image(p).engine,
                    observations=sc.read_image(p).observations,
                )
                for i, p in enumerate(source_images)
            ]
        else:
            pages = _pages_from(source, work=a.out / ".pages", dpi=a.dpi)
    else:
        pages = _pages_from(a.path, work=a.out / ".pages", dpi=a.dpi)

    x = ex.extract(pages)
    rows = load_jsonl(a.data / f"{a.split}.jsonl")
    index = val.build_index(rows)
    intake = val.validate(x, index)

    print(f"dibaca         : {x.engine}, {len(x.lines)} baris rincian")
    print(f"gerbang        : {'LULUS' if intake.passed else 'DITAHAN'}")
    if not intake.passed:
        for f in intake.blocking:
            print(f"  [blocking] {f.check}: {f.detail}")
        raise SystemExit("berkas ditahan di gerbang validasi (aturan arsitektur 4)")

    if form is None:
        # Rebuild the batch from the SEPs that were actually read, so the
        # corrected form covers exactly what came off the paper.
        pairs = [index[s] for s in intake.matched]
        form = forms_for_cohort([(ep, cl) for ep, cl in pairs], site_meta=_site_meta())[
            0
        ]

    run = run_corrections(intake, index, model_dir=a.model, use_llm=a.llm)
    out = write_corrected_fpk(form, intake, run, a.out / "fpk_draf_perbaikan.pdf")

    delta = run.total_after - run.total_before
    arah = "naik" if delta >= 0 else "turun"
    print(f"\nepisode        : {len(run.corrections)} ({len(run.errors)} gagal)")
    print(f"temuan         : {len(run.findings)}")
    print(f"diajukan       : {format_idr(run.total_before)}")
    print(
        f"draf perbaikan : {format_idr(run.total_after)}  "
        f"({arah} {format_idr(abs(delta))})"
    )
    print(
        f"bersyarat DPJP : {format_idr(run.total_if_confirmed - run.total_after)} "
        "(tidak ditotalkan)"
    )
    if run.advisory:
        print("mode           : ADVISORY — lapisan model tidak aktif")
    print(f"\nDRAF ditulis   : {out}")
    print("Tidak ada yang dikirim ke BPJS. Draf berlaku setelah ditandatangani.")

    (a.out / "correction.json").write_text(
        json.dumps(
            {
                "intake": intake.summary(),
                "episodes": len(run.corrections),
                "findings": len(run.findings),
                "total_before_idr": run.total_before,
                "total_after_idr": run.total_after,
                "total_if_confirmed_idr": run.total_if_confirmed,
                "advisory": run.advisory,
                "errors": run.errors,
                "source": "grouper INA-CBG",
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------


_CELLS = ("sep_number", "no_kartu", "tanggal_masuk", "hari", "cbg_code", "biaya_idr")


def _truth(form: FPKForm) -> dict[str, dict[str, Any]]:
    return {
        ln.sep_number: {
            "sep_number": ln.sep_number,
            "no_kartu": ln.no_kartu,
            "tanggal_masuk": ln.tanggal_masuk,
            "hari": ln.hari,
            "cbg_code": ln.cbg_code,
            "biaya_idr": ln.biaya_idr,
        }
        for ln in form.lines
    }


def _score(form: FPKForm, x: ex.ExtractedFPK) -> dict[str, Any]:
    """Cell-level accuracy, and the three failure modes kept apart.

    `wrong` is the one that matters. A cell the extractor refused to read is a
    cell the validation gate will stop; a cell it read incorrectly is one that
    could reach a claim, so the two are never added together.
    """
    truth = _truth(form)
    correct = wrong = unread = 0
    misses: list[dict[str, Any]] = []
    for ln in x.lines:
        t = truth.get(ln.sep_number or "")
        if t is None:
            wrong += len(_CELLS)
            misses.append({"sep": ln.sep_number, "field": "row", "read": "unmatched"})
            continue
        for c in _CELLS:
            got, want = getattr(ln, c), t[c]
            if got is None:
                unread += 1
            elif got == want:
                correct += 1
            else:
                wrong += 1
                misses.append(
                    {
                        "sep": ln.sep_number,
                        "field": c,
                        "want": str(want),
                        "got": str(got),
                    }
                )
    total = len(truth) * len(_CELLS)
    return {
        "rows_expected": len(truth),
        "rows_read": len(x.lines),
        "cells_expected": total,
        "cells_correct": correct,
        "cells_wrong": wrong,
        "cells_unread": unread,
        "cells_never_reached": total - (correct + wrong + unread),
        "cell_accuracy": round(correct / total, 4) if total else 0.0,
        "cell_error_rate": round(wrong / total, 4) if total else 0.0,
        "header_fields_read": len(x.fields),
        "header_fields_missing": list(x.missing),
        "examples": misses[:8],
    }


def cmd_eval(a: argparse.Namespace) -> None:
    forms = _forms(a.data, a.split)[: a.n]
    a.out.mkdir(parents=True, exist_ok=True)
    work = a.out / ".eval"
    profiles = [deg.BY_NAME[p] for p in a.profiles]

    results: dict[str, Any] = {
        "seed": a.seed,
        "dpi": a.dpi,
        "engine": None,
        "forms": len(forms),
        "profiles": {},
    }
    for profile in profiles:
        totals = dict.fromkeys(
            (
                "cells_expected",
                "cells_correct",
                "cells_wrong",
                "cells_unread",
                "cells_never_reached",
                "header_missing",
            ),
            0,
        )
        per_form: list[dict[str, Any]] = []
        for i, form in enumerate(forms):
            src = render_fpk(form, work / f"form{i}.pdf")
            images = sc.rasterise(src, work / f"form{i}_pages", dpi=a.dpi)
            if profile.name != "clean":
                images = [
                    deg.degrade(
                        p,
                        work / f"form{i}_{profile.name}" / p.name,
                        profile,
                        seed=a.seed + j,
                    )
                    for j, p in enumerate(images)
                ]
            pages = []
            for j, img in enumerate(images):
                page = sc.read_image(img)
                results["engine"] = page.engine
                pages.append(
                    sc.Page(index=j, engine=page.engine, observations=page.observations)
                )
            s = _score(form, ex.extract(pages))
            for k in totals:
                if k == "header_missing":
                    totals[k] += len(s["header_fields_missing"])
                else:
                    totals[k] += int(s[k])
            per_form.append(s)

        n = max(1, totals["cells_expected"])
        agg: dict[str, Any] = {
            "description": profile.description,
            **totals,
            "cell_accuracy": round(totals["cells_correct"] / n, 4),
            "cell_error_rate": round(totals["cells_wrong"] / n, 4),
            "cell_unread_rate": round(totals["cells_unread"] / n, 4),
            "per_form": per_form,
        }
        results["profiles"][profile.name] = agg
        print(
            f"  {profile.name:11} accuracy {agg['cell_accuracy']:.3f}   "
            f"salah baca {agg['cell_error_rate']:.3f}   "
            f"tidak terbaca {agg['cell_unread_rate']:.3f}   "
            f"— {profile.description}"
        )

    path = a.out.parent / "intake_ocr.json"
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {path}")


# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(prog="vitera.intake", description=__doc__)
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--split", default="test")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--seed", type=int, default=config.DEFAULT_SEED)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="tulis FPK dari korpus")
    r.add_argument("-n", type=int, default=4)
    r.set_defaults(fn=cmd_render)

    s = sub.add_parser("scan", help="baca FPK terpindai, jalankan gerbang validasi")
    s.add_argument("path", type=Path)
    s.set_defaults(fn=cmd_scan)

    c = sub.add_parser("correct", help="pindai lalu tulis draf FPK perbaikan")
    c.add_argument("path", type=Path, nargs="?", default=None)
    c.add_argument("--model", type=Path, default=Path("models/cross_encoder"))
    c.add_argument("--profile", default="office", choices=list(deg.BY_NAME))
    c.add_argument("--llm", action="store_true", help="nyalakan lapisan prosa")
    c.set_defaults(fn=cmd_correct)

    e = sub.add_parser("eval", help="akurasi OCR terukur per profil pindaian")
    e.add_argument("-n", type=int, default=2)
    e.add_argument("--profiles", nargs="+", default=[x.name for x in deg.PROFILES])
    e.set_defaults(fn=cmd_eval)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
