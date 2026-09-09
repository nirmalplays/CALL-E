"""CLI helper for the readback demo.

--dry-run renders the fixture locally (no server, no call) — use it to check
how a script reads before recording. Without --dry-run it places a real call
through the running app (POST /demo/readback-call), so the pending
confirmation and the later webhook resolution share the same in-memory store
— see app.py's docstring for why that has to be one process.

Usage:
    python demo_call.py demo-misread-dose --dry-run
    python demo_call.py demo-misread-dose --phone +91XXXXXXXXXX   # requires: uvicorn app:app --reload
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

import env_config as cfg
from medai_readback.readback import READBACK_RESULT_SCHEMA, build_readback_task
from ocr.main import available_scan_ids, extract_prescription


def preview(scan_id: str) -> None:
    try:
        scan = extract_prescription(scan_id)
    except KeyError as exc:
        print(f"[ERROR] {exc}. Known scan ids: {', '.join(available_scan_ids())}")
        sys.exit(1)

    task = build_readback_task(scan["patient_name"], scan["medications"])
    print("=" * 60)
    print(f"  {scan_id} — {scan['patient_name']} ({len(scan['medications'])} medications)")
    print("=" * 60)
    print(task)
    print(json.dumps({"result_schema": READBACK_RESULT_SCHEMA}, indent=2))


def place_call(scan_id: str, phone: str, language: str, server_url: str) -> None:
    resp = httpx.post(
        f"{server_url}/demo/readback-call",
        json={"scan_id": scan_id, "phone": phone, "language_preference": language},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        print(f"[ERROR] {body['error']}. Known scan ids: {body.get('known_scan_ids')}")
        sys.exit(1)
    if "fallback" in body:
        print(f"[FALLBACK] {body['language_preference']} is not a supported locale yet.")
        print(f"           Supported: {body['supported_locales']}")
        print("           No call was placed — this would route to dashboard staff review.")
        return

    print(f"[CALL PLACED] call_id={body['call_id']}  calle={body['calle']}")
    print("Your phone should ring shortly. Watch the confirmation land at:")
    print(f"    {server_url}/demo/confirmations")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "scan_id", nargs="?", default="demo-clean",
        help=f"one of: {', '.join(available_scan_ids())}",
    )
    parser.add_argument("--phone", default=None, help="E.164 number; defaults to TEST_PHONE")
    parser.add_argument("--language", default="en-IN", help="patient's language_preference, e.g. en-IN, hi-IN")
    parser.add_argument("--dry-run", action="store_true", help="print the task locally, place no call")
    parser.add_argument("--server-url", default="http://127.0.0.1:8000", help="running app.py address")
    args = parser.parse_args()

    if args.dry_run:
        preview(args.scan_id)
        return

    phone = cfg.require("TEST_PHONE", args.phone or cfg.TEST_PHONE)
    place_call(args.scan_id, phone, args.language, args.server_url)


if __name__ == "__main__":
    main()
