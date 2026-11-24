# Gardener

A Claude Code skill for anyone who keeps a folder of notes that Claude reads: a CLAUDE.md, memory files, an Obsidian vault, project docs. Those files grow too long, links break when files move, empty stubs pile up, and old rules go stale. Claude reads them before every job, so it ends up working from old or missing pages.

Gardener checks the folder, writes one short report, and fixes only what it can prove. It never deletes anything.

## The three rules

1. **Keep every file Claude reads short.** Anything Claude loads each session (CLAUDE.md, AGENTS.md, MEMORY.md and files you list) is flagged when it goes over 2,000 estimated tokens. You can change the cap.
2. **Fix dead links the same night.** If a link points to a file that moved, and that filename exists exactly once elsewhere in the folder, Gardener rewrites the link after saving a backup. If it is not certain, it tells you instead.
3. **Never let it delete. Make it ask.** Gardener has no delete in it. Empty files, old inbox items and idle projects come back as proposals you say yes or no to.

## What it checks

- Broken `[[wiki links]]` and relative markdown links
- Files Claude reads every session that are over the token cap
- Empty files
- Inbox items older than 7 days (only if you have an `inbox/` folder)
- Projects with no changes for 14 days (only if you have a `projects/` folder)

## Install

One step, in a terminal:

```
git clone https://github.com/Liamrjohnston/gardener-skill gardener-skill && bash gardener-skill/install.sh
```

Or paste the repo link into Claude Code and say "install this skill". It copies the skill into `~/.claude/skills` and asks before replacing anything (your old copy is moved aside, never deleted). Then start a new Claude Code session and type `/gardener`.

## Run it

Inside Claude Code, type `/gardener` in your notes folder. Or run the script yourself:

```
python3 ~/.claude/skills/gardener/scripts/gardener.py "/path/to/your/notes"
```

Add `--dry-run` to see the report without changing or writing anything. Add `--no-fix` to report only. Add `--cap 3000` to change the token cap, and `--read "rules/*.md"` to name more files Claude reads.

The report is saved in `.gardener/` inside your folder as `report-<date>.md`. The top says, in plain English, how many links were fixed and how many things need your call. Each finding below it has its path and a proposed fix.

## What it fixes by itself

Only broken links where the target file moved. It does this when all of these hold:

- the file name exists exactly once elsewhere in the folder
- the file with the broken link has not been edited in the last hour
- a backup copy is saved first, in `.gardener/backups/<date-time>/`
- the change (old to new) is logged in `.gardener/fix-log.md`

To undo a fix, copy the backup file back over the original.

## What it never does

- Never deletes or overwrites a file without a backup, and never deletes at all
- Never edits a file you changed in the last hour
- Never touches anything outside the folder you point it at (it does not follow links out of the folder)
- Never guesses between two matches
- Never makes a network call, and sends nothing anywhere
- Needs only Python 3, nothing to install

## Switch on the nightly run

It ships off. Nothing runs until you do one of these.

**cron (Mac or Linux).** Run `crontab -e` and add one line (every night at 2:00):

```
0 2 * * * python3 "$HOME/.claude/skills/gardener/scripts/gardener.py" "/full/path/to/your/notes" >/dev/null 2>&1
```

**launchd (Mac).** Save this as `~/Library/LaunchAgents/local.gardener.plist`, replace YOUR_HOME with your home folder (run `echo $HOME` to see it) and change the folder path, then run `launchctl load ~/Library/LaunchAgents/local.gardener.plist`. To switch it off, run `launchctl unload` on the same file.

```
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.gardener</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string>
    <string>YOUR_HOME/.claude/skills/gardener/scripts/gardener.py</string>
    <string>/full/path/to/your/notes</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>2</integer><key>Minute</key><integer>0</integer></dict>
</dict></plist>
```

**Claude Code scheduled task.** In Claude Code, ask it to set up a scheduled task that runs `/gardener` on your notes folder every night at 2:00, and read you the report. Check that the task is the one you asked for before you accept it.

A computer that is asleep at 2:00 skips the run. Pick a time it is awake.

## Limits

The token count is an estimate (characters divided by four), close enough to catch files that are far too long. Gardener checks links, not whether what a file says is still true; that part is still yours. It checks `.md` links only.

MIT licence.
