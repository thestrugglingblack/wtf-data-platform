import json


def try_repair_json(text: str):
    try:
        return json.loads(text)

    except json.JSONDecodeError:
        repaired = text

        brace_diff = repaired.count("{") - repaired.count("}")
        bracket_diff = repaired.count("[") - repaired.count("]")

        repaired += "]" * bracket_diff
        repaired += "}" * brace_diff

        return json.loads(repaired)