"""Clone gates: dupehound (structural whole-function clones) and jscpd (copied blocks).

Dupehound answers "does a changed function reimplement an existing one after
identifiers and literals are rewritten"; jscpd owns copied blocks, templates
and configuration, including blocks embedded in otherwise different functions.
The two run at different hook stages so one incident does not produce two
simultaneous blocking verdicts.
"""
