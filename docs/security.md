# security.md — hardening reference & kill-switch runbook

Companion to CLAUDE.md → "Production hardening & integrity" and PLAN.md → "Kill-switch &
MinKNOW co-location design". This file is the operator-facing reference. It grows as the
deferred infrastructure lands (image signing at M6; central management plane at M8).

## Enforced now (every run, M1 onward)

These are checked by `bin/ont_pipeline.sh` — the single integrity/kill-switch chokepoint —
before any pipeline work, and recorded in the per-run manifest
(`results/pipeline_info/run-manifest.json`).

| Seam | Where | Behavior now | Plugs into later |
|------|-------|--------------|------------------|
| Non-root / `bfxsvc` | entrypoint | refuse to run as root; warn if not `bfxsvc` (hard-fail with `SEQLOCAL_REQUIRE_BFXSVC=1`) | deploy identity owns code read+exec-only to `bfxsvc` |
| Kill-flag | entrypoint | refuse if `SEQLOCAL_KILL_FLAG` (default `/var/lib/seqlocal/KILL`) exists | M8 central kill trigger flips this local flag |
| Code integrity | entrypoint | hash git-tracked repo; compare to `SEQLOCAL_CODE_HASH` / `/var/lib/seqlocal/code.sha256`; refuse on mismatch | M6 cosign image signing + per-process digests |
| MinKNOW yield | entrypoint | refuse if `SEQLOCAL_FLOWCELL_ACTIVE=1` | M8 systemd resource slices / GPU arbitration |
| Run manifest | every stage | each stage appends a sha256-hashed provenance block; `MANIFEST_MERGE` finalizes + schema-validates | M8 append-only central manifest store |

The kill-flag and the recorded code-hash baseline live **outside the repo** at a runtime
path (e.g. `/var/lib/seqlocal/`), owned by the deploy identity and **not writable by
`bfxsvc`** — the account that runs the pipeline must not be able to disable its own gate.

## Kill-switch fail-safe semantics

On trip (kill-flag present), the pipeline MUST:

1. **Halt** — do no further work.
2. **Quarantine** in-flight data in place.
3. **Refuse** to emit or transmit any deliverable.
4. **Revoke** delivery credentials — *once the central plane exists (M8)*.
5. **Alert** — see the alert path below.

It MUST NOT:

- **Wipe data** — forensics and chain of custody require the data stay intact.
- **Auto-abort a live flow cell** — analysis-stop and sequencing-stop are separate
  decisions; aborting sequencing is never automatic.

## Alert path & ownership (TODO — fill before production)

> The switch is only as good as its runbook.

- **On-call owner:** _TODO — name/role responsible for kill-switch trips._
- **Alert channel:** _TODO — pager/email/Slack destination._
- **Escalation:** _TODO — who decides analysis-resume vs. sequencing-stop._

## Deferred (seam reserved now, built later)

- **M6:** container image signing (cosign/sigstore) + per-process image digests; the
  manifest `pipeline.container_digest` field is populated then (null on the conda interim).
- **M8:** central management plane — heartbeat, dead-man's-switch token, scoped+revocable
  delivery credentials, config-as-code push; OS tamper-evidence (dm-verity / AIDE /
  read-only immutable mounts); the central kill trigger that flips the local flag.

## Provisioning the `bfxsvc` account (deployment, on the box)

Not automated by this repo — part of host provisioning:

- Create `bfxsvc` as a **no-login, no-shell, no-sudo** service account.
- Code + containers owned by a **separate deploy identity**, **read+execute-only** to
  `bfxsvc`.
- Record the code-hash baseline at deploy: write the repo hash printed by
  `bin/ont_pipeline.sh` to `/var/lib/seqlocal/code.sha256` (owned by the deploy identity).
- Never develop or test as root.
