"""next_action: the Planner's single entry point. Inputs: memo, question, today, typed results. Nothing else."""
import json
import sys

from planner import ollama, prompt
from planner.schema import SchemaError, normalize_preset, validate_action, validate_typed_list

DONE = {"action": "done"}
ATTEMPTS = 2  # first try plus one retry


def next_action(memo, question, today, typed_results, *, chat=None) -> dict:
    if not isinstance(memo, str) or not isinstance(question, str):
        raise TypeError("memo and question must be strings")
    typed = validate_typed_list(typed_results)  # raises before anything reaches the model
    known_ids = {v["result_id"] for t in typed for v in t["values"]}
    messages = prompt.build_messages(memo, question, today, typed)
    chat = chat or ollama.chat

    for attempt in range(1, ATTEMPTS + 1):
        try:
            # Safety net: a wrong preset is corrected to the action's default (fixed list only) instead of
            # failing the whole action. Every other field is still validated strictly below.
            obj, corrected = normalize_preset(json.loads(chat(messages)))
            if corrected:
                # The action word and default preset are fixed values; the model's preset is never logged.
                print(f"planner: corrected {obj['action']} preset to {obj['preset']}", file=sys.stderr)
            return validate_action(obj, known_ids=known_ids)
        except ollama.OllamaError as e:
            reason = str(e)
        except json.JSONDecodeError:
            reason = "model output is not JSON"
        except SchemaError as e:
            reason = f"invalid action ({e})"
        # Reason only; model output is never logged.
        print(f"planner: attempt {attempt} failed: {reason}", file=sys.stderr)
    return dict(DONE)
