"""CrewAI tool that retrieves relevant chart-of-accounts entries via RAG."""
from __future__ import annotations

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from .indexer import _default_embed as embed_texts
from .indexer import get_collection


class ChartSearchInput(BaseModel):
    query: str = Field(..., description="Free-text description of the spend to categorize")
    top_k: int = Field(5, description="Number of candidate accounts to return")


class ChartOfAccountsSearchTool(BaseTool):
    name: str = "chart_of_accounts_search"
    description: str = (
        "Search the corporate chart of accounts for accounts relevant to a spend "
        "description. Returns candidate accounts as 'code | name | category | description'."
    )
    args_schema: type[BaseModel] = ChartSearchInput

    def _run(self, query: str, top_k: int = 5) -> str:
        collection = get_collection()
        embeddings = embed_texts([query])
        result = collection.query(query_embeddings=embeddings, n_results=top_k)
        metadatas = (result.get("metadatas") or [[]])[0]
        if not metadatas:
            return "No matching accounts found."
        lines = [
            f'- {m["account_code"]} | {m["account_name"]} | {m["category"]} | {m["description"]}'
            for m in metadatas
        ]
        return "Candidate accounts:\n" + "\n".join(lines)
