"""next_action: the Planner's single entry point. Inputs: memo, question, today, typed results. Nothing else."""
import json
import sys

from planner import ollama, prompt
from planner.schema import SchemaError, validate_action, validate_typed_list

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
            return validate_action(json.loads(chat(messages)), known_ids=known_ids)
        except ollama.OllamaError as e:
            reason = str(e)
        except json.JSONDecodeError:
            reason = "model output is not JSON"
        except SchemaError as e:
            reason = f"invalid action ({e})"
        # Reason only; model output is never logged.
        print(f"planner: attempt {attempt} failed: {reason}", file=sys.stderr)
    return dict(DONE)
