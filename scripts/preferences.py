#!/usr/bin/env python3
"""The person's own Patstack preferences: which models they have, how they rank them per job, and how they
want to work. Written by the start-here interview; read by agents through the global instructions.

  python3 scripts/preferences.py models [--json]      models this machine's clients offer (local catalogs)
  python3 scripts/preferences.py propose              recommended answers as JSON (the interview's defaults)
  python3 scripts/preferences.py show                 the saved preferences
  python3 scripts/preferences.py write [--apply] < answers.json
                                                      check answers; with --apply save them (backup first)
  python3 scripts/preferences.py notify --url URL --topic TOPIC [--host NAME] [--apply]
                                                      phone pings for status changes (tools/task_status.py)
  python3 scripts/preferences.py notify --off [--apply]   turn the pings off (the file is kept, renamed)

Model discovery reads the clients' own catalogs, with no network call and no model call:
Claude Code's ~/.claude/cache/model-catalog/*.json (section "main") and `codex debug models` (visibility
"list"; ~/.codex/models_cache.json when the command fails). A model a catalog lists is offered by the client;
whether the person's plan allows it shows only when it is used.

Preferences live in ~/.config/patstack/preferences.json (PATSTACK_PREFERENCES overrides), owner-only. They
choose among models and shape how agents talk and when they ask; they grant no permission and never lower a
review level, a safety rule or a human gate.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from start_here import Linked, backup, check_links, write_atomic  # noqa: E402  (same write rules as the setup)

VERSION = 1
JOBS = ("lead", "design", "implementation", "ui", "review")
JOB_HELP = {
    "lead": "owns a task end to end: coordination, integration, final report",
    "design": "frontend design and backend architecture",
    "implementation": "code, integrations, tests, analysis",
    "ui": "clicking through a real app to prove a UI works (needs a computer-use capable client)",
    "review": "independent review of someone else's change",
}
# MODEL_RANKING.md, as (provider, family) in order of preference per job.
DEFAULTS = {
    "lead": [("claude", "opus"), ("codex", "sol")],
    "design": [("claude", "opus"), ("claude", "fable"), ("codex", "sol")],
    "implementation": [("codex", "sol"), ("claude", "opus")],
    "ui": [("codex", "astra"), ("claude", "opus")],
    "review": [("codex", "sol"), ("claude", "opus")],
}
EFFORTS = ("low", "medium", "high", "xhigh", "max")
CHOICES = {
    "reports": ("short", "detailed"),
    "involvement": ("hands-off", "checkpoints"),
    "notify": ("none", "ntfy"),
}
LANGUAGE = re.compile(r"[a-z]{2,3}(-[A-Za-z]{2,4})?")
REF = re.compile(r"(claude|codex):[A-Za-z0-9._\[\]-]{1,64}")


def prefs_path(home):
    return Path(os.environ.get("PATSTACK_PREFERENCES") or home / ".config/patstack/preferences.json")


# ---------------------------------------------------------------- discovery

CLAUDE_ALIASES = (("opus", "Opus (latest)"), ("fable", "Fable (latest)"), ("sonnet", "Sonnet (latest)"),
                  ("haiku", "Haiku (latest)"))


def claude_models(home, which=shutil.which):
    """The catalog Claude Code caches. A fresh install has none until the client has run interactively; then,
    when Claude Code is installed, its model aliases, which always resolve to the newest model of a family."""
    found = []
    for path in sorted((home / ".claude/cache/model-catalog").glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            models = data["catalog"]["config"]["models"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        for m in models if isinstance(models, list) else []:
            if not isinstance(m, dict) or m.get("section") != "main" or not isinstance(m.get("id"), str):
                continue
            runtime = m.get("runtime") or {}
            found.append({"provider": "claude", "id": m["id"], "name": m.get("name") or m["id"],
                          "family": runtime.get("family") or family_of(m["id"]),
                          "efforts": [e for e in runtime.get("effort_levels") or [] if e in EFFORTS]})
    if not found and (which("claude") or (home / ".claude.json").exists()):
        found = [{"provider": "claude", "id": alias, "name": name, "family": alias, "efforts": [],
                  "alias": True} for alias, name in CLAUDE_ALIASES]
    return unique(found)


def codex_models(home, run=subprocess.run):
    data = None
    try:
        result = run(["codex", "debug", "models"], capture_output=True, text=True, timeout=60,
                     env=dict(os.environ, CODEX_HOME=os.environ.get("CODEX_HOME") or str(home / ".codex")))
        if result.returncode == 0:
            data = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        data = None
    if data is None:
        try:
            data = json.loads((home / ".codex/models_cache.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    models = data.get("models") if isinstance(data, dict) else data
    found = []
    for m in models if isinstance(models, list) else []:
        if not isinstance(m, dict) or m.get("visibility") != "list" or not isinstance(m.get("slug"), str):
            continue
        levels = [lvl.get("effort") for lvl in m.get("supported_reasoning_levels") or [] if isinstance(lvl, dict)]
        found.append({"provider": "codex", "id": m["slug"], "name": m.get("display_name") or m["slug"],
                      "family": family_of(m["slug"]), "efforts": [e for e in levels if e in EFFORTS]})
    return unique(found)


def family_of(model_id):
    """claude-opus-5-5 -> opus, gpt-6.1-sol -> sol: the word that names the line, not the version."""
    words = [w for w in re.split(r"[-_.]", model_id.lower()) if w.isalpha() and w not in ("claude", "gpt")]
    return words[-1] if words else model_id


def unique(models):
    seen, out = set(), []
    for m in models:
        if m["id"] not in seen:
            seen.add(m["id"])
            out.append(m)
    return out


def discover(home, run=subprocess.run, which=shutil.which):
    return claude_models(home, which) + codex_models(home, run)


def ref(model):
    return f"{model['provider']}:{model['id']}"


def version_key(model_id):
    """claude-opus-5-5 -> (5, 5), gpt-6.1-sol -> (6, 1): the version numbers in the id, for "newest"."""
    return tuple(int(n) for n in re.findall(r"\d+", model_id) if len(n) < 6)  # a date suffix is not a version


def save_private(home, path, text):
    """Owner-only (0600) also when replacing a wider file; links are checked before anything is read, backed
    up or written; the previous bytes are kept as a backup whether or not they parse."""
    check_links(home, path)
    saved = backup(path) if path.exists() else None
    write_atomic(home, path, text, 0o600, force_mode=True)
    return saved


# ---------------------------------------------------------------- proposal and validation

def propose(models):
    """Recommended answers: MODEL_RANKING.md's order, using the newest available model of each family, then
    every other available model, so each job has a complete ranking."""
    def newest(provider, family):
        candidates = [m for m in models if m["provider"] == provider and m["family"] == family]
        return ref(max(candidates, key=lambda m: version_key(m["id"]))) if candidates else None

    ranking = {}
    for job in JOBS:
        first = [r for r in (newest(p, f) for p, f in DEFAULTS[job]) if r]
        ranking[job] = first + [ref(m) for m in models if ref(m) not in first]
    providers = {m["provider"] for m in models}
    if len(providers) >= 2:
        pair = [r for r in (newest("claude", "opus"), newest("codex", "sol")) if r]
        if len(pair) < 2:  # no Opus or no Sol here: the first model of each provider
            pair = [next(ref(m) for m in models if m["provider"] == p) for p in ("claude", "codex")]
    else:
        pair = ranking["review"][:1]  # one provider: R2/R3 run as fresh sessions under the reviewer lenses
    return {"version": VERSION, "language": "en", "reports": "short", "involvement": "hands-off",
            "effort": {"default": "medium", "ceiling": "high"}, "notify": "none",
            "models": {"ranking": ranking, "reviewPair": pair}}


def problems(prefs, models):
    """Everything wrong with PREFS, as sentences; empty when it can be saved. Unknown models are allowed only
    when no catalog was found (an empty MODELS), so a typo cannot slip through on a machine that has one."""
    out = []
    if not isinstance(prefs, dict):
        return ["preferences must be a JSON object"]
    allowed = {"version", "updated", "language", "reports", "involvement", "effort", "notify", "models", "quiz"}
    out += [f"unknown key {k!r}" for k in sorted(set(prefs) - allowed)]
    if prefs.get("version") != VERSION:
        out.append(f"version must be {VERSION}")
    if not (isinstance(prefs.get("language"), str) and LANGUAGE.fullmatch(prefs["language"])):
        out.append("language must be a language code such as en or nb")
    for key, values in CHOICES.items():
        if prefs.get(key) not in values:
            out.append(f"{key} must be one of {', '.join(values)}")
    effort = prefs.get("effort")
    if not (isinstance(effort, dict) and effort.get("default") in EFFORTS and effort.get("ceiling") in EFFORTS
            and set(effort) <= {"default", "ceiling"}):
        out.append(f"effort needs default and ceiling, each one of {', '.join(EFFORTS)}")
    elif EFFORTS.index(effort["default"]) > EFFORTS.index(effort["ceiling"]):
        out.append("effort default must not be above the ceiling")
    quiz = prefs.get("quiz")
    if quiz is not None:
        ints = isinstance(quiz, dict) and all(isinstance(quiz.get(k), int) and not isinstance(quiz.get(k), bool)
                                              for k in ("score", "of"))
        if not (ints and set(quiz) == {"score", "of", "date"} and 1 <= quiz["of"] <= 20
                and 0 <= quiz["score"] <= quiz["of"] and isinstance(quiz["date"], str)
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", quiz["date"])):
            out.append("quiz must be {score, of, date} with 0 <= score <= of <= 20 and date YYYY-MM-DD")
    known = {ref(m): m for m in models}
    section = prefs.get("models")
    if not isinstance(section, dict) or set(section) != {"ranking", "reviewPair"}:
        return out + ["models needs exactly ranking and reviewPair"]
    ranking = section["ranking"]
    if not isinstance(ranking, dict) or set(ranking) != set(JOBS):
        out.append(f"models.ranking needs exactly the jobs {', '.join(JOBS)}")
        ranking = {}
    for job, order in ranking.items():
        if not (isinstance(order, list) and order and all(isinstance(r, str) and REF.fullmatch(r) for r in order)):
            out.append(f"ranking.{job} must be a non-empty list of provider:model")
            continue
        if len(set(order)) != len(order):
            out.append(f"ranking.{job} lists a model twice")
        if known:
            out += [f"ranking.{job}: {r} is not offered on this machine" for r in order if r not in known]
    pair = section["reviewPair"]
    if not (isinstance(pair, list) and 1 <= len(pair) <= 2 and all(isinstance(r, str) and REF.fullmatch(r) for r in pair)):
        out.append("reviewPair must list one or two provider:model")
    else:
        if known:
            out += [f"reviewPair: {r} is not offered on this machine" for r in pair if r not in known]
        if len(pair) == 2 and pair[0].split(":")[0] == pair[1].split(":")[0]:
            out.append("reviewPair needs two different providers; with one provider, list one model "
                       "(R2/R3 then run as fresh sessions under the reviewer lenses)")
        if len(pair) == 1 and len({m["provider"] for m in models}) >= 2:
            out.append("reviewPair has one model although two providers are available; list one of each")
    return out


# ---------------------------------------------------------------- commands

def load(home):
    path = prefs_path(home)
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        if path.is_symlink():
            raise ValueError("preferences path is a dangling link") from None
        return None
    if not stat.S_ISREG(mode):
        raise ValueError("preferences path is not a regular file")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def cmd_models(home, args, out):
    models = discover(home)
    if args.json:
        print(json.dumps(models, indent=2), file=out)
        return 0
    if not models:
        print("No model catalog found. Start claude and codex once, then rerun.", file=out)
        return 1
    for i, m in enumerate(models, 1):
        note = "  (alias: catalog not cached yet)" if m.get("alias") else ""
        print(f"{i:2}. {m['name']:<16} {ref(m):<32} family {m['family']:<8} effort {'/'.join(m['efforts']) or '-'}"
              f"{note}", file=out)
    return 0


def cmd_write(home, args, out, stdin):
    try:
        prefs = json.loads(stdin.read().lstrip("\ufeff"))
    except ValueError as error:
        print(f"not JSON: {error}", file=out)
        return 3
    models = discover(home)
    if not models:
        print("NOT SAVED: no model catalog on this machine, so the ranking cannot be checked. Start `claude` "
              "and/or `codex` once (logged in), then rerun.", file=out)
        return 3
    found = problems(prefs, models)
    if found:
        print("NOT SAVED:\n- " + "\n- ".join(found), file=out)
        return 3
    prefs["updated"] = datetime.date.today().isoformat()
    path = prefs_path(home)
    if not args.apply:
        print(f"OK: valid. DRY-RUN: would write {path}" + (" (replacing the saved file)" if path.exists() else ""),
              file=out)
        return 0
    try:
        saved = save_private(home, path, json.dumps(prefs, indent=2, ensure_ascii=False) + "\n")
    except Linked as error:
        print(f"NOT SAVED: {error}", file=out)
        return 3
    print(f"Saved {path}" + (f" (previous kept as {saved.name})" if saved else ""), file=out)
    return 0


def cmd_notify(home, args, out):
    """notify.json for tools/task_status.py: an ntfy server URL, a topic and this host's name. The topic is
    the only thing protecting the pings, so it is never printed."""
    path = Path(os.environ.get("PATSTACK_NOTIFY") or home / ".config/patstack/notify.json")
    if args.off:
        return notify_off(home, path, args.apply, out)
    if not (args.url and args.topic):
        print("NOT SAVED: give --url and --topic, or --off", file=out)
        return 3
    config = {"url": args.url, "topic": args.topic}
    if args.host:
        config["host"] = args.host
    bad = []
    if not re.fullmatch(r"https?://[^\s/?#]+(/[^\s?#]*)?", args.url or ""):
        bad.append("url must be an http(s) address of an ntfy server, for example https://ntfy.sh")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,58}", args.topic or ""):
        bad.append("topic must be 1-58 letters, digits, - or _ (a long random one: it is the only protection)")
    if args.host and not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", args.host):
        bad.append("host must be 1-32 letters, digits, - or _")
    if bad:
        print("NOT SAVED:\n- " + "\n- ".join(bad), file=out)
        return 3
    if not args.apply:
        print(f"OK: valid. DRY-RUN: would write {path} (topic not shown)", file=out)
        return 0
    try:
        saved = save_private(home, path, json.dumps(config, indent=2) + "\n")
    except Linked as error:
        print(f"NOT SAVED: {error}", file=out)
        return 3
    print(f"Saved {path} (topic not shown)" + (f"; previous kept as {saved.name}" if saved else ""), file=out)
    return 0


def notify_off(home, path, apply, out):
    """Turns pings off: notify.json is kept as notify.json.<time>.off (an exclusive copy, then the original is
    removed), so tools/task_status.py finds no server. Renaming the copy back turns them on again."""
    if not path.exists():
        print("OK: notifications are already off (no notify.json)", file=out)
        return 0
    try:
        check_links(home, path)
    except Linked as error:
        print(f"NOT CHANGED: {error}", file=out)
        return 3
    if not apply:
        print(f"DRY-RUN: would turn notifications off by renaming {path.name} to {path.name}.<time>.off", file=out)
        return 0
    target = backup(path, "off")  # an exclusive owner-only copy under a fresh name: never replaces another
    os.unlink(str(path))
    print(f"Notifications off: {path.name} kept as {target.name}", file=out)
    return 0


def main(argv=None, home=None, out=sys.stdout, stdin=sys.stdin):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("models").add_argument("--json", action="store_true")
    sub.add_parser("propose")
    sub.add_parser("show")
    sub.add_parser("write").add_argument("--apply", action="store_true")
    notify = sub.add_parser("notify")
    notify.add_argument("--url")
    notify.add_argument("--topic")
    notify.add_argument("--off", action="store_true", help="turn pings off (notify.json is kept, renamed)")
    notify.add_argument("--host")
    notify.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    home = Path(home or Path.home())
    if args.command == "models":
        return cmd_models(home, args, out)
    if args.command == "propose":
        print(json.dumps(propose(discover(home)), indent=2), file=out)
        return 0
    if args.command == "show":
        try:
            prefs = load(home)
        except (OSError, ValueError) as error:
            print(f"unreadable {prefs_path(home)}: {error}", file=out)
            return 1
        print(json.dumps(prefs, indent=2, ensure_ascii=False) if prefs else "No preferences yet: run /start-here.",
              file=out)
        return 0
    if args.command == "notify":
        return cmd_notify(home, args, out)
    return cmd_write(home, args, out, stdin)


if __name__ == "__main__":
    sys.exit(main())
