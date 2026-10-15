"""Industry and pain-point templates used by the rule-based generator."""

from __future__ import annotations

from typing import Dict, List


INDUSTRY_PROFILES: Dict[str, Dict[str, object]] = {
    "plumber": {
        "customer_need": "fast help for leaks, repairs, and emergency callouts",
        "primary_cta": "Request a plumbing quote",
        "secondary_cta": "Call for emergency service",
        "services": ["Emergency plumbing", "Leak detection", "Drain cleaning", "Water heater repair"],
    },
    "electrician": {
        "customer_need": "safe electrical repairs, upgrades, and urgent fault checks",
        "primary_cta": "Book an electrical inspection",
        "secondary_cta": "Call a licensed electrician",
        "services": ["Emergency repairs", "Panel upgrades", "Lighting installation", "Safety inspections"],
    },
    "roofing": {
        "customer_need": "clear estimates, storm-damage support, and trusted roof repairs",
        "primary_cta": "Get a roof estimate",
        "secondary_cta": "Schedule an inspection",
        "services": ["Roof repair", "Roof replacement", "Storm damage checks", "Gutter service"],
    },
    "dentist": {
        "customer_need": "easy appointment booking and confidence before visiting",
        "primary_cta": "Book an appointment",
        "secondary_cta": "Ask about availability",
        "services": ["General dentistry", "Emergency dental care", "Cleanings", "Cosmetic dentistry"],
    },
    "local service": {
        "customer_need": "a clear reason to trust the business and a quick way to make contact",
        "primary_cta": "Request a quote",
        "secondary_cta": "Contact the team",
        "services": ["Consultation", "Service quote", "Scheduling", "Customer support"],
    },
}


PAIN_POINT_LIBRARY: Dict[str, Dict[str, str]] = {
    "booking": {
        "bottleneck": "Visitors have no simple way to book or request service without calling.",
        "automation": "Add an online booking or quote form that routes requests into the CRM automatically.",
        "quick_win": "Place a short request form above the fold and repeat the booking CTA after service sections.",
        "website_section": "A booking block with service type, preferred time, address, and urgency fields.",
    },
    "mobile": {
        "bottleneck": "Mobile visitors may struggle to understand the offer or contact the company quickly.",
        "automation": "Use a mobile-first landing page with sticky call and quote actions.",
        "quick_win": "Prioritize tap-friendly buttons, shorter copy, and a visible phone CTA on small screens.",
        "website_section": "A compact mobile hero with one clear promise and two action buttons.",
    },
    "cta": {
        "bottleneck": "The site does not make the next step obvious enough for ready-to-buy visitors.",
        "automation": "Trigger follow-up reminders for visitors who submit a form but do not schedule.",
        "quick_win": "Use one primary CTA across the page and connect it to the most valuable conversion.",
        "website_section": "A repeated CTA strip that explains exactly what happens after the request.",
    },
    "trust": {
        "bottleneck": "The site may not show enough proof to make a new customer feel safe choosing them.",
        "automation": "Collect reviews after completed jobs and surface the best ones on the website.",
        "quick_win": "Add review highlights, licenses, guarantees, and recent project examples.",
        "website_section": "A trust section with reviews, credentials, service guarantees, and local proof.",
    },
    "speed": {
        "bottleneck": "Slow loading can reduce calls and form submissions, especially on mobile.",
        "automation": "Monitor page speed and alert the team when key pages become slower.",
        "quick_win": "Compress images, remove unused scripts, and keep the landing page lightweight.",
        "website_section": "A fast-loading service page focused on essential content and conversion.",
    },
    "email": {
        "bottleneck": "The business is missing an easy public email/contact path for lower-urgency leads.",
        "automation": "Route email and form inquiries into a shared lead inbox with status tracking.",
        "quick_win": "Add a dedicated contact block with phone, email, service area, and response-time promise.",
        "website_section": "A contact block that explains when to call, email, or request a quote.",
    },
}


DEFAULT_PAIN_POINTS: List[str] = [
    "No clear conversion path for visitors",
    "Weak proof of trust for first-time buyers",
    "Manual follow-up likely depends on phone calls or inbox memory",
]
