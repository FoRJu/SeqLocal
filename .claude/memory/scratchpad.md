# Scratchpad

Transient working notes. Durable decisions go in `decisions.md`, not here.

## M0 — Environment (in progress, 2026-06-10)

- Scaffolded PLAN.md directory tree.
- Toolchain pins recorded in decisions.md (ADR-0002).
- Dorado bumped 1.x → 2.0.0 (ADR-0001); CLAUDE.md updated to match.
- Medaka isolated in `environment-medaka.yml` (ADR-0003).
- TODO on the Ubuntu 24.04 GPU host: create both envs, run install scripts, generate
  `conda-lock` lockfiles, confirm v6.0 model identifiers from `dorado download --list`.
