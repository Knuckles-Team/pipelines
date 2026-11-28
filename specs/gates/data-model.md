# PIPE-GATES — Data model

The records below are the types this spec adds. Files named `new` do not exist on the default branch. The row that defines each type is in `requirements.md`.

## Explicit state machines

- `Machine` in new `pipelines_hooks/code/state_machine_model.py` (`PIPE-GATES-R086.1`): language, file, type name, declared states, the table or the transition function, the functions that assign the state field, string-literal status comparisons, lifecycle flag fields, and the tests bound to each transition and refusal.
- `Finding` in the same module: file, line, type name, code and rule number (1 to 6). The codes are `SM-MULTI-ASSIGN`, `SM-STRING-STATUS`, `SM-STRING-VALUE` (`PIPE-GATES-R086.13`, rule 2, a string status on a type set only at construction), `SM-LIFECYCLE-FLAGS`, `SM-UNTESTED-EDGE`, `SM-NO-REFUSAL-TEST`, `SM-NO-DECLARATION`, and for rule 6 (`PIPE-GATES-R086.9`) `SM-UNREACHABLE`, `SM-DEAD-END`, `SM-TERMINAL-NOT-ABSORBING`, `SM-NONDETERMINISTIC`, `SM-UNTESTED-REFUSAL` and `SM-NO-INITIAL`, and for rule 7 (`PIPE-GATES-R086.11`) `SM-UNRESOLVED-RECEIVER`, whose type name is `<unresolved>`. `Use.receiver` is the resolved type name or `None`.
- `Site.how` and `Machine.assigned_flags` (`PIPE-GATES-R086.27`, `PIPE-GATES-R086.28`): `how` is `recompute` for a replacement of the status by a computed value in a function that never compares that status; `assigned_flags` holds the flags a non-constructor function assigns. `Machine.derived` and `Machine.settle_flags` read them. `Use.kind` gains `flag`.
