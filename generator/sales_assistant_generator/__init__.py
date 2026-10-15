"""Personalized website and outreach generator for the sales assistant MVP."""

from .generator import generate_personalized_package
from .models import LeadInput

__all__ = ["LeadInput", "generate_personalized_package"]
