"""Rule-based personalization engine for the backend MVP."""

from __future__ import annotations

import html
import os
import re
from typing import Any, Dict, List

from .models import LeadInput
from .templates import DEFAULT_PAIN_POINTS, INDUSTRY_PROFILES, PAIN_POINT_LIBRARY


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _profile_for(industry: str) -> Dict[str, object]:
    normalized = industry.lower().strip()
    for key, profile in INDUSTRY_PROFILES.items():
        if key in normalized or normalized in key:
            return profile
    return INDUSTRY_PROFILES["local service"]


def _classify_pain_point(point: str) -> str:
    text = point.lower()
    keyword_map = {
        "booking": ["booking", "book", "schedule", "appointment", "quote form", "form"],
        "mobile": ["mobile", "responsive", "phone layout", "small screen"],
        "cta": ["cta", "call to action", "button", "next step", "conversion", "emergency"],
        "trust": ["trust", "review", "testimonial", "license", "proof", "guarantee"],
        "speed": ["slow", "speed", "performance", "load"],
        "email": ["email", "contact", "inbox"],
    }
    for category, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "cta"


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        marker = item.lower().strip()
        if marker and marker not in seen:
            result.append(item)
            seen.add(marker)
    return result


def _score_label(score: int | None) -> str:
    if score is None:
        return "unknown"
    if score >= 80:
        return "strong"
    if score >= 60:
        return "workable"
    if score >= 40:
        return "needs improvement"
    return "high priority"


def build_audit(lead: LeadInput) -> Dict[str, Any]:
    profile = _profile_for(lead.industry)
    pain_points = lead.pain_points or DEFAULT_PAIN_POINTS
    categories = [_classify_pain_point(point) for point in pain_points]

    bottlenecks = [
        PAIN_POINT_LIBRARY[category]["bottleneck"]
        for category in categories
        if category in PAIN_POINT_LIBRARY
    ]
    automation_ideas = [
        PAIN_POINT_LIBRARY[category]["automation"]
        for category in categories
        if category in PAIN_POINT_LIBRARY
    ]
    quick_wins = [
        PAIN_POINT_LIBRARY[category]["quick_win"]
        for category in categories
        if category in PAIN_POINT_LIBRARY
    ]

    services = ", ".join(profile["services"][:3])  # type: ignore[index]
    score = _score_label(lead.website_score)
    location = lead.display_location()

    return {
        "summary": (
            f"{lead.company_name} appears to be a {lead.industry} business serving {location}. "
            f"The website signal is {score}, and the biggest opportunity is to make it easier "
            f"for customers who need {profile['customer_need']} to take action quickly."
        ),
        "observed_pain_points": pain_points,
        "bottlenecks": _dedupe(bottlenecks),
        "automation_opportunities": _dedupe(automation_ideas),
        "quick_wins": _dedupe(quick_wins),
        "business_impact": [
            "More quote requests from visitors who are already comparing providers.",
            "Less manual back-and-forth because intake details are captured upfront.",
            f"A clearer path from interest to booked work for services like {services}.",
        ],
    }


def build_website_draft(lead: LeadInput) -> Dict[str, Any]:
    profile = _profile_for(lead.industry)
    pain_points = lead.pain_points or DEFAULT_PAIN_POINTS
    categories = _dedupe([_classify_pain_point(point) for point in pain_points])
    services = list(profile["services"])  # type: ignore[arg-type]

    improvement_sections = [
        {
            "title": "Fast request flow",
            "goal": "Turn interested visitors into qualified leads without forcing a phone call.",
            "content": "A short form captures service type, location, urgency, and contact details.",
        },
        {
            "title": "Local trust proof",
            "goal": "Make new visitors feel confident before they reach out.",
            "content": "Reviews, guarantees, licenses, and service-area messaging reduce hesitation.",
        },
    ]

    for category in categories:
        detail = PAIN_POINT_LIBRARY.get(category)
        if detail:
            improvement_sections.append(
                {
                    "title": detail["website_section"].split(" with ")[0].rstrip("."),
                    "goal": detail["quick_win"],
                    "content": detail["website_section"],
                }
            )

    return {
        "page_slug": _slug(f"{lead.company_name} improved landing page"),
        "headline": f"{lead.company_name}: a clearer, faster way to win {lead.industry} leads",
        "subheadline": (
            f"A focused website concept for {lead.display_location()} customers who need "
            f"{profile['customer_need']}."
        ),
        "primary_cta": profile["primary_cta"],
        "secondary_cta": profile["secondary_cta"],
        "recommended_sections": _dedupe_dicts(improvement_sections),
        "service_blocks": [
            {
                "name": service,
                "copy": f"Explain the process, expected response time, and why {lead.company_name} is a safe choice.",
            }
            for service in services
        ],
        "form_fields": ["Name", "Phone", "Email", "Service needed", "Location", "Preferred time"],
    }


def _dedupe_dicts(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    result: List[Dict[str, str]] = []
    for item in items:
        marker = (item.get("title", "") + item.get("content", "")).lower()
        if marker not in seen:
            result.append(item)
            seen.add(marker)
    return result


def _sender_sign_off() -> str:
    """Return the configured sender sign-off for generated emails."""
    name = os.environ.get("SENDER_NAME", "Your Name")
    signature = os.environ.get("SENDER_SIGNATURE")
    if signature:
        return signature
    return f"Best,\n{name}"


def build_cold_email(lead: LeadInput, audit: Dict[str, Any], website_draft: Dict[str, Any]) -> Dict[str, str]:
    first_pain = audit["observed_pain_points"][0] if audit["observed_pain_points"] else "the site could convert more visitors"
    first_pain = str(first_pain).rstrip(".").strip()
    first_win = audit["quick_wins"][0] if audit["quick_wins"] else "make the next step clearer for visitors"
    first_win_sentence = str(first_win).rstrip(".").strip()
    location_phrase = f" in {lead.location}" if lead.location else ""
    sign_off = _sender_sign_off()

    subject = f"Quick idea for {lead.company_name}'s website"
    body = (
        f"Hi {lead.company_name} team,\n\n"
        f"I was looking at your website and noticed one practical opportunity: {first_pain}.\n\n"
        f"For a {lead.industry} business{location_phrase}, that can mean ready-to-buy visitors leave "
        f"before they request help. A good starting point is to "
        f"{first_win_sentence[0].lower() + first_win_sentence[1:]}.\n\n"
        f"I sketched a possible website concept I thought you might be interested in. "
        f"The idea is to remove that friction so more visitors actually reach out, "
        f"instead of leaving to compare elsewhere.\n\n"
        f"If you're interested, I can send over the 1-page audit with the full breakdown.\n\n"
        f"{sign_off}"
    )

    return {"subject": subject, "body": body}


def render_landing_page_html(lead: LeadInput, website_draft: Dict[str, Any]) -> str:
    company = html.escape(lead.company_name)
    headline = html.escape(website_draft["headline"])
    subheadline = html.escape(website_draft["subheadline"])
    primary_cta = html.escape(str(website_draft["primary_cta"]))
    secondary_cta = html.escape(str(website_draft["secondary_cta"]))

    sections = "\n".join(
        f"""
        <section class="panel">
          <h2>{html.escape(section['title'])}</h2>
          <p class="goal">{html.escape(section['goal'])}</p>
          <p>{html.escape(section['content'])}</p>
        </section>
        """
        for section in website_draft["recommended_sections"]
    )

    services = "\n".join(
        f"""
        <article class="service">
          <h3>{html.escape(service['name'])}</h3>
          <p>{html.escape(service['copy'])}</p>
        </article>
        """
        for service in website_draft["service_blocks"]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{company} Website Concept</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #5f6c7b;
      --paper: #f7f8fb;
      --surface: #ffffff;
      --line: #dfe5ec;
      --accent: #0f766e;
      --accent-dark: #115e59;
      --warn: #b45309;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: var(--paper);
      line-height: 1.55;
    }}
    .wrap {{ max-width: 1120px; margin: 0 auto; padding: 28px; }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 24px;
      padding: 18px 0;
      border-bottom: 1px solid var(--line);
    }}
    .brand {{ font-weight: 800; font-size: 18px; }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(280px, .85fr);
      gap: 32px;
      align-items: center;
      padding: 54px 0 38px;
    }}
    h1 {{ font-size: clamp(34px, 5vw, 58px); line-height: 1.02; margin: 0 0 18px; }}
    h2 {{ margin: 0 0 10px; font-size: 22px; }}
    h3 {{ margin: 0 0 8px; font-size: 18px; }}
    p {{ margin: 0; }}
    .lead {{ color: var(--muted); font-size: 19px; max-width: 680px; }}
    .actions {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 26px; }}
    .btn {{
      appearance: none;
      border: 1px solid var(--accent);
      background: var(--accent);
      color: white;
      padding: 12px 16px;
      border-radius: 6px;
      font-weight: 700;
      text-decoration: none;
      display: inline-flex;
      min-height: 46px;
      align-items: center;
    }}
    .btn.secondary {{ background: transparent; color: var(--accent-dark); }}
    .intake {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px;
      box-shadow: 0 16px 40px rgba(23, 32, 42, .08);
    }}
    .field {{
      display: block;
      width: 100%;
      margin: 10px 0;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      font: inherit;
    }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .panel, .service {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
    }}
    .goal {{ color: var(--warn); font-weight: 700; margin-bottom: 8px; }}
    .band {{ padding: 34px 0; }}
    footer {{ color: var(--muted); padding: 32px 0; border-top: 1px solid var(--line); margin-top: 28px; }}
    @media (max-width: 780px) {{
      .wrap {{ padding: 20px; }}
      header {{ align-items: flex-start; flex-direction: column; }}
      .hero, .grid {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 38px; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="brand">{company}</div>
      <a class="btn secondary" href="#contact">{secondary_cta}</a>
    </header>
    <main>
      <section class="hero">
        <div>
          <h1>{headline}</h1>
          <p class="lead">{subheadline}</p>
          <div class="actions">
            <a class="btn" href="#contact">{primary_cta}</a>
            <a class="btn secondary" href="#services">View services</a>
          </div>
        </div>
        <form id="contact" class="intake">
          <h2>Request service</h2>
          <input class="field" placeholder="Name">
          <input class="field" placeholder="Phone">
          <input class="field" placeholder="Email">
          <input class="field" placeholder="Service needed">
          <button class="btn" type="button">{primary_cta}</button>
        </form>
      </section>
      <section class="band">
        <div class="grid">{sections}</div>
      </section>
      <section id="services" class="band">
        <h2>Services customers can understand quickly</h2>
        <div class="grid">{services}</div>
      </section>
    </main>
    <footer>Generated concept for demo purposes. Connect form submissions to CRM follow-up in the full product.</footer>
  </div>
</body>
</html>"""


def generate_personalized_package(input_data: Dict[str, Any] | LeadInput) -> Dict[str, Any]:
    lead = input_data if isinstance(input_data, LeadInput) else LeadInput.from_dict(input_data)
    audit = build_audit(lead)
    website_draft = build_website_draft(lead)
    cold_email = build_cold_email(lead, audit, website_draft)
    html_page = render_landing_page_html(lead, website_draft)

    return {
        "lead": {
            "companyName": lead.company_name,
            "industry": lead.industry,
            "location": lead.location,
            "website": lead.website,
            "email": lead.email,
            "websiteScore": lead.website_score,
            "companySize": lead.company_size,
        },
        "audit": audit,
        "coldEmail": cold_email,
        "websiteDraft": website_draft,
        "generatedWebsiteHtml": html_page,
    }
