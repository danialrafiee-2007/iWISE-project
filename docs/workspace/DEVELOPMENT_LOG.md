# Development log

> One entry per meaningful change: date, what changed, files, why, and how it was verified. Newest first.
> Every change to application code must be recorded here.

---

## 2026-11-13 (evening): workspace docs committed on the personal branch (no application code changed)

- **Decision:** the user chose "Commit on my branch" for `docs/workspace/`.
- **What:** one commit on `sepehr/ui-ux-development`, the first after `c5e4ac81`, holding the six files of
  `docs/workspace/` (`PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `UI_UX_GUIDE.md`, `COMPONENT_MAP.md`,
  `GIT_WORKFLOW.md`, `DEVELOPMENT_LOG.md`), including this entry.
- **How:** `git add docs/workspace` (a named path; nothing else staged), then `git commit`. The message follows D-152:
  it names no AI tool. These docs were written with Claude Code; record that in `docs/AI_USAGE.md` when the branch goes
  to `main` by pull request.
- **Checked before committing:**
  - no keys, tokens, email addresses or local user paths in the six files (pattern scan)
  - branch was `sepehr/ui-ux-development`
  - nothing else untracked or modified
- **Not done:** no push (the branch still has no upstream), no change outside `docs/workspace/`.

---

## 2026-11-13 (evening): Git history attached, guard rails, personal branch (no application code changed)

**Approved by the user:** "Approve Git setup" (attach history, guard rails, local branch, no push).

- **What:** the working copy became a Git repository at the exact verified commit `c5e4ac81` (tag
  `package-20261111-1611`), without writing any project file.
  - `origin` = `https://github.com/danialrafiee-2007/iWISE-project.git`
  - `main` tracks `origin/main`
  - a local branch **`sepehr/ui-ux-development`** was created at `c5e4ac81` and is checked out
- **Guard rails:** `.git/hooks/pre-push` blocks any push to `refs/heads/main`; local config `push.default=current` and
  `branch.main.pushRemote=no_push`.
- **Files:** only `.git/` was created. No tracked or untracked project file changed. This log and
  `GIT_WORKFLOW.md`, `PROJECT_CONTEXT.md` and `Edit_IWISE_Project\CLAUDE.md` were updated afterwards.
- **Incident:** the first `git fetch` failed (`fetch-pack: invalid index-pack output`). Nothing was changed by it; the
  broken temporary pack in `.git/objects/pack` was removed and the retry succeeded.
- **Verified:**
  - HEAD `c5e4ac81`; tree `3e9f6524…` equals the commit tree
  - 433 tracked files, empty `git diff`
  - `git status` shows only `?? docs/workspace/`
  - 0 project files with a modification time after the start (19:20)
  - the hook was tested offline (main blocked, personal branch allowed)
  - GitHub still has only `main` at `c5e4ac81`
- **Not done:** no commit, no push, `docs/workspace/` not committed (the user's decision), no install, no UI change.

---

## 2026-11-13: Phase 1, workspace created (no application code changed)

**Done by:** Claude Code at the user's request (Phase 1 brief, resumed once after a session limit).

### What was done

1. **Investigated the source** at `A:\Apps\IWISI_London\iWISE_Truth Guardian\TruthGuardian`, read-only.
   - It is the ready-made package, build `20261111-1615-e88d666b`; there is no `.git`.
   - All 433 tracked files are byte-identical to GitHub commit `c5e4ac81` (tag `package-20261111-1611`). I compared Git
     blob hashes against GitHub's tree.
2. **Copied it** to `A:\Apps\IWISI_London\Edit_IWISE_Project\TruthGuardian`:
   - command: `robocopy /E /COPY:DAT /DCOPY:DAT /XJ /XD <src>\.venv /R:2 /W:2 /MT:16`
   - no `/MIR`, `/PURGE` or `/MOVE`; the source was only read
   - robocopy exit code 1 = "files copied, no failures": 35,963 files, 6.408 GB, 0 failed, 1 directory skipped
     (`.venv`)
3. **Verified the copy:**
   - SHA-256 of every file in both trees, sorted by relative path: the two manifests are **identical** (35,963 lines;
     manifest hash `f2b84f05…` on both sides)
   - directories: 3,822 on both sides (excluding `.venv`); empty directories 1 = 1
   - timestamps preserved (for example `README.md` 2026-11-11 15:50:34 on both)
   - source: no file (outside `.venv`) modified on 2026-11-13 **at verification time**; see "Resume check" for a later
     run of the app
   - `Edit_IWISE_Project\video` untouched (its folder timestamp is still 2026-11-10)
4. **Re-checked after resuming**, without a second full hash:
   - copy file count, and files modified after the copy (2026-11-13 14:27)
   - source file count, and files or folders modified on 2026-11-13
   - result: see the section "Resume check" below
5. **Git dry run** in a scratch repository (in the session scratchpad, not in the working copy), with the working copy
   as its work tree:
   - 433 files staged, tree `3e9f6524448bd131117692823805141795afce75`, which is exactly the tree of `c5e4ac81`
   - nothing outside `.gitignore` is untracked
   - the working copy still has no `.git`
6. **Wrote the workspace knowledge docs** in `docs/workspace/` (this folder): `PROJECT_CONTEXT.md`,
   `ARCHITECTURE.md`, `UI_UX_GUIDE.md`, `COMPONENT_MAP.md`, `GIT_WORKFLOW.md`, `DEVELOPMENT_LOG.md`.
7. **Added `A:\Apps\IWISI_London\Edit_IWISE_Project\CLAUDE.md`**, outside the repository, which points future sessions
   at these docs and the working rules.

### Excluded from the copy, and why

| Excluded | Size | Why | Consequence |
|---|---|---|---|
| `.venv/` (33,015 files) | 108 MB | Its `pyvenv.cfg` holds the absolute path of the **source's** Python (`...\iWISE_Truth Guardian\TruthGuardian\runtime\python\...`). Used from the copy, it would run the source's interpreter, which could write `__pycache__` into the source. | `TruthGuardian.bat` detects the missing or foreign `.venv` (`:env_check`) and rebuilds it **offline** from `runtime/uv-cache` (`:env_build`, about a minute). That rebuild is an environment build, so it waits for authorization. |
| Junctions (`/XJ`) | — | None were found; the flag guards against links pointing back into the source | — |

No secret files existed to exclude (no `*.local.env`, `.env` or keys in the source).

### Not done (by instruction)

- No `git init`, branch, commit or push.
- No dependency install, and no `.venv` rebuild.
- No UI or code change.

### Resume check (after the interruption, 2026-11-13)

- **Working copy:** 35,963 files, and **0** files modified after the copy finished (14:27), so it is unchanged since
  verification. A full re-hash was not repeated because there was no sign of change.
- **Source:** one file appeared after verification, `runtime/logs/activity-2026-11-13.jsonl` (5 KB, written from
  15:00 to 16:17). In addition, 37 `__pycache__` files were written in the source's `.venv` (spaCy language packs and
  transformers models, 16:16–16:17).
  - The log's own first row is "server started" at 15:00. It then records `/api/ask`, `/api/model-card`,
    `/api/examples`, `/api/fool/*` and `/api/learned` requests.
  - So **the source app was started and used outside this session** (I never launched it).
  - No tracked code, data or model file changed: the only file outside `.venv` modified after 14:34 is that log.
- **Takeaway:** running `TruthGuardian.bat` in the source writes runtime files into it (logs, `__pycache__`, and
  possibly the library and caches). To keep the source pristine, run the app from the working copy once its `.venv`
  rebuild is authorized. The working copy deliberately does not get the source's later log: it is a snapshot of the
  verified state.
