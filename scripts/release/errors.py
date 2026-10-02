"""Exceptions for the dependency-ordered digest release tooling."""

from __future__ import annotations


class ReleaseError(Exception):
    """Base of every release-orchestration refusal."""


class CandidateSetError(ReleaseError):
    """The candidate manifest fails strict validation (FR-1): fail closed, never partially trust it."""


class ReproducibilityError(ReleaseError):
    """A reproducible-build comparison could not produce a trustworthy verdict."""
