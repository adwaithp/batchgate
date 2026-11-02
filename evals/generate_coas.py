# ruff: noqa: E501  (HTML templates read better unwrapped)
"""Fictional COA documents with known answers: for trying the reader in the UI, and for evals.

    cd backend && uv run python ../evals/generate_coas.py

Writes evals/coas/ (PDFs, a phone photo and manifest.json). Every document is for the seeded
batch FC-2611-12 (Ferric Chloride, PO-1042 line 1). Before anything is written, each
document's expected decision is checked with the real rules engine against the seeded spec,
so the answers can't drift from the spec. Companies are the seed's fictional ones.
"""

import io
import json
import sys
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import pymupdf
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.models.enums import CoaSource, Decision  # noqa: E402
from app.seed import SPECS, TOLERANCES  # noqa: E402
from app.services.rules.engine import check_batch  # noqa: E402
from app.services.rules.types import (  # noqa: E402
    BatchInput,
    CoaInput,
    ParamSpec,
    ResultInput,
    SpecInput,
)

OUT = Path(__file__).resolve().parent / "coas"
BATCH = "FC-2611-12"


@dataclass
class Row:
    name: str
    limit: str
    result: str
    unit: str
    method: str


@dataclass
class Coa:
    source: CoaSource
    issuer: str
    batch_number: str
    rows: list[Row]
    product_name: str = "Ferric Chloride Solution 40%"
    cas_number: str = "7705-08-0"
    po_reference: str | None = "PO-1042"
    mfg_date: date = date(2026, 10, 29)
    test_date: date = date(2026, 10, 30)
    expiry_date: date = date(2027, 10, 28)


FACTORY = Coa(
    source=CoaSource.FACTORY,
    issuer="Kutch Coastal Chemicals",
    batch_number=BATCH,
    rows=[
        Row("FeCl3 content", "min 40.0", "40.8", "%", "IS 711"),
        Row("Total iron (as Fe)", "min 13.8", "14.0", "%", "IS 711"),
        Row("Free acid (as HCl)", "max 0.5", "0.28", "%", "Titrimetric"),
        Row("Ferrous iron (Fe2+)", "max 0.25", "0.10", "%", "KMnO4 titration"),
        Row("Insoluble matter", "max 0.1", "0.04", "%", "Gravimetric"),
        Row("Specific gravity @ 25 °C", "1.40 - 1.45", "1.43", "", "Hydrometer"),
        Row("Appearance", "Dark brown liquid", "Dark brown liquid", "", "Visual"),
    ],
)

# The lab names the same tests differently, orders its columns differently and tests a day later.
LAB = Coa(
    source=CoaSource.LAB,
    issuer="Northbridge Analytical Labs",
    batch_number=BATCH,
    po_reference=None,
    test_date=date(2026, 10, 31),
    rows=[
        Row("Assay as FeCl3", "≥ 40.0", "40.6", "% w/w", "NAL-WI-112"),
        Row("Fe", "≥ 13.8", "13.95", "% w/w", "NAL-WI-112"),
        Row("Free acidity", "≤ 0.5", "0.30", "% w/w", "NAL-WI-118"),
        Row("Fe(II)", "≤ 0.25", "0.11", "% w/w", "NAL-WI-121"),
        Row("Water insolubles", "≤ 0.10", "0.05", "% w/w", "NAL-WI-130"),
        Row("SG", "1.40 – 1.45", "1.432", "—", "Density meter"),
        Row("Appearance", "Dark brown liquid", "Complies", "—", "Visual"),
    ],
)


def with_row(coa: Coa, name: str, **changes) -> Coa:
    rows = [replace(r, **changes) if r.name == name else r for r in coa.rows]
    return replace(coa, rows=rows)


def without_row(coa: Coa, name: str) -> Coa:
    return replace(coa, rows=[r for r in coa.rows if r.name != name])


@dataclass
class Doc:
    file: str
    coa: Coa
    expect: Decision
    why: str
    look: str = "clean"  # clean | scan (scanned into a PDF) | photo (phone picture, JPEG)


DOCS = [
    Doc("01_factory_clean.pdf", FACTORY, Decision.RELEASE, "Everything in spec."),
    Doc("02_lab_clean.pdf", LAB, Decision.RELEASE, "Agrees with the factory within tolerance."),
    Doc(
        "03_lab_insolubles_out_of_spec.pdf",
        with_row(LAB, "Water insolubles", result="0.16"),
        Decision.HOLD,
        "Lab finds insoluble matter at 0.16 % against max 0.1 %.",
    ),
    Doc(
        "04_factory_scanned.pdf",
        FACTORY,
        Decision.RELEASE,
        "Same values as 01, but a skewed, noisy scan (no text layer).",
        look="scan",
    ),
    Doc(
        "05_factory_assay_w_v.pdf",
        with_row(FACTORY, "FeCl3 content", result="58.4", unit="% w/v", limit="min 56.0 (w/v)"),
        Decision.REVIEW,
        "Assay reported as % w/v; it can't be converted to % w/w without the density.",
    ),
    Doc(
        "06_factory_insolubles_below_detection.pdf",
        with_row(FACTORY, "Insoluble matter", result="< 0.2"),
        Decision.REVIEW,
        "'< 0.2' doesn't prove the value is below the 0.1 % limit.",
    ),
    Doc(
        "07_factory_wrong_batch.pdf",
        replace(FACTORY, batch_number="FC-2611-21"),
        Decision.REVIEW,
        "The COA is for batch FC-2611-21, not FC-2611-12.",
    ),
    Doc(
        "08_factory_missing_ferrous_iron.pdf",
        without_row(FACTORY, "Ferrous iron (Fe2+)"),
        Decision.REVIEW,
        "Ferrous iron, a critical parameter, is not reported.",
    ),
    Doc(
        "09_factory_phone_photo.jpg",
        FACTORY,
        Decision.RELEASE,
        "Same values as 01, photographed at an angle in poor light.",
        look="photo",
    ),
]


# ---- Checking the answers with the real engine ---------------------------------------------


def ferric_spec() -> SpecInput:
    spec = next(s for s in SPECS if s["product"] == "Ferric Chloride")
    return SpecInput(
        product_name="Ferric Chloride",
        cas_number="7705-08-0",
        product_synonyms=["Iron(III) chloride", "FeCl3", "Ferric chloride solution"],
        parameters=[
            ParamSpec(
                id=i,
                name=p["name"],
                rule_type=p["rule_type"],
                low=p["low"],
                high=p["high"],
                unit=p["unit"],
                expected_text=p["expected_text"],
                aliases=p["aliases"],
                critical=p["critical"],
                **TOLERANCES.get(p["name"], {}),
            )
            for i, p in enumerate(spec["parameters"], start=1)
        ],
    )


def coa_input(coa: Coa) -> CoaInput:
    return CoaInput(
        source=coa.source,
        issuer_name=coa.issuer,
        product_name=coa.product_name,
        cas_number=coa.cas_number,
        batch_number=coa.batch_number,
        mfg_date=coa.mfg_date,
        test_date=coa.test_date,
        expiry_date=coa.expiry_date,
        results=[ResultInput(r.name, r.result, r.unit or None) for r in coa.rows],
    )


def engine_decision(doc: Doc) -> tuple[Decision, str]:
    """The decision with this document and the clean COA from the other source."""
    partner = LAB if doc.coa.source == CoaSource.FACTORY else FACTORY
    batch = BatchInput(BATCH, [coa_input(doc.coa), coa_input(partner)])
    result = check_batch(ferric_spec(), batch)
    return result.decision, result.summary


# ---- Rendering -----------------------------------------------------------------------------

CSS = """
* { font-family: sans-serif; color: #1b1b1b; }
h1 { font-size: 15px; margin: 0; }
h2 { font-size: 13px; margin: 10px 0 6px; letter-spacing: 1px; }
p { font-size: 9px; margin: 2px 0; }
table { border-collapse: collapse; width: 100%; margin-top: 8px; }
td, th { font-size: 9px; border: 0.6px solid #555; padding: 3px 4px; text-align: left; }
th { background: #e6e6e6; }
.meta td { border: none; padding: 2px 4px; }
.small { font-size: 8px; color: #444; }
"""


def _fmt(d: date, lab: bool) -> str:
    return d.strftime("%d.%m.%Y") if lab else d.isoformat()


def factory_html(coa: Coa) -> str:
    rows = "".join(
        f"<tr><td>{i}</td><td>{r.name}</td><td>{r.limit}</td><td>{r.result}</td>"
        f"<td>{r.unit or '-'}</td><td>{r.method}</td></tr>"
        for i, r in enumerate(coa.rows, start=1)
    )
    return f"""
<h1>{coa.issuer}</h1>
<p class="small">Plot 14, GIDC Industrial Estate, Bhuj, Gujarat 370001, India</p>
<h2>CERTIFICATE OF ANALYSIS</h2>
<table class="meta">
<tr><td><b>Product</b></td><td>{coa.product_name}</td><td><b>CAS No.</b></td><td>{coa.cas_number}</td></tr>
<tr><td><b>Batch No.</b></td><td>{coa.batch_number}</td><td><b>Customer PO</b></td><td>{coa.po_reference or "-"}</td></tr>
<tr><td><b>Mfg. date</b></td><td>{_fmt(coa.mfg_date, False)}</td><td><b>Date of analysis</b></td><td>{_fmt(coa.test_date, False)}</td></tr>
<tr><td><b>Expiry date</b></td><td>{_fmt(coa.expiry_date, False)}</td><td><b>Pack</b></td><td>IBC, 1250 kg</td></tr>
</table>
<table>
<tr><th>S.No</th><th>Test parameter</th><th>Specification</th><th>Result</th><th>Unit</th><th>Method</th></tr>
{rows}
</table>
<p style="margin-top:10px"><b>Remarks:</b> The material complies with the specification.</p>
<p style="margin-top:24px">Checked by: Production Chemist &nbsp;&nbsp;&nbsp; Approved by: QC Manager</p>
"""


def lab_html(coa: Coa) -> str:
    rows = "".join(
        f"<tr><td>{r.name}</td><td>{r.method}</td><td>{r.unit or '—'}</td><td><b>{r.result}</b></td>"
        f"<td>{r.limit}</td></tr>"
        for r in coa.rows
    )
    return f"""
<h1>{coa.issuer}</h1>
<p class="small">Independent testing laboratory · Gachibowli, Hyderabad 500032, India</p>
<h2>TEST REPORT</h2>
<table class="meta">
<tr><td><b>Report No.</b></td><td>NAL/26/10/4471</td><td><b>Report date</b></td><td>{_fmt(date(2026, 11, 1), True)}</td></tr>
<tr><td><b>Sample</b></td><td>{coa.product_name} (CAS {coa.cas_number})</td><td><b>Lot No.</b></td><td>{coa.batch_number}</td></tr>
<tr><td><b>Manufacturer</b></td><td>Kutch Coastal Chemicals</td><td><b>Date of mfg.</b></td><td>{_fmt(coa.mfg_date, True)}</td></tr>
<tr><td><b>Tested on</b></td><td>{_fmt(coa.test_date, True)}</td><td><b>Best before</b></td><td>{_fmt(coa.expiry_date, True)}</td></tr>
</table>
<table>
<tr><th>Parameter</th><th>Test method</th><th>Units</th><th>Result</th><th>Limits</th></tr>
{rows}
</table>
<p class="small" style="margin-top:10px">Results relate only to the sample as received.
This report shall not be reproduced except in full without written approval of the laboratory.</p>
<p style="margin-top:24px">Authorised signatory, Chemical Testing</p>
"""


def render_pdf(coa: Coa) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4
    html = factory_html(coa) if coa.source == CoaSource.FACTORY else lab_html(coa)
    page.insert_htmlbox(pymupdf.Rect(48, 48, 547, 794), html, css=CSS)
    return doc.tobytes(deflate=True)


def _raster(pdf: bytes, dpi: int) -> Image.Image:
    page = pymupdf.open(stream=pdf, filetype="pdf")[0]
    pix = page.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def scanned(pdf: bytes) -> bytes:
    """A skewed, slightly blurred and noisy greyscale scan, as an image-only PDF."""
    img = _raster(pdf, 120).convert("L")
    img = img.rotate(1.3, resample=Image.BICUBIC, expand=True, fillcolor=255)
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    noise = Image.effect_noise(img.size, 28)
    img = Image.blend(img, noise, 0.12)
    img = ImageEnhance.Contrast(img).enhance(0.85)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=55)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=buf.getvalue())
    return doc.tobytes(deflate=True)


def photo(pdf: bytes) -> bytes:
    """A phone photo: tilted page on a desk, warm uneven light, soft focus."""
    page = _raster(pdf, 110)
    page = page.rotate(-3.5, resample=Image.BICUBIC, expand=True, fillcolor=(120, 104, 86))
    w, h = page.size
    canvas = Image.new("RGB", (w + 80, h + 80), (120, 104, 86))
    canvas.paste(page, (40, 30))
    light = ImageOps.invert(Image.radial_gradient("L")).resize(canvas.size)  # bright centre
    canvas = Image.composite(canvas, ImageEnhance.Brightness(canvas).enhance(0.6), light)
    canvas = canvas.filter(ImageFilter.GaussianBlur(0.9))
    tint = Image.new("RGB", canvas.size, (255, 236, 200))
    canvas = Image.blend(canvas, tint, 0.08)
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=70)
    return buf.getvalue()


# ---- Main ----------------------------------------------------------------------------------


def main() -> None:
    problems = []
    for doc in DOCS:
        decision, summary = engine_decision(doc)
        if decision != doc.expect:
            problems.append(f"{doc.file}: expected {doc.expect.value}, engine says {summary}")
    if problems:
        sys.exit("Expected answers disagree with the engine:\n  " + "\n  ".join(problems))

    OUT.mkdir(exist_ok=True)
    manifest = []
    for doc in DOCS:
        pdf = render_pdf(doc.coa)
        if doc.look == "scan":
            pdf = scanned(pdf)
        elif doc.look == "photo":
            pdf = photo(pdf)
        (OUT / doc.file).write_bytes(pdf)
        c = doc.coa
        manifest.append(
            {
                "file": doc.file,
                "upload_to": {"batch": BATCH, "source": c.source.value},
                "look": doc.look,
                "expected_decision": doc.expect.value,
                "why": doc.why,
                "truth": {
                    "product_name": c.product_name,
                    "cas_number": c.cas_number,
                    "batch_number": c.batch_number,
                    "po_reference": c.po_reference,
                    "mfg_date": c.mfg_date.isoformat(),
                    "test_date": c.test_date.isoformat(),
                    "expiry_date": c.expiry_date.isoformat(),
                    "results": [
                        {"name_as_written": r.name, "raw_value": r.result, "unit": r.unit or None}
                        for r in c.rows
                    ],
                },
            }
        )
        print(f"{doc.file:45} {c.source.value:8} {doc.expect.value:8} {doc.why}")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"\n{len(DOCS)} documents in {OUT}")


if __name__ == "__main__":
    main()
