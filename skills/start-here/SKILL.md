---
name: start-here
description: Set up Patstack for a new team member on this machine, end to end, or re-check and repair an existing setup - prerequisites, skills, global instructions, merge guard for Claude Code and Codex, ticket numbers, the bundled project pack (product vault, test logins), an interview that sets the person's own preferences (language, involvement, effort, their available models ranked per job, review pair, notifications) with a short quiz, and a final health check. Use when someone says start here, set me up, install Patstack, onboard me, or after pulling a Patstack update. Changes only the person's own client configuration, with backups; creates no ticket and touches no project or production system.
---

# Start here

One run takes a person from a fresh clone to a working Patstack on this machine, set up the way they want to work. The mechanical steps live in [`scripts/start_here.py`](../../scripts/start_here.py) (dry run by default, idempotent); this skill runs it, handles what needs judgment and proves the result. Run it again at any time: what is already in place is reported `OK` and left alone.

Talk to the person in their language. Before you begin, say in one line what will change: their skill folders, `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.claude/settings.json` and `~/.codex/hooks.json` (each backed up before a change), what the bundled project pack sets up (for example a clone of its product vault), and their own preferences file `~/.config/patstack/preferences.json` from a short interview.

## Boundaries

- No ticket, no project repository change, no deploy, no production system.
- Never print, paste or store a credential: passwords, tokens, `BW_SESSION`, cookies. Logins are done by the person in their own terminal or browser.
- Never overwrite: an existing file is backed up or left alone and reported. Never remove someone's existing skills, hooks or instructions.
- Never edit a client's trust or permission settings yourself. Codex hook trust is the person's click. The one exception is a pack step that only adds asking (an `ask` rule or a stricter approval mode, backed up first, as a project pack may add for an external tool's write tools); it never adds an allow rule, removes a rule or weakens a mode.
- Install no paid or system software without asking. Name what is missing and the command to install it.

## 1. Where you are

Find the checkout: the folder two levels above this file. Read `git -C <checkout> status -sb` and the OS (`mac`, `devbox` for any Linux, `windows`). Check, and report one line each:

| Check | Command | Needed for |
|---|---|---|
| Python 3.9+ | `python3 --version` (Windows: `python`) | everything |
| git | `git --version` | everything |
| GitHub CLI, logged in as the person's own account | `gh auth status` | PRs, cloning private repositories |
| Node.js | `node --version` | `scripts/check.py` |
| Claude Code and/or Codex | `claude --version`, `codex --version` | the clients |

If `gh` is not logged in, the person runs `gh auth login` and then `gh auth setup-git` in their own terminal; wait for them. The account `gh` is logged in with on the person's own machine is theirs: use it and go on. When several accounts are logged in, name the active one in the report. Never log in with, or switch to, someone else's account.

### In T3 Code

When `T3CODE_THREAD_ID` is set, this runs inside T3. Check these too, and report one line each ([Patstack in T3](../../docs/t3.md)):

- **Providers:** read the T3 orchestrator capabilities. Name the providers and models T3 can run here. With only one provider, say that R2 and R3 run as fresh sessions under the reviewer lenses, and that this is fine.
- **Projects:** list the T3 projects. The Patstack checkout must be one; this thread runs in it. Ask which product repositories they work in. For each, offer to add the folder as a T3 project, or to clone the repository first, with their own GitHub account. Never add anything they did not choose.
- **Runtime mode:** say which one this thread runs in. Recommend *full access* for normal work, and say in one sentence that it is tool access, not permission.
- **Codex trust:** a Codex merge guard is trusted only in a terminal, because T3 never shows Codex's trust question. Step 3 tells them how.
- **Browser panel:** run `preview_status`. Say that web UI checks run there, and that they sign a test persona in themselves, once, in the panel.

## 2. Update and validate the checkout

On a clean checkout of `main`: `git pull --ff-only`. Never pull into a dirty tree or another branch; report it instead. Then `python3 scripts/check.py` must print `OK:`. If it does not, stop and report the failing line. On Windows use `python scripts/check.py`, never `python3` (usually only the Microsoft Store placeholder). Windows runs the portable tests; tests requiring POSIX task fixtures, executable bits or Linux sandboxing are explicitly skipped and must also pass on Linux before delivery. The health check step's `setup_doctor.py` checks the person's installation separately.

## 3. Run the setup

```bash
python3 scripts/start_here.py              # dry run: read the rows to the person
python3 scripts/start_here.py --apply      # then do it
```

Rows: `OK` already in place, `DONE` changed now, `TODO` needs the person or you, `SKIP` not applicable. Work through every `TODO`:

- **`instr` exists without Patstack.** The person already has their own instructions. Back the file up (`<file>.<time>.bak`), merge the template `examples/global-instructions/AGENTS.md` into it with `<PATSTACK>` replaced by the checkout path, keep every rule of theirs and the template's first line `<!-- patstack-global-instructions -->`, drop only an older workflow block that names another router, and show the person the diff before saving. Where rules disagree, the stricter authority rule wins.
- **`skills … left alone`.** An older installation. Show where each one points. Replace one only when the person agrees (back up first); an old `patstack` link is the pre-rename coordinator and goes.
- **`ticket board`.** The checkout or the person has a team board config (`monday.json`), so new ticket numbers come from that board. Set up the person's access now, so their first task does not stop for it. Run `python3 tools/monday_ticket.py check`. If it fails for lack of a token, follow step 1 of "Tickets on a team board" in the [coordination reference](../patstack/references/coordination.md): `monday_ticket.py setup` prints the token page, which you open in their browser. They create and copy a personal API token. It comes to you only through the host's private secret input (in T3, `request_secret` with file delivery), never through chat. Then `monday_ticket.py setup --store <that file>`, and `check` again. Never print, log or commit the token. The row is `OK` once the board answers; `check failed` with a stored token means a wrong or expired token, so repeat with a new one; `configuration is broken` names a config file to fix first.
- **`tickets`.** Without a team board: nothing to do now. The first time an agent on this machine needs a new `TKT-…` number, it asks the person which slot the Patstack maintainer gave this machine and sets up the counter itself (coordination reference). Tell the person to have the slot ready.
- **`guard codex … Trust all`.** Codex runs a new hook only after it is trusted, and skips an untrusted one without a word. The person starts `codex` once in a terminal, outside T3, and chooses **Trust all and continue** (or reviews it under `/hooks`). T3 never shows that question. Wait for them, then rerun the doctor (health check step).
- **A project pack row** (`<pack> vault`, `<pack> personas` and the like) comes from the bundled pack's own setup step (`project-packs/<pack>/tools/start_here.py`). The row says what is missing; the pack's `onboarding.md` says how to fix it.

## 4. Your preferences: the interview

Run the [interview](references/interview.md): four short rounds through the client's question tool.

1. How they work: language, report length, involvement and reasoning effort.
2. Their models: found on this machine with `scripts/preferences.py models`, then ranked per job (lead, design, implementation, UI checks) plus a review pair.
3. Notifications.
4. A four-question quiz on what the agents will and will not do.

Their answers are saved with `scripts/preferences.py write --apply`. On a rerun, saved preferences are shown and kept unless they want to change them. In a non-interactive run (nobody can answer), skip the interview, leave saved preferences as they are, and list it as still to do.

## 5. Prove the project pack works

For each bundled pack (`project-packs/*/INDEX.md`), read its `onboarding.md` and run the checks it lists under the setup check: typically its product-context doctor and its test-login check. They show that context and test logins work from this machine. Report each result in one line.

## 6. Health check

```bash
python3 scripts/setup_doctor.py --host <mac|devbox|windows>
```

Every row should be `OK` or an understood `INFO`; `preferences` shows what the interview saved. Explain each `WARN` in one line with its fix; fix only what is the person's own configuration.

## 7. Report

End with a short table: step, status, and what the person still has to do (for example restart the client so it loads the new skills, trust the Codex hook, the ticket board token if it is still missing, or this machine's ticket slot when there is no board), their quiz score and their saved preferences in one line each. Then the first steps:

- Open a **new** Claude Code or Codex session in a project and ask for a real change ("Fix the redirect loop after login"). Patstack takes it from there.
- `/start-here` again after every Patstack update, or whenever something seems off.

Proof labels: the doctor output and the pack checks are EXECUTED; a client loading the skills is OBSERVED only in a fresh session.
