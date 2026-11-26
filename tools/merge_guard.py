#!/usr/bin/env python3
"""PreToolUse hook: a pull request is merged only through tools/merge_gate.py.

Reads the client's hook JSON on stdin and exits 2 with the reason on stderr, which Claude Code
(and Codex hooks that follow the same contract) treat as a refusal, when the command text could
merge a GitHub pull request directly. Anything else exits 0. The gate runs `gh` from Python,
outside the shell tool, so it is not refused.

The test is a deliberate over-approximation, not a shell parser: quotes, `$'` and the escape and
continuation characters of sh, cmd and PowerShell (backslash, caret, backtick) are removed, a
continuation (one of them before a line break) is removed with its line break so it rejoins a
word, the
text is split into words at whitespace and shell punctuation, and the command
is refused when it contains a word ending in `gh` or `gh.exe` (so any path to the CLI, also on
Windows, where removed backslashes join the path into one word) together with

- the word `pr` followed anywhere later by the word `merge`, whatever stands between them
  (flags, redirections, punctuation, other commands), or
- the word `api` and any word containing `merge` (REST `pulls/N/merge` with or without a query,
  `repos/…/merges`, GraphQL `mergePullRequest` or auto-merge mutations). Read merge state with
  `gh pr view --json`, not `gh api`, or
- the words `api` and `graphql`: any raw GraphQL call, because its payload (inline, a file,
  `--input`, a substitution) can hold a merge mutation the guard cannot read. Read data with
  `gh pr view --json`, `gh issue` or REST through `gh api` instead.

So control flow, wrappers and their operands, nested shells, `eval`, substitutions and heredocs
cannot hide a merge, because the words are found wherever they stand. The cost is that a
harmless command naming those words together (a commit message or grep that spells out
`gh pr merge`, or `gh pr view` followed by `git merge` in one command line) is refused too;
rephrase it or split it into two commands. A variable, alias, function or script file that
holds the verb is not caught, nor another HTTP client or a direct push to the default branch:
the guard closes the normal path, and the rule in coordination.md#merge still applies.
"""
import json
import re
import sys

CONTINUATION = re.compile(r"[\\^`][ \t]*\r?\n")
NOISE = re.compile(r"\$'|[\"'\\^`]")
WORD = re.compile(r"[^\s;&|()<>{}$=,]+")
REASON = ("Merges go through the merge gate, which checks the mode line, the review records "
          "for the exact head and CI before it merges: "
          "python3 <patstack>/tools/merge_gate.py merge --repo OWNER/NAME --pr N "
          "(see skills/patstack/references/coordination.md#merge). This guard also refuses "
          "text that only names `gh` with `pr merge`; rephrase it or split it into two commands.")


def refused(command):
    text = NOISE.sub("", CONTINUATION.sub("", command or ""))
    words = [w.lower() for w in WORD.findall(text)]
    if not any(w.endswith(("gh", "gh.exe")) for w in words):
        return False
    if "pr" in words and "merge" in words[words.index("pr") + 1:]:
        return True
    return "api" in words and any("graphql" in w or "merge" in w for w in words)


UNREADABLE = ("BLOCKED: the merge guard could not read this hook input, so it refuses rather than let a "
              "command through unchecked. Run the command again; if this repeats, check the hook setup "
              "(docs/setup.md step 6).")


def command_of(event):
    """The shell command in a hook event, or "" when the event carries none (Read, Edit and the like).
    A field that is present but malformed raises ValueError: absent is fine, wrong is refused."""
    if not isinstance(event, dict):
        raise ValueError("event is not an object")
    if "tool_input" not in event:
        return ""
    tool_input = event["tool_input"]
    if not isinstance(tool_input, dict):
        raise ValueError("tool_input is not an object")
    if "command" not in tool_input:
        return ""
    command = tool_input["command"]
    if isinstance(command, str):
        return command
    if isinstance(command, list) and all(isinstance(part, str) for part in command):
        return " ".join(command)
    raise ValueError("command is not text")


def main():
    # Fail closed: whatever goes wrong while reading or judging the input (not JSON, wrong types, too deeply
    # nested, an unreadable stream) is refused with exit 2, never waved through and never a bare crash.
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))  # utf-8-sig also accepts a byte-order mark
        blocked = refused(command_of(event))
    except Exception:
        sys.stderr.write(UNREADABLE + "\n")
        return 2
    if blocked:
        sys.stderr.write("BLOCKED: " + REASON + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
