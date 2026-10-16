"""Data models and validation helpers for lead personalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _first_present(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def _normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = [str(item).strip()[:300] for item in value[:25] if str(item).strip()]
        return items
    if isinstance(value, str):
        return [part.strip()[:300] for part in value.split(",")[:25] if part.strip()]
    return [str(value).strip()[:300]]


@dataclass
class LeadInput:
    company_name: str
    industry: str
    location: str = ""
    website: Optional[str] = None
    email: Optional[str] = None
    pain_points: List[str] = field(default_factory=list)
    website_score: Optional[int] = None
    company_size: Optional[str] = None
    extra_context: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LeadInput":
        company_name = _first_present(data, "companyName", "company_name", "name")
        industry = _first_present(data, "industry", "category", "businessType", default="local service")

        if not company_name:
            raise ValueError("Lead input must include companyName or company_name.")

        website_score = _first_present(data, "websiteScore", "website_score")
        if website_score is not None:
            try:
                website_score = max(0, min(100, int(website_score)))
            except (TypeError, ValueError):
                website_score = None

        known_keys = {
            "companyName",
            "company_name",
            "name",
            "industry",
            "category",
            "businessType",
            "location",
            "city",
            "website",
            "url",
            "email",
            "businessEmail",
            "painPoints",
            "pain_points",
            "issues",
            "websiteScore",
            "website_score",
            "companySize",
            "company_size",
        }

        raw_website = _first_present(data, "website", "url")
        raw_email = _first_present(data, "email", "businessEmail")
        raw_size = _first_present(data, "companySize", "company_size")

        return cls(
            company_name=str(company_name).strip()[:200],
            industry=str(industry).strip()[:100],
            location=str(_first_present(data, "location", "city", default="")).strip()[:120],
            website=str(raw_website).strip()[:500] if raw_website is not None else None,
            email=str(raw_email).strip()[:254] if raw_email is not None else None,
            pain_points=_normalize_list(_first_present(data, "painPoints", "pain_points", "issues")),
            website_score=website_score,
            company_size=str(raw_size).strip()[:80] if raw_size is not None else None,
            extra_context={
                str(key)[:64]: value
                for key, value in list(data.items())[:30]
                if key not in known_keys
            },
        )

    def display_location(self) -> str:
        return self.location or "your local market"

    def display_website(self) -> str:
        return self.website or "no public website found"
