#!/usr/bin/env python3
"""Gardener: a nightly tidy-up check for a folder of notes that Claude reads.

    python3 gardener.py [FOLDER] [--cap 2000] [--read PATH_OR_GLOB ...] [--dry-run] [--no-fix]

It finds broken links, files that are too long, empty files, old inbox items and idle
projects, writes one short dated report, and fixes only links it can prove were moved.
It never deletes anything, never touches anything outside FOLDER, and makes a backup
copy before it changes a file. Python 3 standard library only. No network.
"""
import argparse
import datetime as dt
import fnmatch
import json
import math
import os
import re
import shutil
import sys
import time
import urllib.parse

sys.dont_write_bytecode = True

STATE_DIR = ".gardener"
SKIP_DIRS = {".git", "node_modules", ".obsidian", ".trash", ".venv", "__pycache__", STATE_DIR}
DEFAULT_READ = ["CLAUDE.md", "AGENTS.md", "MEMORY.md"]
DEFAULTS = {"cap": 2000, "read": [], "inbox_days": 7, "idle_days": 14, "recent_minutes": 60}
IGNORE_EMPTY = {".gitkeep", ".keep", "__init__.py", ".DS_Store"}

WIKI = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
MDLINK = re.compile(r"(!?)\[([^\]\n]*)\]\(([^)\n]+)\)")
FENCE = re.compile(r"^(```|~~~).*?^\1[ \t]*$", re.S | re.M)
INLINE = re.compile(r"`[^`\n]*`")
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def est_tokens(text):
    return math.ceil(len(text) / 4)


def mask_code(text):
    """Blank out code (same length) so links shown as examples are not checked."""
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))
    return INLINE.sub(blank, FENCE.sub(blank, text))


def inside(root, path):
    root = os.path.realpath(root)
    path = os.path.realpath(path)
    return path == root or path.startswith(root + os.sep)


def scan_files(root):
    """Every regular file inside root (relative paths), skipping state and tool folders and symlinks."""
    out = []
    for cur, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not os.path.islink(os.path.join(cur, d)))
        for f in sorted(files):
            p = os.path.join(cur, f)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            out.append(os.path.relpath(p, root))
    return out


class Index:
    def __init__(self, files):
        self.files = files
        self.set = set(files)
        self.by_name = {}
        self.by_stem = {}
        for rel in files:
            name = os.path.basename(rel)
            self.by_name.setdefault(name, []).append(rel)
            self.by_stem.setdefault(os.path.splitext(name)[0].casefold(), []).append(rel)
        self.names_cf = {n.casefold() for n in self.by_name}


def load_config(root):
    cfg = dict(DEFAULTS)
    p = os.path.join(root, ".gardener.json")
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
            for k in DEFAULTS:
                if k in data:
                    cfg[k] = data[k]
        except (OSError, ValueError):
            pass
    return cfg


def read_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def find_links(rel, text, root, idx):
    """Return broken links: dicts with kind, line, link, target, and an optional proposed edit."""
    masked = mask_code(text)
    broken = []
    here = os.path.dirname(rel)

    def line_of(pos):
        return text.count("\n", 0, pos) + 1

    for m in WIKI.finditer(masked):
        inner = m.group(2)
        tm = re.match(r"[^|#^]*", inner)
        target = tm.group(0).strip()
        if not target:
            continue
        t = target.replace("\\", "/")
        ok = False
        if "/" in t:
            cands = [t, t + ".md", os.path.normpath(os.path.join(here, t)), os.path.normpath(os.path.join(here, t)) + ".md"]
            ok = any(c in idx.set for c in cands) or any(f.endswith("/" + t + ".md") or f.endswith("/" + t) for f in idx.files)
        else:
            ok = t.casefold() in idx.names_cf or t.casefold() in idx.by_stem
        if ok:
            continue
        item = {"kind": "wiki", "line": line_of(m.start()), "link": m.group(0), "target": target, "fix": None, "why": None}
        if "/" in t:
            base = os.path.basename(t)
            fname = base if os.path.splitext(base)[1] else base + ".md"
            cands = idx.by_name.get(fname, [])
            if len(cands) == 1:
                new = cands[0][:-3] if cands[0].endswith(".md") and not base.endswith(".md") else cands[0]
                start = m.start(2) + tm.start()
                item["fix"] = (start, start + len(tm.group(0)), tm.group(0).replace(target, new, 1), cands[0])
            elif len(cands) > 1:
                item["why"] = "several files with that name: " + ", ".join(cands[:4])
            else:
                item["why"] = "no file with that name anywhere in the folder"
        else:
            item["why"] = "no note with that name anywhere in the folder"
        broken.append(item)

    for m in MDLINK.finditer(masked):
        raw = m.group(3)
        path_raw = raw
        tm = re.match(r'^(.*?)(\s+"[^"]*"|\s+\'[^\']*\')\s*$', raw)
        if tm:
            path_raw = tm.group(1)
        off = 0
        if path_raw.startswith("<") and path_raw.endswith(">"):
            path_raw, off = path_raw[1:-1], 1
        path_raw_s = path_raw.strip()
        if not path_raw_s or path_raw_s.startswith("#") or SCHEME.match(path_raw_s) or path_raw_s.startswith("//"):
            continue
        pm = re.match(r"[^#?]*", path_raw_s)
        pure = urllib.parse.unquote(pm.group(0))
        if not pure:
            continue
        lead = len(path_raw) - len(path_raw.lstrip())
        if pure.startswith("/"):
            res = os.path.normpath(pure.lstrip("/"))
        else:
            res = os.path.normpath(os.path.join(here, pure))
        if res.startswith(".."):
            continue  # points outside the folder: not ours to judge
        if res in idx.set or os.path.isdir(os.path.join(root, res)) or (res + ".md") in idx.set:
            continue
        item = {"kind": "markdown", "line": line_of(m.start()), "link": m.group(0), "target": pure, "fix": None, "why": None}
        cands = idx.by_name.get(os.path.basename(res), []) if os.path.basename(res) else []
        if len(cands) == 1:
            if pure.startswith("/"):
                newp = "/" + cands[0].replace(os.sep, "/")
            else:
                newp = os.path.relpath(cands[0], here or ".").replace(os.sep, "/")
            if "%" in pm.group(0):
                newp = urllib.parse.quote(newp, safe="/-_.~()")
            start = m.start(3) + off + lead
            item["fix"] = (start, start + len(pm.group(0)), newp, cands[0])
        elif len(cands) > 1:
            item["why"] = "several files with that name: " + ", ".join(cands[:4])
        else:
            item["why"] = "no file with that name anywhere in the folder"
        broken.append(item)
    return broken


def matches_read(rel, patterns):
    name = os.path.basename(rel)
    for p in patterns:
        if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) or rel == p.lstrip("./"):
            return True
    return False


def run(root, cap=None, read=None, dry_run=False, no_fix=False, now=None, out=None):
    root = os.path.realpath(root)
    cfg = load_config(root)
    if cap is not None:
        cfg["cap"] = cap
    patterns = list(DEFAULT_READ) + list(cfg["read"]) + list(read or [])
    now = time.time() if now is None else now
    today = dt.date.fromtimestamp(now).isoformat()
    stamp = dt.datetime.fromtimestamp(now).strftime("%Y%m%d-%H%M%S")

    files = scan_files(root)
    idx = Index(files)
    over, empty, broken, inbox, idle = [], [], [], [], []
    unreadable = []

    for rel in files:
        full = os.path.join(root, rel)
        size = os.path.getsize(full)
        name = os.path.basename(rel)
        text = None
        if rel.lower().endswith((".md", ".markdown", ".txt")):
            text = read_text(full)
        if name not in IGNORE_EMPTY and (size == 0 or (text is not None and not text.strip())):
            empty.append(rel)
            continue
        if text is None:
            continue
        if matches_read(rel, patterns):
            tok = est_tokens(text)
            if tok > cfg["cap"]:
                over.append((rel, tok))
        if rel.lower().endswith((".md", ".markdown")):
            for b in find_links(rel, text, root, idx):
                b["file"] = rel
                broken.append(b)

    # inbox items and idle projects, only if those folders exist
    for d in os.listdir(root):
        full = os.path.join(root, d)
        if os.path.isdir(full) and not os.path.islink(full) and d.lower() == "inbox":
            for rel in files:
                if rel.startswith(d + os.sep):
                    age = (now - os.path.getmtime(os.path.join(root, rel))) / 86400
                    if age > cfg["inbox_days"]:
                        inbox.append((rel, int(age)))
        if os.path.isdir(full) and not os.path.islink(full) and d.lower() == "projects":
            for p in sorted(os.listdir(full)):
                pdir = os.path.join(full, p)
                if not os.path.isdir(pdir) or p in SKIP_DIRS:
                    continue
                newest = 0
                for rel in files:
                    if rel.startswith(os.path.join(d, p) + os.sep):
                        newest = max(newest, os.path.getmtime(os.path.join(root, rel)))
                if newest:
                    age = (now - newest) / 86400
                    if age > cfg["idle_days"]:
                        idle.append((os.path.join(d, p), int(age)))

    # fixes: only provable moved links, backup first, skip recent files
    fixed, skipped_recent, proposals = [], [], []
    by_file = {}
    for b in broken:
        by_file.setdefault(b["file"], []).append(b)
    backup_dir = os.path.join(root, STATE_DIR, "backups", stamp)
    for rel, items in by_file.items():
        full = os.path.join(root, rel)
        fixable = [b for b in items if b["fix"]]
        for b in items:
            if not b["fix"]:
                proposals.append(b)
        if not fixable:
            continue
        recent = (now - os.path.getmtime(full)) < cfg["recent_minutes"] * 60
        if no_fix or recent:
            for b in fixable:
                b["why"] = ("file edited in the last %d minutes, left alone" % cfg["recent_minutes"]) if recent else "fixing is switched off (--no-fix)"
                (skipped_recent if recent else proposals).append(b)
            continue
        if dry_run:
            for b in fixable:
                fixed.append((rel, b, None, True))
            continue
        text = read_text(full)
        if text is None:
            continue
        bpath = os.path.join(backup_dir, rel)
        if not inside(root, bpath):
            continue
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        shutil.copy2(full, bpath)
        new_text = text
        for b in sorted(fixable, key=lambda x: -x["fix"][0]):
            s, e, newtxt, _ = b["fix"]
            new_text = new_text[:s] + newtxt + new_text[e:]
        tmp = full + ".gardener-tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
        shutil.copystat(full, tmp)
        os.replace(tmp, full)
        # keep the file's old edit time so the fix does not look like a fresh human edit
        for b in fixable:
            fixed.append((rel, b, os.path.relpath(bpath, root), False))
        os.makedirs(os.path.join(root, STATE_DIR), exist_ok=True)
        with open(os.path.join(root, STATE_DIR, "fix-log.md"), "a", encoding="utf-8") as lg:
            for b in fixable:
                lg.write("%s | %s | line %d | %s -> %s | backup: %s\n" % (
                    today, rel, b["line"], b["target"], b["fix"][3], os.path.relpath(bpath, root)))

    report = build_report(root, today, cfg, over, empty, proposals, skipped_recent, fixed, inbox, idle, len(files), dry_run)
    path = None
    if not dry_run:
        os.makedirs(os.path.join(root, STATE_DIR), exist_ok=True)
        path = os.path.join(root, STATE_DIR, "report-%s.md" % today)
        n = 2
        while os.path.exists(path):
            path = os.path.join(root, STATE_DIR, "report-%s-%d.md" % (today, n))
            n += 1
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(report)
    return {"report": report, "path": path, "over": over, "empty": empty, "broken": broken,
            "proposals": proposals, "skipped_recent": skipped_recent, "fixed": fixed, "inbox": inbox, "idle": idle}


def plural(n, one, many=None):
    return "%d %s" % (n, one if n == 1 else (many or one + "s"))


def build_report(root, today, cfg, over, empty, proposals, skipped, fixed, inbox, idle, nfiles, dry):
    L = []
    L.append("# Gardener report, %s%s" % (today, " (dry run, nothing changed)" if dry else ""))
    L.append("")
    nbroken = len(proposals) + len(skipped) + len(fixed)
    L.append("Checked %s." % plural(nfiles, "file"))
    L.append("- %s %s." % (plural(len(fixed), "broken link"), "would be fixed" if dry else "fixed tonight (backups saved)"))
    L.append("- %s left for you to decide." % plural(len(proposals) + len(skipped), "broken link"))
    L.append("- %s over the %s-token cap." % (plural(len(over), "file Claude reads", "files Claude reads"), format(cfg["cap"], ",")))
    L.append("- %s." % plural(len(empty), "empty file"))
    L.append("- %s older than %d days." % (plural(len(inbox), "inbox item"), cfg["inbox_days"]))
    L.append("- %s idle for more than %d days." % (plural(len(idle), "project"), cfg["idle_days"]))
    if not (nbroken or over or empty or inbox or idle):
        L.append("")
        L.append("All clear. Nothing to fix and nothing to decide.")
    L.append("")
    L.append("Nothing was deleted. Anything below marked Proposal needs your yes.")
    if fixed:
        L.append("")
        L.append("## %s" % ("Links I would fix" if dry else "Links fixed (moved files, proved by an exact filename match)"))
        for rel, b, bk, _ in fixed:
            L.append("- `%s` line %d: `%s` -> `%s`%s" % (rel, b["line"], b["target"], b["fix"][3],
                     "" if dry else " (backup: `%s`)" % bk))
        if not dry:
            L.append("")
            L.append("To undo any fix, copy the backup file back over the original. Every change is also logged in `%s/fix-log.md`." % STATE_DIR)
    if proposals or skipped:
        L.append("")
        L.append("## Broken links (Proposal)")
        for b in proposals + skipped:
            L.append("- `%s` line %d: `%s`. %s. Proposed fix: %s." % (
                b["file"], b["line"], b["target"], b["why"].capitalize() if b["why"] else "Not fixed",
                "point it at the right file, or remove the link" if not b["fix"] else "re-run after the hour has passed, or without --no-fix"))
    if over:
        L.append("")
        L.append("## Files Claude reads that are too long (Proposal)")
        for rel, tok in sorted(over, key=lambda x: -x[1]):
            L.append("- `%s`: about %s tokens, cap %s. Proposed fix: move the detail into a linked file and keep the top short." % (
                rel, format(tok, ","), format(cfg["cap"], ",")))
    if empty:
        L.append("")
        L.append("## Empty files (Proposal)")
        for rel in empty:
            L.append("- `%s`. Proposed fix: write what it is for in one line, or ask Claude whether to remove it." % rel)
    if inbox:
        L.append("")
        L.append("## Old inbox items (Proposal)")
        for rel, age in inbox:
            L.append("- `%s`: %d days old. Proposed fix: file it where it belongs, or decide to drop it." % (rel, age))
    if idle:
        L.append("")
        L.append("## Idle projects (Proposal)")
        for rel, age in idle:
            L.append("- `%s`: nothing changed for %d days. Proposed fix: mark it done, or write down the next step." % (rel, age))
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Nightly tidy-up check for a folder of notes Claude reads.")
    ap.add_argument("folder", nargs="?", default=".", help="folder to check (default: current folder)")
    ap.add_argument("--cap", type=int, default=None, help="token cap for files Claude reads (default 2000)")
    ap.add_argument("--read", action="append", default=[], metavar="PATH_OR_GLOB",
                    help="another file Claude reads every session; repeat for more. CLAUDE.md, AGENTS.md and MEMORY.md are always included")
    ap.add_argument("--dry-run", action="store_true", help="print the report, change and write nothing")
    ap.add_argument("--no-fix", action="store_true", help="report only; do not rewrite any link")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.folder):
        print("Not a folder: %s" % a.folder, file=sys.stderr)
        return 2
    r = run(a.folder, cap=a.cap, read=a.read, dry_run=a.dry_run, no_fix=a.no_fix)
    print(r["report"])
    if r["path"]:
        print("Report saved: %s" % r["path"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
