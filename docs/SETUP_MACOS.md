# macOS Setup — read this before running anything

This project requires **Python 3.11 or newer** (it uses `str | None` union-type syntax
throughout). Many Macs ship with an older system Python or a conda `base` environment
pinned to Python 3.9, which fails with a confusing error — not "wrong Python version,"
but:
**If you see that error, this document is the fix — do not try to "fix" the code.**
The code is correct; the Python interpreter running it is too old.

---

## One-time setup (do this once per machine)

### 1. Check what Python versions exist

```bash
which -a python3
python3 --version
```

If you see `/usr/bin/python3` and it reports 3.9.x, that's the problem — it's macOS's
old bundled Python, not a real dev environment. Conda's `base` environment often uses
this same old version.

### 2. Install Python 3.12 via Homebrew (skip if you already have 3.11+)

```bash
brew install python@3.12
```

This installs to `/opt/homebrew/bin/python3.12` and does **not** touch your system
Python or your conda `base` environment — it sits alongside them.

If `brew` itself is not found:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 3. Create a project-local virtual environment

**Do this inside `backend/`, not at the repo root:**

```bash
cd ~/Projects/shios/backend
/opt/homebrew/bin/python3.12 -m venv venv
```

This creates a `venv/` folder scoped to this project only. It never conflicts with
conda, with other projects, or with system Python.

### 4. Activate it and install dependencies

```bash
source venv/bin/activate
pip install -r requirements-dev.txt
```

Your shell prompt should now show `(venv)` instead of `(base)`.

### 5. Verify

```bash
python -m pytest --tb=no 2>&1 | tail -2
```

Expect something like `73 passed` (the exact count grows as features are added — see
`docs/TESTING.md` for the current baseline).

---

## Every time you open a new terminal

Conda's `base` environment activates automatically on most Macs. You must switch to
this project's virtual environment every session:

```bash
cd ~/Projects/shios/backend
source venv/bin/activate
```

Your prompt changes from `(base)` to `(venv)` when it's active. If you forget this
step, `pytest`, `python`, `pip`, `uvicorn`, and `alembic` all silently fall back to
conda's Python 3.9 and you'll see the union-type error again.

**To make this automatic** (optional, recommended once you're comfortable with the
manual version): add this to `~/.zshrc`, which auto-activates the venv whenever you
`cd` into the project:

```bash
# Add near the end of ~/.zshrc
autoload -U add-zsh-hook
_shios_auto_venv() {
  if [[ "$PWD" == "$HOME/Projects/shios/backend"* ]] && [[ -z "$VIRTUAL_ENV" ]]; then
    source "$HOME/Projects/shios/backend/venv/bin/activate"
  fi
}
add-zsh-hook chpwd _shios_auto_venv
_shios_auto_venv  # run once for the current shell too
```

Reload with `source ~/.zshrc`, then `cd` into `backend/` — it activates on its own
from then on.

---

## Where the project must live

Do **not** keep this project inside `~/Desktop` or `~/Documents` if iCloud Drive sync
("Desktop & Documents Folders") is turned on. iCloud will create duplicate files
(`config 2.py`, `Dockerfile 3`, etc.) whenever many files change quickly, such as
during a `tar -xzf` extraction or a fast series of edits.

**Keep the project at `~/Projects/shios`** (outside any iCloud-synced folder), or turn
off iCloud sync for Desktop & Documents in **System Settings → Apple ID → iCloud →
iCloud Drive → Options**.

If you ever see files with a trailing number in their name that you didn't create,
that is the iCloud duplication bug, not a code problem — delete the numbered copies,
keep the originals, and move the project out of Desktop/Documents if it isn't already.

---

## Quick reference

| Symptom | Cause | Fix |
|---|---|---|
| `TypeError: Unable to evaluate type annotation 'str \| None'` | Python < 3.11 | `source venv/bin/activate` (see above) |
| `zsh: command not found: pip` | conda/venv not activated | `source venv/bin/activate` |
| Files like `config 2.py` appearing | iCloud sync duplicating files | Move project out of `~/Desktop`/`~/Documents`; delete numbered copies |
| `fatal: 'origin' does not appear to be a git repository` | remote not configured in this clone | `git remote add origin https://github.com/strategichonesty-2026/SHIOS---Ai-Intelligence-Software.git` |
| `! [rejected] main -> main (non-fast-forward)` | GitHub has commits you don't have locally | `git pull origin main --rebase` then `git push` |
| `fatal: bad object refs/heads/main 2` | Local repo corrupted (usually from iCloud interference) | Abandon the folder; `git clone` fresh into `~/Projects/shios` |
