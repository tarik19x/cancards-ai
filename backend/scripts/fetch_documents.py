"""Download the cardholder agreements and benefit guides listed in the manifest.

Run from backend/:  python -m scripts.fetch_documents [--force]

Inputs:  data/documents/manifest.json   (hand-maintained, committed)
Outputs: data/documents/pdf/<card_id>/<doc_type>.pdf   (gitignored, dockerignored)
         data/documents/downloads.json   (committed, provenance for every PDF)

A PDF placed by hand at the expected path is kept and recorded as "manual",
so the script's report stays the single list of what the corpus contains.
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict

import httpx

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DOCS_DIR = DATA_DIR / "documents"
PDF_DIR = DOCS_DIR / "pdf"
MANIFEST_PATH = DOCS_DIR / "manifest.json"
REPORT_PATH = DOCS_DIR / "downloads.json"
CARDS_PATH = DATA_DIR / "cards.json"

DocType = Literal["cardholder_agreement", "benefit_guide", "insurance_certificate"]
Status = Literal["downloaded", "manual", "failed"]

DOC_TYPES: frozenset[str] = frozenset(DocType.__args__)  # type: ignore[attr-defined]

# Several bank sites return 403 to httpx's default user agent even for public PDFs.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
# One request every couple of seconds keeps this well clear of any rate limiting.
DELAY_SECONDS = 2.0
# Error and cookie-wall pages are small HTML; a real agreement is never this tiny.
MIN_PDF_BYTES = 10_000


class ManifestEntry(TypedDict):
    card_id: str
    doc_type: DocType
    url: str


class ReportEntry(TypedDict):
    card_id: str
    doc_type: DocType
    url: str
    status: Status
    reason: str | None
    sha256: str | None
    bytes: int | None
    recorded_at: str


def load_manifest() -> list[ManifestEntry]:
    entries: list[ManifestEntry] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    known_cards = {c["card_id"] for c in json.loads(CARDS_PATH.read_text(encoding="utf-8"))}

    # Typos here would silently create orphan documents that no card ever retrieves,
    # so the manifest is rejected outright rather than partially processed.
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for i, entry in enumerate(entries):
        key = (entry["card_id"], entry["doc_type"])
        if entry["card_id"] not in known_cards:
            problems.append(f"entry {i}: unknown card_id {entry['card_id']!r}")
        if entry["doc_type"] not in DOC_TYPES:
            problems.append(f"entry {i}: unknown doc_type {entry['doc_type']!r}")
        if key in seen:
            problems.append(f"entry {i}: duplicate {key}, the second would overwrite the first")
        seen.add(key)
    if problems:
        sys.exit("manifest.json is invalid:\n  " + "\n  ".join(problems))
    return entries


def pdf_path(entry: ManifestEntry) -> Path:
    return PDF_DIR / entry["card_id"] / f"{entry['doc_type']}.pdf"


def record(
    entry: ManifestEntry, status: Status, *, reason: str | None = None, content: bytes | None = None
) -> ReportEntry:
    return {
        "card_id": entry["card_id"],
        "doc_type": entry["doc_type"],
        "url": entry["url"],
        "status": status,
        "reason": reason,
        # The hash lets a later re-run tell whether a bank quietly replaced a document.
        "sha256": hashlib.sha256(content).hexdigest() if content is not None else None,
        "bytes": len(content) if content is not None else None,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def fetch(client: httpx.Client, entry: ManifestEntry) -> ReportEntry:
    try:
        response = client.get(entry["url"])
    except httpx.HTTPError as exc:
        return record(entry, "failed", reason=f"{type(exc).__name__}: {exc}")

    if response.status_code != 200:
        return record(entry, "failed", reason=f"HTTP {response.status_code}")

    # A 200 is not proof of a PDF: banks answer dead links with HTML landing pages.
    content = response.content
    if not content.startswith(b"%PDF-"):
        content_type = response.headers.get("content-type", "unknown")
        return record(entry, "failed", reason=f"not a PDF (content-type {content_type})")
    if len(content) < MIN_PDF_BYTES:
        return record(entry, "failed", reason=f"suspiciously small ({len(content)} bytes)")

    path = pdf_path(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return record(entry, "downloaded", content=content)


def load_previous_report() -> dict[tuple[str, str], ReportEntry]:
    if not REPORT_PATH.exists():
        return {}
    previous: list[ReportEntry] = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    return {(r["card_id"], r["doc_type"]): r for r in previous}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--force", action="store_true", help="re-download files that already exist on disk"
    )
    args = parser.parse_args()

    entries = load_manifest()
    previous = load_previous_report()
    report: list[ReportEntry] = []
    # Several issuers publish one generic agreement shared by multiple cards
    # (RBC, BMO eclipse, PC Financial, Brim). Fetching it once and copying the
    # bytes avoids hammering the same URL every couple of seconds for no reason.
    fetched_by_url: dict[str, ReportEntry] = {}
    requests_made = 0

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30.0) as client:
        for entry in entries:
            path = pdf_path(entry)
            key = (entry["card_id"], entry["doc_type"])

            if path.exists() and not args.force:
                content = path.read_bytes()
                prior = previous.get(key)
                # An unchanged file keeps its earlier record, so a re-run doesn't
                # relabel script downloads. A file with no matching record was
                # dropped in by hand after a failed download.
                digest = hashlib.sha256(content).hexdigest()
                if prior is not None and prior["sha256"] == digest:
                    report.append(prior)
                else:
                    report.append(record(entry, "manual", content=content))
                continue

            if entry["url"] in fetched_by_url:
                shared = fetched_by_url[entry["url"]]
                # Re-save under this card's own path so ingest can still find it
                # by (card_id, doc_type), even though nothing was re-requested.
                if shared["status"] == "downloaded":
                    source = pdf_path(
                        {**entry, "card_id": shared["card_id"], "doc_type": shared["doc_type"]}
                    )
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(source.read_bytes())
                copy: ReportEntry = {
                    **shared,
                    "card_id": entry["card_id"],
                    "doc_type": entry["doc_type"],
                }
                report.append(copy)
                print(
                    f"{copy['status']:<10} {entry['card_id']}/{entry['doc_type']}"
                    f"  (same file as {shared['card_id']}/{shared['doc_type']})"
                )
                continue

            if requests_made > 0:
                time.sleep(DELAY_SECONDS)
            result = fetch(client, entry)
            requests_made += 1
            fetched_by_url[entry["url"]] = result
            report.append(result)
            print(
                f"{result['status']:<10} {entry['card_id']}/{entry['doc_type']}"
                + (f"  ({result['reason']})" if result["reason"] else "")
            )

    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    failed = [r for r in report if r["status"] == "failed"]
    counts = {s: sum(r["status"] == s for r in report) for s in ("downloaded", "manual", "failed")}
    print(f"\n{len(report)} documents: " + ", ".join(f"{n} {s}" for s, n in counts.items()))
    if failed:
        print("\nDownload these by hand, save to the path shown, then re-run:")
        for r in failed:
            print(f"  {r['url']}\n    -> {PDF_DIR / r['card_id'] / (r['doc_type'] + '.pdf')}")


if __name__ == "__main__":
    main()
