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
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(value).strip()]


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
                website_score = int(website_score)
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

        return cls(
            company_name=str(company_name).strip(),
            industry=str(industry).strip(),
            location=str(_first_present(data, "location", "city", default="")).strip(),
            website=_first_present(data, "website", "url"),
            email=_first_present(data, "email", "businessEmail"),
            pain_points=_normalize_list(_first_present(data, "painPoints", "pain_points", "issues")),
            website_score=website_score,
            company_size=_first_present(data, "companySize", "company_size"),
            extra_context={key: value for key, value in data.items() if key not in known_keys},
        )

    def display_location(self) -> str:
        return self.location or "your local market"

    def display_website(self) -> str:
        return self.website or "no public website found"
