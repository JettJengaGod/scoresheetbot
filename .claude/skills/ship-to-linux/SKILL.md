---
name: ship-to-linux
description: Ships the current work to the Linux server branch. Pushes it to master, merges master into the linux branch, and resolves any merge conflicts in the linux branch's own style (flat imports, Linux paths). Use when the user asks to ship, release or deploy to Linux, or to update the linux branch from master.
disable-model-invocation: true
---

# Ship to Linux

The bot runs on the server from the `linux` branch. That branch is `master` plus a fixed set of changes that
make it run there, and it is kept up to date by merging `master` into it (its history is a long run of
"Merge branch 'master' into linux" commits). This skill does that whole release:

1. push the work to `master`;
2. merge `master` into `linux`;
3. resolve the conflicts, and fix anything that merged cleanly but breaks the linux style;
4. check and push `linux`.

Never force-push, rebase or amend either branch, and never resolve a conflict by dropping master's
behaviour. If anything below fails and you can't fix it safely, stop and tell the user what is wrong,
leaving the branches as they were.

## 1. Push to master

```
git status                      # must be clean; commit or ask about anything uncommitted
git fetch origin
```

Note the branch you started on (`START`), so you can return to it at the end. Copy `sweep.sh` from this
skill's folder to `/tmp/linux-sweep.sh` now: the branches you switch to may not have the skill's folder.

- If `START` is `master`: `git pull --ff-only origin master`, then `git push origin master`.
- Otherwise, merge it in:
  ```
  git checkout master
  git pull --ff-only origin master
  git merge --no-edit START
  ```
  Resolve any conflicts here the normal way: this is master, so master's own style applies, not the
  linux one. Then run the tests (`python -m pytest tests`) if they can run on this machine, and push:
  `git push origin master`.

If the push is rejected because master moved, pull again (`git pull --no-rebase origin master`), re-check,
and push. Don't force.

## 2. Merge master into linux

```
git checkout linux
git pull --ff-only origin linux
```

Before merging, record the master-style lines linux already has, so the sweep in step 3 only fixes what the
merge brings in:

```
bash /tmp/linux-sweep.sh > /tmp/linux-sweep-before.txt
git merge --no-edit master       # message: "Merge branch 'master' into linux"
```

If it merges with no conflicts, still do the style sweep in step 3: code that merged cleanly can still use
master's imports or paths, and that breaks the server.

## 3. Resolve in the linux style

List the conflicts with `git diff --name-only --diff-filter=U`. For each conflict, keep **master's logic**
(that is the change being shipped) written in **linux's style**. Keep any change that exists only on
`linux` and isn't one of the style points below (for example the early `return` in `countdown`), unless
master changed that same code on purpose.

Look at the linux side of the file (`git show linux:<path>`) to match how it does things. The linux style:

- **Flat imports.** `src/` is the import root on the server, so modules import each other by bare name:
  - `from .helpers import x` and `from src.helpers import x` → `from helpers import x`
  - `from .constants import *` → `from constants import *`
  - `import src.cache` with `src.cache.Cache` → `from cache import Cache` with `Cache`
  - `from src import battle_store` → `import battle_store`
  - the same inside `if TYPE_CHECKING:` blocks
  - `src/main.py` does `from scoreSheetBot import main`
- **Paths relative to the project folder** (the bot is started from the project root by `startup.sh`), never
  `C:/...` Windows paths:
  - `'database.ini'`, `'client_key.json'`, `'token.pickle'`, `'credentials.json'`
  - images: `f'./src/img/{name}.png'`
  - the bracket font: `'/usr/local/share/fonts/SquadaOne-Regular.ttf'`
- **`src/db_config.py`** uses `SafeConfigParser` and `filename='database.ini'`. Keep linux's version of
  those lines.
- **`src/scoreSheetBot.py`** has no `if __name__ == '__main__':` block at the end; `main.py` starts the bot.
- **Linux-only files:** keep the linux versions of `startup.sh`, `update.sh` and `Pipfile.lock`. If master
  deleted or changed one, keep linux's anyway. Don't bring back `src/font/SquadaOne-Regular2.ttf`, which
  linux deleted.
- **New files from master** in `src/` get the same treatment: flat imports, linux paths.

Then sweep the whole tree for master style that merged cleanly, and compare with what linux had before:

```
bash /tmp/linux-sweep.sh > /tmp/linux-sweep-after.txt
diff /tmp/linux-sweep-before.txt /tmp/linux-sweep-after.txt
```

Fix every line the merge added (`>` in the diff), in the style above. Leave the lines linux already had:
it still has a few `src.` imports (in `bracket.py` and `sheet_helpers.py`) and a relative import under
`TYPE_CHECKING` in `cache.py`. They work on the server because `main.py` puts the project folder on the
path, and changing them isn't part of a release. `tests/` imports `src.` and is left as it is on linux.
The sweep prints file and pattern without line numbers, so code moving around doesn't show up as new.

## 4. Check and push linux

```
grep -rnE "^(<<<<<<<|=======|>>>>>>>)" src *.sh *.md      # no conflict markers left
python -m py_compile src/*.py                            # every module still compiles
```

If `client_key.json` and the dependencies are present, also check that the bot imports the way the
server runs it, from the project root: `python -c "import sys; sys.path.insert(0, 'src'); import scoreSheetBot"`.

Read over the merge against linux (`git diff --cached HEAD` while the merge is in progress, or
`git diff HEAD~1` once it is committed) and check every hunk: master's logic, linux's style, nothing of
linux's lost. Then stage the files you resolved or fixed by name (not `git add -A`, which picks up stray
files such as images left by a test run) and finish:

```
git add <files>
git commit --no-edit             # if the merge stopped for conflicts; otherwise commit the sweep fixes
git push origin linux
git checkout START
```

If the merge went through cleanly and the sweep found things to fix, commit those fixes separately, e.g.
"Use flat imports and Linux paths for the code merged from master".

## 5. Report

Tell the user, briefly:
- what went to master (the commits merged, or "already up to date");
- the linux merge commit, and each conflict or style fix with how you resolved it;
- anything you weren't sure about, or checks you couldn't run (such as the import check without
  `client_key.json`).

Pushing only updates the branch on GitHub. Remind the user that on the server they should run
`git checkout linux && git pull` and restart the bot. The server's `update.sh` merges its local `master`
into its local `linux` instead of pulling `linux`, so it would redo the merge there without the
resolutions made here, and stop at the same conflicts.
