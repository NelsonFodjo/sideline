"""A very small JSON Schema (2020-12 subset) validator.

Why hand-rolled: this server has zero runtime dependencies on purpose
(see docs/ARCHITECTURE.md, "No dependencies"). We only need the subset
our own tool contracts use - object/string/integer/number/boolean/array
(or a list of them), required, enum, minimum/maximum, minLength/maxLength,
pattern, minItems/maxItems. Anything beyond
that is a sign the tool contract has grown too clever for a voice
interface and should be simplified instead.
"""

import re

from .errors import InvalidParams

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def _is(instance, t):
    # bool is a subclass of int in Python; do not let True pass as 1
    if t in ("integer", "number") and isinstance(instance, bool):
        return False
    return isinstance(instance, _TYPES[t])


def validate(instance, schema, path="arguments"):
    t = schema.get("type")
    if t:
        # A list of types: the first that matches decides which keywords apply below
        # (as in JSON Schema, `minimum` constrains numbers only, `pattern` strings only).
        types = t if isinstance(t, list) else [t]
        t = next((x for x in types if _is(instance, x)), None)
        if t is None:
            raise InvalidParams("%s must be a %s" % (path, " or ".join(types)))

    if "enum" in schema and instance not in schema["enum"]:
        raise InvalidParams(
            "%s must be one of %s" % (path, ", ".join(map(str, schema["enum"])))
        )

    if t == "object":
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                raise InvalidParams("%s.%s is required" % (path, key))
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in props:
                    raise InvalidParams("%s.%s is not a known argument" % (path, key))
        for key, sub in props.items():
            if key in instance:
                validate(instance[key], sub, "%s.%s" % (path, key))

    elif t == "array":
        items = schema.get("items")
        if items:
            for i, el in enumerate(instance):
                validate(el, items, "%s[%d]" % (path, i))
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise InvalidParams("%s needs at least %d items" % (path, schema["minItems"]))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise InvalidParams("%s takes at most %d items" % (path, schema["maxItems"]))

    elif t == "string":
        if "minLength" in schema and len(instance) < schema["minLength"]:
            raise InvalidParams("%s is too short" % path)
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise InvalidParams("%s is too long" % path)
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            raise InvalidParams("%s is not in the expected form" % path)

    elif t in ("integer", "number"):
        if "minimum" in schema and instance < schema["minimum"]:
            raise InvalidParams("%s must be at least %s" % (path, schema["minimum"]))
        if "maximum" in schema and instance > schema["maximum"]:
            raise InvalidParams("%s must be at most %s" % (path, schema["maximum"]))

    return instance
