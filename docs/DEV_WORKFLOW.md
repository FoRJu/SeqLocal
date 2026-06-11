# DEV_WORKFLOW.md — develop on macOS, run on the Ubuntu GPU box

Code is written on a MacBook Pro; **all execution and testing happen on the Ubuntu
24.04 box** (NVIDIA + CUDA, RTX 4090). macOS can't run Dorado, CUDA, or the bioconda
GPU stack, so nothing in this pipeline is meant to run locally — the Mac is an editor,
the Ubuntu box is the runtime.

There are two loops. Use git for durable history; use rsync for fast iteration.

## 1. Durable loop — git (source of truth)

Every milestone and reviewable change goes through git. This is the CRO-reproducible
record.

```bash
# one-time: create a private remote (GitHub example) and push
gh repo create ont-pipeline --private --source=. --remote=origin
git push -u origin main
```

Then, on the Ubuntu box:

```bash
git clone <remote-url> ont-pipeline && cd ont-pipeline
# provision once, per docs/SETUP.md:
mamba env create -f environment.yml
mamba env create -f environment-medaka.yml
bash bin/install_dorado.sh
bash bin/install_nextflow.sh
```

Day to day: commit on the Mac → `git push`; on the box `git pull` and run.

## 2. Fast loop — rsync (tight iteration)

When you're iterating on a run and don't want a commit per change, push the working
tree straight to the box. `bin/sync.sh` wraps rsync and excludes heavy/gitignored
paths (`tools/`, `work/`, `results/`, `*.pod5`, `.git`).

```bash
# one-time: point it at your box (host + path). Stored untracked in .sync.env
echo 'SYNC_DEST="user@ont-box:~/ont-pipeline"' > .sync.env

# each iteration: push Mac → box
bash bin/sync.sh

# then run on the box over SSH, e.g.
ssh user@ont-box 'cd ~/ont-pipeline && mamba run -n ont-tools nextflow run workflows/main.nf ...'
```

rsync is one-directional (Mac → box) by design: the Mac stays the editing source, the
box never edits code. Results/outputs are pulled back explicitly when needed
(`rsync -avz user@ont-box:~/ont-pipeline/results/ ./results/`), not auto-synced.

## 3. Alternative — VS Code Remote-SSH (edit in place)

If you'd rather skip syncing entirely, open the repo **on the box** via VS Code
Remote-SSH and edit the files there directly. Then git is still the source of truth
(commit/push from the box). Good when you're doing long debugging sessions against
real POD5 data. Pick this *or* the rsync loop, not both at once, to avoid divergent
copies.

## Which to use

| Situation | Use |
|-----------|-----|
| Finishing a milestone / anything reviewable | git push/pull |
| Tweak-run-tweak against real data | `bin/sync.sh` (or Remote-SSH) |
| Long interactive debugging on the box | VS Code Remote-SSH |

> Whatever the inner loop, land the change in git before calling it done — the
> reproducibility record lives there, not in an rsync'd working tree.
