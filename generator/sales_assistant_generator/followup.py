"""Follow-up email generator for contacted leads.

Reads the unified leads database, finds leads that have been contacted but not
yet followed up, and generates a personalized follow-up email draft.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from .generator import build_cold_email
from .models import LeadInput


DEFAULT_DELAY_DAYS = 7


def _parse_iso_date(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string into a timezone-aware datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _sender_config() -> tuple[str, str | None]:
    """Read sender identity from environment variables."""
    name = os.environ.get("SENDER_NAME", "Your Name")
    signature = os.environ.get("SENDER_SIGNATURE")
    return name, signature


def _first_pain_point(audit: Dict[str, Any]) -> str:
    """Extract the first concrete pain point from an audit."""
    observed = audit.get("observed_pain_points", []) or audit.get("painPoints", [])
    if observed:
        first = observed[0]
        if isinstance(first, dict):
            return first.get("issue") or first.get("fact", "")
        return first
    return "your website could convert more visitors"


def build_follow_up_email(
    lead: LeadInput,
    audit: Dict[str, Any],
    cold_email: Dict[str, str],
    sender_name: str,
    sender_signature: str | None = None,
) -> Dict[str, str]:
    """Generate a personalized follow-up email draft."""
    company = lead.company_name
    pain_point = _first_pain_point(audit)
    original_subject = cold_email.get("subject", f"Quick idea for {company}'s website")

    subject = f"Re: {original_subject}"
    sign_off = sender_signature or f"Best,\n{sender_name}"

    body = (
        f"Hi {company} team,\n\n"
        f"Quick follow-up on my note about {pain_point.rstrip('.')}.\n\n"
        f"I know inboxes get busy. If improving your online presence is a priority this quarter, "
        f"I can send over the 1-page audit I mentioned — no call required unless you want one.\n\n"
        f"{sign_off}"
    )

    return {"subject": subject, "body": body}


def _is_due(email_sent_at: datetime, delay_days: int, now: datetime) -> bool:
    """Return True if a follow-up is due based on the email sent date."""
    due_at = email_sent_at + timedelta(days=delay_days)
    return due_at.date() <= now.date()


def process_follow_ups(
    input_path: Path,
    output_path: Path,
    delay_days: int = DEFAULT_DELAY_DAYS,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Generate follow-up email drafts for contacted leads."""
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    leads = payload.get("leads", [])
    sender_name, sender_signature = _sender_config()
    now = datetime.now(timezone.utc)

    generated = 0
    skipped = 0

    for item in leads:
        lead_record = item.get("lead", {})
        status = lead_record.get("status")
        email_sent_raw = lead_record.get("emailSentAt")
        follow_up_count = lead_record.get("followUpCount", 0) or 0

        if status != "contacted" or not email_sent_raw:
            skipped += 1
            continue

        email_sent_at = _parse_iso_date(email_sent_raw)
        if not email_sent_at:
            skipped += 1
            continue

        due_at = email_sent_at + timedelta(days=delay_days)
        lead_record["followUpDueAt"] = due_at.isoformat()

        if follow_up_count == 0 and _is_due(email_sent_at, delay_days, now):
            lead_input = LeadInput.from_dict(lead_record)
            audit = item.get("audit", {})
            cold_email = item.get("coldEmail", {})
            item["followUpEmail"] = build_follow_up_email(
                lead_input, audit, cold_email, sender_name, sender_signature
            )
            lead_record["followUpCount"] = 1
            generated += 1
        else:
            skipped += 1

    if not dry_run:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(output_path.parent), suffix=".tmp", prefix=".leads-"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(output_path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    return {"generated": generated, "skipped": skipped, "delayDays": delay_days}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate follow-up email drafts for contacted leads.")
    parser.add_argument("--input", type=Path, default=None, help="Path to unified_leads.json.")
    parser.add_argument("--output", type=Path, default=None, help="Path to write updated unified_leads.json.")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY_DAYS, help="Days after emailSentAt before follow-up is due.")
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing files.")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parents[2]
    input_path = args.input or root_dir / "unified_leads.json"
    output_path = args.output or input_path

    if not input_path.exists():
        print(f"Error: Input file {input_path} not found.", file=sys.stderr)
        return 1

    result = process_follow_ups(input_path, output_path, delay_days=args.delay, dry_run=args.dry_run)
    action = "Would generate" if args.dry_run else "Generated"
    print(f"{action} {result['generated']} follow-up email(s). Skipped {result['skipped']} lead(s).")
    print(f"Follow-up delay: {result['delayDays']} day(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
