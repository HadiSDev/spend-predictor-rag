import pytest


@pytest.fixture
def mock_erp_connector():
    """A MockErpConnector wired to the mock ERP app, in-process.

    Mirrors ``tests/test_mock_erp.py``'s ``connector_over_app`` fixture:
    ``TestClient`` is a synchronous ``httpx.Client`` bound to the ASGI app
    (entering it fires startup, i.e. the data generator). Assigning it as
    the connector's own ``_http`` — an attribute the connector already
    lazily builds itself — gives every fetch a real HTTP round-trip through
    the actual FastAPI handlers, without a live server and without touching
    any private httpx internals.
    """
    from fastapi.testclient import TestClient
    from mock_erp.main import app
    from web_api.connectors.mock import MockErpConnector

    client = TestClient(app)
    client.__enter__()
    connector = MockErpConnector({"api_key": "mock-secret"})
    connector._http = client
    yield connector
    client.__exit__(None, None, None)


@pytest.fixture(autouse=True)
def offline_categorizer(monkeypatch):
    """No test ever calls a real model.

    The line categorizer asks an LLM, so without this the suite would open
    network connections to whatever `VLLM_BASE_URL` points at — hanging when
    nothing is listening and, worse, passing or failing on a model's mood.

    The stand-in reads the prompt the categorizer actually built and answers in
    the format it actually expects, so the seam under test is the real one: it
    parses the numbered candidate list, scores it against the line's own words,
    and picks the best overlap or declines. Deterministic, offline, and it
    exercises the parsing and grounding paths rather than bypassing them.

    A test that wants a specific answer passes its own `complete` to
    `categorize_line`, or monkeypatches this back out.
    """
    import re

    from ai_api.sync import llm_categorizer

    def _words(text: str) -> set[str]:
        return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}

    def offline_complete(prompt: str) -> str:
        facts, _, rest = prompt.partition("Categories:")
        line_words = _words(facts.split("Invoice line:", 1)[-1])
        best_index, best_score = 0, 0
        for raw in rest.splitlines():
            match = re.match(r"\s*(\d+)\.\s+(.*)", raw)
            if not match or match.group(1) == "0":
                continue
            score = len(line_words & _words(match.group(2)))
            if score > best_score:
                best_index, best_score = int(match.group(1)), score
        if best_index == 0:
            return '{"choice": 0, "confidence": 0.0, "rationale": "offline stand-in found no overlap"}'
        return (
            f'{{"choice": {best_index}, "confidence": 0.9, '
            f'"rationale": "offline stand-in matched {best_score} word(s)"}}'
        )

    monkeypatch.setattr(llm_categorizer, "_default_complete", offline_complete)
