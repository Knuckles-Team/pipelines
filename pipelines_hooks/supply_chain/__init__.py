"""supply-chain: fail closed on high-risk source supply-chain drift.

Inspects Git-tracked and untracked non-ignored files (or, in source-snapshot
mode, exactly the workspace-declared provider roots). It never follows a
repository symlink, never fetches, installs, builds or executes project code,
and reports repository-relative locations only.
"""
