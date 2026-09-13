"""dependency-audit: fail-closed OSV audit of the committed ``uv.lock``.

Every resolved package is queried against the fixed OSV HTTPS API; any
advisory fails unless the exact advisory/package pair has a short-lived,
justified risk acceptance in ``.security-audit-allow.txt``. Offline is a hard
failure unless ``SECURITY_AUDIT_OFFLINE_POLICY=warn`` is set for a
disconnected local commit (CI must never set it).
"""
