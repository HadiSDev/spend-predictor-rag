"""Organization-owned spend trees: the taxonomy categorization targets.

``service`` is the only writer of ``SpendCategory`` — see its module docstring
for why. ``template`` holds the platform's default taxonomy; ``importer``
turns a CSV into nodes; ``reassign`` handles a company changing trees.
"""
from .service import SpendTreeError, ensure_default_tree

__all__ = ["SpendTreeError", "ensure_default_tree"]
