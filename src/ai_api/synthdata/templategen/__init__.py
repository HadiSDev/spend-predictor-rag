"""Offline tool: web image references -> drafted invoice HTML templates.

Searches the web for invoice design references, drafts Jinja2 templates from them
via the local vision LLM, validates them (render + contract + no-real-data lint),
and stages them for human review. NOT part of the generator's runtime path.
"""
