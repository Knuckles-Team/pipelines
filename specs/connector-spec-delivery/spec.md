# PIPE-CONNSPEC-001 — Connector spec-delivery rollout

## Purpose and user stories

A maintainer of any connector or agent package sees the same spec-delivery method and the same published status page as the five core repositories. The core implementation in this repository is the single reference, so every connector is checked the same way.

## Functional requirements

- **FR-1 — One standard.** PIPE-CONNSPEC-R001 to PIPE-CONNSPEC-R005 state the standard by pointing at the core implementation: generated status and hooks, test bindings, the page, the reference callers, and the lane contract.
- **FR-2 — Per-connector adoption.** PIPE-CONNSPEC-R101 to PIPE-CONNSPEC-R174 each cover one of the 74 connector repositories listed under the agents section of the workspace manifest, with four children: a generated `specs/` tree, the three hooks, the Pages caller, and the rapid-delivery skill section.

## Scope and interfaces

Excludes the five core repositories, pipelines itself, third-party clones, services, images, and the skill repositories (universal-skills, skill-graphs). No code is changed by this spec. It tracks the rollout only.
