"""cccc complexity gates: diff-scoped staged gate and absolute census.

Measurement rule: BOTH metrics (cyclomatic 10, cognitive 15), EVERY function,
INCLUDING nested children. Extraction moves complexity into the child, so a
parent that now looks clean is not the whole story.
"""

MAX_CYCLOMATIC = 10
MAX_COGNITIVE = 15
