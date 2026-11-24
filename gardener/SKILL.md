---
name: gardener
description: Check a folder of notes that Claude reads (CLAUDE.md, memory files, an Obsidian vault, project docs) for broken links, files that have grown too long, empty files, old inbox items and idle projects. Writes one short dated report. Fixes only links it can prove were moved (after saving a backup) and proposes everything else. Never deletes anything. Use when the user says gardener, tidy my notes, check my CLAUDE.md, find broken links, or asks to set up the nightly check.
version: 1.0.0
---

# Gardener

Claude reads your notes before every job. When those files grow too long, link to pages that moved, or sit empty, Claude works from old or missing pages. This skill checks the folder, writes a short report, and fixes only what it can prove.

## Rules that never bend

1. **Never delete.** Not a file, not a line. Anything that needs removing is a proposal the user answers yes or no to.
2. **Fix only provable moved links.** A broken link is rewritten only when its target filename exists exactly once elsewhere in the folder. Two matches, or none, means a proposal, not a fix.
3. **Back up first.** Before a file is changed, a copy goes to `.gardener/backups/<date-time>/` inside the folder, and the change is logged in `.gardener/fix-log.md`.
4. **Skip files edited in the last hour.** The user may be mid-edit.
5. **Stay inside the folder.** Nothing outside it is written or moved. No network.
6. **Proposals need a yes.** If the user says yes to a proposal, make that one change, with a backup copy first, and say what you changed.

## Run it

The script sits next to this file. Run it on the folder the user means (default: the current project):

```
python3 ~/.claude/skills/gardener/scripts/gardener.py "<folder>"
```

Useful options:

- `--dry-run` prints the report and changes nothing. Offer this first if the user seems nervous.
- `--no-fix` reports only, rewrites no link.
- `--cap 3000` changes the token cap (default 2,000 estimated tokens, about 4 characters each).
- `--read "rules/*.md"` adds files Claude reads every session. `CLAUDE.md`, `AGENTS.md` and `MEMORY.md` are always checked. Repeat the option for more. The same settings can live in a `.gardener.json` file at the top of the folder: `{"cap": 2000, "read": ["rules/*.md"], "inbox_days": 7, "idle_days": 14}`.

If Claude Code runs from a different folder than the notes, pass the notes folder explicitly.

## What to do after it runs

1. Read the report it printed (also saved at `.gardener/report-<date>.md`).
2. Tell the user, in plain English: how many links were fixed, how many things need a decision, and the two or three that matter most. Lead with the counts.
3. For each proposal, say what you would do in one sentence and ask. For a file over the cap, offer to move the detail into a linked file and keep the top short, showing the exact split first.
4. Never apply a proposal without a yes on that item.

## Set up the nightly run (only if the user asks)

It is off until the user switches it on. Show the options from the README and let them pick:

- cron, one line (every night at 2:00): `0 2 * * * python3 "$HOME/.claude/skills/gardener/scripts/gardener.py" "/full/path/to/notes" >/dev/null 2>&1`
- macOS launchd: a small plist, shown in the README.
- A Claude Code scheduled task: ask Claude Code to run `/gardener` on the notes folder every night.

Never add a cron entry or plist yourself without the user saying yes to that exact line and folder.
