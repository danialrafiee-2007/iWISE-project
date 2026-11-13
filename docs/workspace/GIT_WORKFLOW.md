# Git workflow for the working copy

> **Status (2026-11-13, 19:2x): §3, §4.1–4.2 and the local part of §5 are DONE**, with the user's approval ("Approve
> Git setup").
> - The working copy is a Git repository at `c5e4ac81`; the local branches are `main` (tracking `origin/main`) and
>   **`sepehr/ui-ux-development`** (checked out, no upstream).
> - The guard rails are installed.
> - **Nothing has been pushed.** On the user's decision ("Commit on my branch"), `docs/workspace/` is committed on
>   `sepehr/ui-ux-development` (the first commit after `c5e4ac81`). Following D-152, the commit message names no AI
>   tool.
> - Still open: protecting `main` on GitHub (§4.3, the owner's action), and the first push of the personal branch
>   (needs approval).
>
> Sections 1–5 below keep the original plan for reference. §7 records what was actually run.

## 1. Verified facts

| Item | Finding | How verified |
|---|---|---|
| Source project | Not a Git repository (no `.git` at any depth); it is the ready-made package, build `20261111-1615-e88d666b` | `find` for `.git`; `..\packages\package.txt` |
| Working copy | No `.git`; exact copy of the source minus `.venv` | SHA-256 manifest of 35,963 files, identical |
| Official repo | `https://github.com/danialrafiee-2007/iWISE-project`, public, default branch `main` | `gh api repos/...` |
| Branches on GitHub | Only `main` at `c5e4ac81`; **not protected** | `gh api .../branches`, `git ls-remote` |
| Tag | `package-20261111-1611`, lightweight, points at `c5e4ac81` | `gh api .../git/refs/tags/...` |
| Commit `c5e4ac81` | 2026-11-11 12:41 UTC, "Correct the dates of D-223 and D-224 and the new release's name"; parent `762f0bc8`; tree `3e9f6524448b…`; `main` holds 111 commits | `gh api .../commits/...` |
| Release | "Truth Guardian — final project", tag `package-20261111-1611`, 8 assets (4 zip parts, starter, guide, SHA256SUMS, package.txt) | `gh api .../releases` |
| Code identity | All 433 tracked files match GitHub's blobs. A dry run in a **scratch** repo (`GIT_DIR` in the scratchpad, `GIT_WORK_TREE` = working copy) staged exactly **433 files** and gave tree **`3e9f6524448bd131117692823805141795afce75`**, the tree of `c5e4ac81` | blob-hash comparison; `git add -A` + `git write-tree` in the scratch repo |
| Ignored extras | `runtime/`, `.venv`, `data/raw`, `data/processed`, `data/web/*` (except `learned_seed.json`), `*.onnx`, `*.safetensors`, `models/detector/`, `eval/*_run.log`, `__pycache__`, `*.local.env` | `.gitignore`; dry run staged none of them |
| Line endings | `.gitattributes` keeps `.bat` files CRLF. Three files on disk have CRLF that Git normalizes (`data/web/learned_seed.json`, `eval/annotation/claims_A.csv`, `claims_B.csv`): a warning only, the content hash matches | dry-run warnings |
| Your access | The logged-in `gh` account has **push** rights (no admin) | `gh api` permissions |
| Secrets in the copy | None: no `*.local.env`, `.env` or key files; only the `*.example.env` templates | `find` |

**Main risk:** push rights plus an unprotected `main` mean one mistaken `git push origin main` or force-push changes the
team's code directly.

## 2. Options for connecting the working copy

| Option | What it does | Verdict |
|---|---|---|
| **A. Attach history in place** (`git init` + `fetch` + `reset --mixed` to the exact commit) | Adds `.git`; index and HEAD come from `c5e4ac81`; **no working-tree file is written** | **Recommended**: proven by the dry run, keeps the 6.4 GB of runtime assets in place |
| B. Fresh `git clone` elsewhere, then copy the runtime assets into it | Clean clone, then robocopy `runtime/`, `data/`, `models/` weights | More copying; the clone would also check out files over existing ones if done in place |
| C. `git clone --no-checkout` to temp, move its `.git` here | Same result as A | More moving parts than A |

## 3. Proposed setup (Option A), awaiting approval

Run from `A:\Apps\IWISI_London\Edit_IWISE_Project\TruthGuardian`.

```bash
# 3.1 Pre-flight: confirm nothing moved
git ls-remote https://github.com/danialrafiee-2007/iWISE-project refs/heads/main refs/tags/package-20261111-1611
#     both must print c5e4ac816e34b0008956ffaa8335fd1d53f9913e; if main moved, still use the exact commit below

# 3.2 Attach the history without touching files
git init -b main
git remote add origin https://github.com/danialrafiee-2007/iWISE-project.git
git fetch origin main --tags
git reset --mixed c5e4ac816e34b0008956ffaa8335fd1d53f9913e   # HEAD + index only
git branch --set-upstream-to=origin/main main

# 3.3 Verify
git rev-parse HEAD            # c5e4ac81...
git write-tree                # 3e9f6524448bd131117692823805141795afce75
git status --short            # expected: only ?? docs/workspace/ (the workspace docs)
```

If `git status` lists any modified tracked file, stop and compare before going further. Nothing is lost: the files on
disk were never touched.

## 4. Guard rails (local; recommended before any branch work)

1. **A pre-push hook** (`.git/hooks/pre-push`, never committed) that blocks every push to `main`:

   ```sh
   #!/bin/sh
   while read local_ref local_sha remote_ref remote_sha; do
     if [ "$remote_ref" = "refs/heads/main" ]; then
       echo "pre-push: pushing to main is blocked in this workspace; open a pull request instead." >&2
       exit 1
     fi
   done
   exit 0
   ```

2. **Safer defaults.** They do **not** stop an explicit `git push origin main`; the hook does that.

   ```bash
   git config push.default current          # a bare "git push" pushes only the current branch
   git config branch.main.pushRemote no_push
   ```

3. **Ask the repository owner** to protect `main` on GitHub (pull requests required, no force-push). That is the only
   guard that also covers other machines.

## 5. Personal branch, awaiting approval

- **Name:** `sepehr/ui-ux-development` (chosen by the user).
- **Create it from the exact verified commit:** `git switch -c sepehr/ui-ux-development c5e4ac81`.
- **First push**, only when approved: `git push -u origin sepehr/ui-ux-development`. This creates the remote branch,
  never `main`.
- **Topic branches** (optional) for larger changes: `sepehr/ui-<topic>` from the personal branch, merged back after
  verification.
- **Keeping up with the team:** `git fetch origin`, then `git merge origin/main` into the personal branch. Rebase only
  branches nobody else has pulled.
- **Getting work into `main`:** a pull request from `sepehr/ui-ux-development`, reviewed by the team. Never push to
  `main`, never force-push, never delete remote branches.
- **Before every commit:**
  - `git status` and `git diff --staged`
  - nothing from `runtime/`, `data/web/`, `*.local.env` or any key may be staged
  - stage named paths rather than `git add -A`
- **Commit style:** the team writes one plain sentence describing the result and cites decision IDs; follow it.
- **`docs/workspace/`:** commit it on the personal branch, or keep it local through `.git/info/exclude`. This is the
  user's decision; nothing is committed until then.

## 6. Running the app from the working copy (later, needs approval)

`TruthGuardian.bat` sees that `.venv` is missing and rebuilds it **offline** from `runtime/uv-cache` (about a minute),
then serves `http://127.0.0.1:8765`. This writes `.venv/`, `runtime/logs/` and `data/web/` caches inside the working
copy only, never the source.

## 7. What was run (2026-11-13), and the result

| Step | Command (in the working copy) | Result |
|---|---|---|
| Pre-flight | `git ls-remote ... refs/heads/main refs/tags/package-20261111-1611` | Both `c5e4ac81`. `.git` absent |
| Line endings | (checked only) | System `core.autocrlf=true`, but `.gitattributes` (`* text=auto eol=lf`, `*.bat -text`) decides; no config changed |
| Init | `git init -b main`, then `git remote add origin https://github.com/danialrafiee-2007/iWISE-project.git` | OK |
| Fetch, first try | `git fetch origin main --tags` | **Failed**: `fetch-pack: invalid index-pack output` after ~11.7 MB (transfer problem). No commit present, so the following `git reset` refused to run ("Could not parse object"); nothing was changed |
| Cleanup | `rm .git/objects/pack/tmp_pack_*` | Removed the broken temporary pack, inside `.git` only |
| Fetch, retry | `git fetch --progress origin main --tags` | OK: `origin/main` and tag `package-20261111-1611` = `c5e4ac81` (repo about 15.5 MB, 2,127 deltas) |
| Attach | `git reset --mixed c5e4ac816e34b0008956ffaa8335fd1d53f9913e`, then `git branch --set-upstream-to=origin/main main` | OK; HEAD and index only |
| Verify | `git rev-parse HEAD`, `git write-tree`, `git diff --stat`, `git status --short` | HEAD `c5e4ac81`; tree `3e9f6524…` = commit tree; 433 tracked; **no tracked file differs**; only `?? docs/workspace/` |
| Files untouched | `find . -path ./.git -prune -o -type f -newermt '2026-11-13 19:20'` | **0** project files modified; 35,969 files (35,963 + 6 docs) |
| Guard rails | `.git/hooks/pre-push` (blocks any push whose target is `refs/heads/main`); `git config push.default current`; `git config branch.main.pushRemote no_push` | Hook tested **offline** with sample input: main → blocked (exit 1, twice); personal branch → allowed (exit 0). No push attempted |
| Personal branch | `git switch -c sepehr/ui-ux-development c5e4ac81` | Created and checked out; **no upstream**; working tree unchanged (0 files modified) |
| Remote unchanged | `git ls-remote --heads origin` | Only `main` at `c5e4ac81` |

**Not covered by the hook:** a force-push to the personal branch itself, and pushes from other clones. The team rule
"never force-push" still applies, and GitHub branch protection on `main` is still recommended.

**Commit of the workspace docs (2026-11-13, user's decision "Commit on my branch"):** the six files in
`docs/workspace/` were committed on `sepehr/ui-ux-development` with `git add docs/workspace` (named path, nothing
else staged). The message follows the team's style and D-152 (no line naming the AI tool; AI use is disclosed in
`docs/AI_USAGE.md` when the work goes to `main`).

**Next Git step (needs approval):** first push, `git push -u origin sepehr/ui-ux-development`.
