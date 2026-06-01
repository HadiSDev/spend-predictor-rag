"""Factory functions for the three pipeline agents."""
from __future__ import annotations

from crewai import Agent

from .config import get_llm
from .rag.search_tool import ChartOfAccountsSearchTool


def make_extractor() -> Agent:
    return Agent(
        role="Invoice Data Extraction Specialist",
        goal=(
            "Read raw invoice text and extract every structured field accurately: "
            "vendor, invoice number, date, currency, line items, subtotal, tax, and total."
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
            "Assign each invoice to the single best-matching account from the corporate "
            "chart of accounts, using the search tool to find candidates and choosing "
            "only from the returned options."
        ),
        backstory=(
            "You are a management accountant who codes spend to the chart of accounts. "
            "You always search for candidate accounts first and pick the closest fit, "
            "giving a confidence score and a short rationale."
        ),
        llm=get_llm(),
        tools=[ChartOfAccountsSearchTool()],
        max_iter=10,
        verbose=False,
    )
