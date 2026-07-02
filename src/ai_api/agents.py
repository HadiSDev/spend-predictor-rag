"""Factory functions for the three pipeline agents."""
from __future__ import annotations

from crewai import Agent

from .config import get_llm


def make_extractor() -> Agent:
    return Agent(
        role="Invoice Data Extraction Specialist",
        goal=(
            "Read raw invoice text and extract every structured field accurately: "
            "vendor, supplier and buyer country codes and VAT numbers, invoice number, "
            "date, currency, line items (with unit type, quantity, and per-line VAT "
            "code and rate), subtotal, tax, and total."
        ),
        backstory=(
            "You are a meticulous accounts-payable clerk who has transcribed tens of "
            "thousands of invoices. You never invent values: if a field is absent you "
            "leave it null, and you copy amounts exactly as written."
        ),
        llm=get_llm(),
        tools=[],
        max_iter=10,
        verbose=False,
    )


def make_verifier() -> Agent:
    return Agent(
        role="Invoice Arithmetic Auditor",
        goal=(
            "Independently verify an extracted invoice: confirm line items sum to the "
            "subtotal and that subtotal plus tax equals the total, and list every "
            "discrepancy you find."
        ),
        backstory=(
            "You are a skeptical financial auditor who trusts nothing until the numbers "
            "reconcile. You flag mismatches precisely but never block processing."
        ),
        llm=get_llm(),
        tools=[],
        max_iter=10,
        verbose=False,
    )


def make_categorizer() -> Agent:
    return Agent(
        role="Spend Categorization Analyst",
        goal=(
            "Choose the single best leaf account for an invoice from the provided "
            "candidate accounts, and classify the spend as Direct or Indirect based "
            "on the buyer's business context and the invoice line items. Never invent "
            "an account code; never classify the hierarchy beyond Direct/Indirect."
        ),
        backstory=(
            "You are a management accountant. You are given the buyer's business "
            "context, what the products are, and a shortlist of candidate accounts. "
            "You pick the closest account and judge whether the spend is a direct cost "
            "of the buyer's revenue (Direct) or overhead (Indirect)."
        ),
        llm=get_llm(),
        tools=[],
        max_iter=5,  # a single pick from an injected shortlist needs few iterations
        verbose=False,
    )
