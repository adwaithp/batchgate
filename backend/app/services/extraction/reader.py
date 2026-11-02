"""Claude reads a COA (PDF or image) and returns what is printed on it. Nothing more.

It transcribes; it never converts units, compares against limits or decides anything. That is
the rules engine's job. No database here, so evals can call read_coa() directly.
"""

import base64
from datetime import date
from pathlib import Path

import anthropic
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.services.rules.types import ParamSpec


class ExtractedRow(BaseModel):
    name_as_written: str
    raw_value: str
    unit: str | None
    method: str | None
    limit_as_printed: str | None  # helps keep the result and limit columns apart; not used
    confidence: float
    parameter_id: int | None


class CoaExtraction(BaseModel):
    is_coa: bool
    issuer_name: str | None
    product_name: str | None
    cas_number: str | None
    batch_number: str | None
    po_reference: str | None
    mfg_date: date | None
    test_date: date | None
    expiry_date: date | None
    results: list[ExtractedRow]
    warnings: list[str]


class ExtractionFailed(Exception):
    """The document could not be read. The message is shown to the person who uploaded it."""


SYSTEM_PROMPT = """\
You transcribe certificates of analysis (COAs) for specialty chemical batches. A quality team \
compares your transcription against the customer's spec with separate, deterministic code, so \
your only job is to report exactly what the document says.

Rules:
- Copy each test result exactly as printed, including signs and words: "< 0.01", "ND", \
"Complies", "131.0 - 133.5", "Clear, colourless liquid". Do not round, convert units or \
reformat numbers.
- Take the value from the result (observed / found / actual) column, never from the \
specification, limit or typical column. Put the printed limit in limit_as_printed.
- Put the unit in unit when it is printed in a unit column or after the value; leave it null \
if no unit is printed. Do not guess units.
- Only list tests that are actually printed. Never fill in a value that is not on the page.
- Header fields: copy the product name, CAS number, batch/lot number and PO reference as \
printed. Give dates as YYYY-MM-DD; use null if a date is missing or its day/month order is \
ambiguous (for example 03/04/2026 with no other clue).
- If a value is unreadable, still list the row with your best reading and a low confidence.
- Add a warning for anything a reviewer should know: rotated or blurred pages, handwritten \
corrections, more than one batch on the document, values you could not read, results that \
look like they belong to a different product.
- If the document is not a certificate of analysis, set is_coa to false.

confidence (per row) is how sure you are that name, value and unit are transcribed correctly:
- 1.0: printed clearly, no doubt about the column.
- about 0.7: partly legible, smudged, or unclear which column the value is in.
- 0.5 or lower: a guess.

parameter_id: the user lists the spec parameters for this batch. If a row clearly measures one \
of them (names often differ: "Fe content" vs "Iron (as Fe)"), give its id; otherwise null. \
Never change a row's name or value to fit the spec."""


def _parameter_list(params: list[ParamSpec]) -> str:
    if not params:
        return "No spec is linked to this batch yet; set parameter_id to null for every row."
    lines = []
    for p in params:
        extra = f" (also called: {', '.join(p.aliases)})" if p.aliases else ""
        unit = f" [{p.unit}]" if p.unit else ""
        lines.append(f"- id {p.id}: {p.name}{extra}{unit}")
    return "Spec parameters for this batch:\n" + "\n".join(lines)


def _file_block(path: Path, content_type: str) -> dict:
    data = base64.standard_b64encode(path.read_bytes()).decode()
    kind = "document" if content_type == "application/pdf" else "image"
    return {"type": kind, "source": {"type": "base64", "media_type": content_type, "data": data}}


def read_coa(
    path: Path,
    content_type: str,
    params: list[ParamSpec],
    *,
    client: anthropic.Anthropic | None = None,
) -> CoaExtraction:
    settings = get_settings()
    client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=180)
    try:
        response = client.beta.messages.parse(
            model=settings.extraction_model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        _file_block(path, content_type),
                        {
                            "type": "text",
                            "text": _parameter_list(params) + "\n\nTranscribe this COA.",
                        },
                    ],
                }
            ],
            output_format=CoaExtraction,
            output_config={"effort": "medium"},
            # On a safety decline, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
        raise ExtractionFailed("Couldn't reach Claude. Try again later.") from e
    except anthropic.RateLimitError as e:
        raise ExtractionFailed("Claude is busy right now. Try again in a minute.") from e
    except anthropic.BadRequestError as e:
        raise ExtractionFailed(f"Claude couldn't open this file ({e.message}).") from e
    except anthropic.APIStatusError as e:
        raise ExtractionFailed(f"Claude returned an error ({e.status_code}).") from e
    except ValidationError as e:
        raise ExtractionFailed("Claude's answer was not in the expected shape.") from e

    if response.stop_reason == "refusal":
        raise ExtractionFailed("Claude declined to read this document.")
    if response.stop_reason == "max_tokens":
        raise ExtractionFailed("The COA is too long to read in one go.")
    if response.parsed_output is None:
        raise ExtractionFailed("Claude's answer was not in the expected shape.")
    return response.parsed_output
