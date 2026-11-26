# The start-here interview

Four short rounds. The person's answers set their own preferences in `~/.config/patstack/preferences.json`, through [`scripts/preferences.py`](../../../scripts/preferences.py). Every agent they run then reads that file (the global instructions say so). Preferences choose among models and shape how agents talk and when they ask. They never grant a permission, lower a review level, skip a safety rule or remove a human gate. Say that once at the start.

## How to ask

- **Use the client's question tool**, within its own limits. Claude Code's ask-the-user tool takes up to four questions per call and two to four options each. Put the recommended option first, with "(Recommended)" in its label. The person can always type their own answer ("Other"). Use whatever question tool the client exposes. Codex has `request_user_input_async` in normal mode (in T3 too); its `request_user_input` works only in Plan mode. Only when there is none, write the same questions as a numbered list in chat, mark the recommended answers, and wait for the reply.
- **A round may take several calls.** Split a round when it has more questions than one call allows.
- **Every question needs two real options.** Never pad with a duplicate or an unavailable model. When only one answer fits, for example a single model for a job, ask whether to use it or leave that job to the proposal. Skip the question when even that choice is empty, and say so.
- Never ask what you can find out yourself: the models come from the catalogs, the host from the OS.
- **Saved preferences:** run `python3 scripts/preferences.py show` first. If there are some, ask once: keep them (Recommended on a rerun), change some rounds (they pick which), or start over.
- **Start from the proposal:** `python3 scripts/preferences.py propose` prints the recommended answers as JSON. Change only what the person changes.

## Round 1: how you work

1. **Language** for replies and reports: English, or Norwegian bokmål. A project's own rule still wins for what it ships; for example a pack may require bokmål in human-facing artifacts.
2. **Reports:** *short* (Recommended: outcome, proof, what is left for you) or *detailed* (also the reasoning and every step).
3. **Involvement:**
   - *hands-off* (Recommended): Full Send. The agent decides routine choices, merges after the required review, and stops only at real gates (production, destructive data, access, an explicit approval).
   - *checkpoints*: the agent also stops for your choice at meaningful product or approach decisions, and on a CRITICAL project prefers Full Stop at intake.
   Neither changes a gate.
4. **Reasoning effort:**
   - *medium, at most high* (Recommended): agents raise effort for hard work, never past the ceiling.
   - *high, at most high*.
   - *high, at most max*: the deepest reasoning, but it uses plan limits several times faster.

## Round 2: your models

Run `python3 scripts/preferences.py models` and show the numbered list. Explain in one line: these are the models this machine's Claude Code and Codex offer, read from their local catalogs. Whether the plan allows a model only shows when it is used. A Claude Code that has not cached its catalog yet (a fresh install) shows its aliases instead (`opus`, `fable`, `sonnet`, `haiku`); each always means the newest model of that family, so ranking them is fine.

**Rank per job.** Ask one question per job: *lead*, *design*, *implementation* and *ui*. `preferences.py` explains each job. Options are the proposal's top three for that job, the first marked recommended; the person may type any number from the list instead. Their choice goes first in that job's ranking, followed by the rest of the proposal's order. Then, in a second call:

- **Review pair.** R2 asks a reviewer from the other family than the author; R3 asks both. Offer the proposal's pair (Recommended) and up to two other pairs that mix the providers. When only one cross-provider pair exists, ask whether to use it. With one provider only, there is one model, and R2/R3 run as fresh sessions of it under the reviewer lenses; say so instead of asking.
- **The full ranking.** Show each job's complete order, one line per job, as the option's preview. Ask: use it (Recommended), or change an order. If they change one, they type it, for example `implementation: 5, 1, 2`.

A model they rank first must be on the list. If a catalog was missing (a client never started), say which and offer to rerun once they have started it.

## Round 3: notifications

One question: phone pings when a task waits for you or is ready to test.

- *none* (Recommended for a first setup). Always run `python3 scripts/preferences.py notify --off --apply`. It finds the same file the pings use, including a `PATSTACK_NOTIFY` override. It turns them off if they were on and does nothing otherwise. The file is kept, renamed, so they can turn the pings back on later.
- *ntfy*. They give, in chat, the ntfy server URL (for example `https://ntfy.sh`) and a long random topic. The topic is the only thing protecting the pings: suggest `patstack-` followed by about 20 random letters and digits. Then run:

```bash
python3 scripts/preferences.py notify --url <url> --topic <topic> --host <short name for this machine> --apply
```

They install the ntfy app and subscribe to that topic. Never print the topic back.

## Round 4: quick quiz

Four questions in one call, each with three options, so they know what the agents will do. It is not a gate. After the answers, show what was right and explain each miss in one sentence. Save the score.

1. *You ask for an ordinary fix on a CRITICAL customer project. What does the agent do by default?*
   It fixes it and gets the change reviewed. Before the task's first deploy to stage it asks you, so you can tell the customer. Then it merges through the merge gate and verifies the test release. Production always waits for your explicit approval, and work a revert cannot undo becomes Full Stop. (Wrong: "deploys straight to production"; "only suggests a patch".)
2. *Codex never refuses a direct merge although the merge guard is installed. Why?*
   The hook is not trusted yet; start `codex` and choose **Trust all and continue**. (Wrong: "Codex has no hooks"; "the guard only works in Claude Code".)
3. *An agent needs to log in to the test environment as a particular role. What does it use?*
   The project's test persona for that role, with the least privilege, logged in without showing the password. (Wrong: "your own account"; "it asks you to paste a password".)
4. *What do your preferences change?*
   Which models agents pick, the language, the report style and when they ask you. Never review levels, safety rules or approvals. (Wrong: "who may merge"; "production access".)

## Save

Put the answers into the proposal's JSON. Add `"quiz": {"score": N, "of": 4, "date": "YYYY-MM-DD"}`. Then:

```bash
python3 scripts/preferences.py write < answers.json            # check against this machine's models; NOT SAVED lists what to fix
python3 scripts/preferences.py write --apply < answers.json    # save (the previous file is kept as a backup)
python3 scripts/preferences.py show
```

Write `answers.json` in a temporary folder, never in the checkout. Show the person the saved summary: language, involvement, effort, first choice per job, review pair.
