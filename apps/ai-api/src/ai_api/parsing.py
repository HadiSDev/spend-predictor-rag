"""Parse free-form LLM text into Pydantic models, repairing malformed JSON."""
from __future__ import annotations

import json
import re
import types
from functools import lru_cache
from typing import Literal, TypeVar, Union, get_args, get_origin

from json_repair import repair_json
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _example_for(annotation: object) -> object:
    """Return a placeholder example value for a field annotation."""
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        return _example_for(non_none[0]) if non_none else "<string>"
    if origin is Literal:
        return " | ".join(str(a) for a in get_args(annotation))
    if origin in (list, set, tuple):
        args = get_args(annotation)
        return [_example_for(args[0])] if args else ["<string>"]
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _skeleton(annotation)
    if annotation is bool:
        return True
    if annotation in (float, int):
        return 0
    return "<string>"


def _skeleton(model: type[BaseModel]) -> dict:
    """Build an example instance shape from a model's fields."""
    return {name: _example_for(f.annotation) for name, f in model.model_fields.items()}


@lru_cache(maxsize=None)
def json_format_hint(model: type[BaseModel], allow_reasoning: bool = False) -> str:
    """Instruction to append to a prompt so the model returns parseable JSON."""
    example = json.dumps(_skeleton(model))
    if allow_reasoning:
        return (
            "Think it through first: name the two or three candidates that could "
            "fit and say briefly why you prefer one. Then, as the LAST thing in "
            "your reply, give a single JSON object with EXACTLY this shape and "
            "these keys (replace the placeholder values; do not add, nest, or "
            "rename keys; no markdown fence; write nothing after it):\n" + example
        )
    return (
        "Return ONLY a single JSON object with EXACTLY this shape and these keys "
        "(replace the placeholder values; do not add, nest, or rename keys; no "
        "markdown fence, no commentary before or after):\n" + example
    )


def _extract_json(text: str) -> str:
    """Isolate the most likely JSON object from an LLM response."""
    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text.strip()


def parse_model(text: str, model: type[T]) -> T:
    """Parse ``text`` into ``model``, repairing malformed JSON when needed."""
    candidate = _extract_json(text)
    try:
        return model.model_validate_json(candidate)
    except (ValidationError, ValueError):
        pass

    obj: object = None
    try:
        obj = repair_json(candidate, return_objects=True)
        return model.model_validate(obj)
    except (ValidationError, ValueError):
        pass
    except Exception:  # noqa: BLE001
        obj = None

    if isinstance(obj, dict) and len(obj) == 1:
        inner = next(iter(obj.values()))
        try:
            return model.model_validate(inner)
        except (ValidationError, ValueError):
            pass

    raise ValueError(f"could not parse {model.__name__} from LLM output")
