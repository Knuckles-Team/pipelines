# PIPE-GATES — Data model

The records below are the types this spec adds. Files named `new` do not exist on the default branch. The row that defines each type is in `requirements.md`.

## Explicit state machines

- `Machine` in new `pipelines_hooks/code/state_machine_model.py` (`PIPE-GATES-R086.1`): language, file, type name, declared states, the table or the transition function, the functions that assign the state field, string-literal status comparisons, lifecycle flag fields, and the tests bound to each transition and refusal.
- `Finding` in the same module: file, line, type name, code and rule number (1 to 5). The codes are `SM-MULTI-ASSIGN`, `SM-STRING-STATUS`, `SM-LIFECYCLE-FLAGS`, `SM-UNTESTED-EDGE`, `SM-NO-REFUSAL-TEST` and `SM-NO-DECLARATION`.
