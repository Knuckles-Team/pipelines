# PIPE-GATES — Data model

The records below are the types this spec adds. Files named `new` do not exist on the default branch. The row that defines each type is in `requirements.md`.

## Explicit state machines

- `Machine` in new `pipelines_hooks/code/state_machine.py` (`PIPE-GATES-R086`): language, file, type name, declared states, the transition function, the functions that assign the state field, string-literal status comparisons, lifecycle boolean and nullable-timestamp fields, and the tests bound to each transition and refusal.
- `StateMachineFinding` in the same module: file, line, type name and rule number (1 to 4).
