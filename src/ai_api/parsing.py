"""Parse free-form LLM text into Pydantic models, repairing malformed JSON.

We deliberately do NOT use vLLM guided/structured decoding (``response_format``).
Under concurrent requests it intermittently fails to emit a stop token and runs
away to ``max_tokens`` (observed live: 8192 tokens / ~196s -> request timeout),
while the same prompt without a schema completes in a few seconds. So we ask the
model for JSON in the prompt and parse it here instead, falling back to
``json-repair`` for slightly malformed output.

We prompt with a concrete *example skeleton* rather than a JSON Schema: small
models tend to echo a schema's own ``description``/``properties`` keys instead of
producing an instance, whereas they reliably imitate an example's shape.
"""
from __future__ import annotations

import json
import re
import types
from functools import lru_cache
from typing import Literal, TypeVar, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _example_for(annotation: object) -> object:
    """Return a placeholder example value for a field annotation."""
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):  # Optional[X] / X | None
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        return _example_for(non_none[0]) if non_none else "<string>"
    if origin is Literal:
        return " | ".join(str(a) for a in get_args(annotation))  # "Direct | Indirect"
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
def json_format_hint(model: type[BaseModel]) -> str:
    """Instruction to append to a prompt so the model returns parseable JSON.

    Cached: the hint is a pure function of the (static) model class.
    """
    example = json.dumps(_skeleton(model))
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
    """Parse ``text`` into ``model``, repairing malformed JSON when needed.

    Raises ``ValueError`` if the text cannot be coerced into the model.
    """
    candidate = _extract_json(text)
    try:
        return model.model_validate_json(candidate)
    except (ValidationError, ValueError):
        pass

    obj: object = None
    try:
        from json_repair import repair_json

        obj = repair_json(candidate, return_objects=True)
        return model.model_validate(obj)
    except (ValidationError, ValueError):
        pass
    except Exception:  # noqa: BLE001 - repair backend failure -> fall through
        obj = None

    # Defense in depth: a model sometimes wraps the answer, e.g.
    # {"AccountChoice": {...}} or {"result": {...}}. Try the lone nested object.
    if isinstance(obj, dict) and len(obj) == 1:
        inner = next(iter(obj.values()))
        try:
            return model.model_validate(inner)
        except (ValidationError, ValueError):
            pass

    raise ValueError(f"could not parse {model.__name__} from LLM output")
