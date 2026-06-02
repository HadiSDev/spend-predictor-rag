from spend_predictor import web_context
from spend_predictor.models import LineItem


def test_buyer_context_cache_miss_then_hit(tmp_path):
    calls = {"scrape": 0, "summarize": 0}

    def scrape(url):
        calls["scrape"] += 1
        return f"raw site for {url}"

    def summarize(name, text):
        calls["summarize"] += 1
        return f"{name} is a SaaS company."

    kw = dict(name="Acme", website="https://acme.example",
              scrape_fn=scrape, summarize_fn=summarize, cache_dir=str(tmp_path))
    first = web_context.get_buyer_context(**kw)
    second = web_context.get_buyer_context(**kw)
    assert first == "Acme is a SaaS company."
    assert second == first
    assert calls == {"scrape": 1, "summarize": 1}  # second call served from cache


def test_buyer_context_blank_when_unconfigured(tmp_path):
    out = web_context.get_buyer_context(
        name="", website="", scrape_fn=lambda u: "x",
        summarize_fn=lambda n, t: "y", cache_dir=str(tmp_path)
    )
    assert out == ""


def test_product_context_searches_each_line_item(tmp_path):
    queries = []

    def search(query):
        queries.append(query)
        return [{"title": "t", "body": f"about {query}", "href": "h"}]

    def summarize(items_with_snippets):
        return "PRODUCTS:\n" + "\n".join(f"- {d}" for d, _ in items_with_snippets)

    items = [LineItem(description="cloud hosting", amount=100.0),
             LineItem(description="object storage", amount=20.0)]
    out = web_context.get_product_context(
        items, "Nimbus", search_fn=search, summarize_fn=summarize, cache_dir=str(tmp_path)
    )
    assert len(queries) == 2
    assert "Nimbus cloud hosting" in queries[0]
    assert "cloud hosting" in out and "object storage" in out


def test_product_context_empty_items(tmp_path):
    out = web_context.get_product_context(
        [], "Nimbus", search_fn=lambda q: [], summarize_fn=lambda x: "Z", cache_dir=str(tmp_path)
    )
    assert out == ""
