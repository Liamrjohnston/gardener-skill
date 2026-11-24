#!/usr/bin/env bash
# Gardener: copies the skill into your Claude Code skills folder.
# Usage, from inside this folder:  bash install.sh
# It does not switch on any nightly run. That is your call (see the README).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DEST_ROOT="${HOME}/.claude/skills"
mkdir -p "$DEST_ROOT"
src="$ROOT/gardener"
[ -f "$src/SKILL.md" ] || { echo "Can't find the skill. Run this from inside the Gardener folder." >&2; exit 1; }
dest="$DEST_ROOT/gardener"
if [ -e "$dest" ]; then
  read -r -p "There's already a gardener skill at $dest. Replace it? [y/N] " ok
  case "$ok" in
    y|Y)
      # Nothing is deleted: the old copy is moved aside.
      # (Kept outside the skills folder so Claude Code does not load two copies.)
      mkdir -p "${HOME}/.claude/skills-backup"
      old="${HOME}/.claude/skills-backup/gardener-$(date +%Y%m%d-%H%M%S)"
      mv "$dest" "$old"
      echo "Moved your old copy to $old"
      ;;
    *) echo "Left it as it is."; exit 0 ;;
  esac
fi
mkdir -p "$dest"
# Copy the skill, leaving out Python cache files.
(cd "$src" && tar --exclude='__pycache__' --exclude='*.pyc' -cf - .) | (cd "$dest" && tar -xf -)
echo "Installed gardener to $dest"
echo "Start a new Claude Code session, then type /gardener. Nothing runs on its own until you schedule it."
