"""Number, amount and currency parsing, vendored from `groundley-ai`.

Lives in `web_api` rather than `ai_api` because the dependency runs one way —
`ai_api` imports the domain, never the reverse — so putting it here is what lets
the document stage use it while leaving the door open for `web_api/fx` to adopt
`parse_currency` in place of its own narrower `normalize_currency`.

The upstream tests came across with the code (`tests/web_api/parsers/`) and pass
unedited; they are the specification, and rewriting them to suit us would move
the contract we adopted this for.
"""
