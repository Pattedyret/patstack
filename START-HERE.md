# Start here

DevStack is one development workflow for Claude Code and Codex: Markdown skills plus small standard-library Python tools. It installs no packages and starts no services. This page gets you from a fresh clone to your first task in about ten minutes.

You need Claude Code or Codex, Python 3.9 or newer, and `git`. `gh` helps for pull requests.

## 1. Clone and check

```bash
git clone "https://github.com/OWNER/REPO.git" devstack && cd devstack
python3 scripts/check.py
```

Replace `OWNER/REPO` with this repository's path on GitHub. The output should start with `OK:`. The check runs offline. If it fails, fix that first; see [setup step 1](docs/setup.md#1-validate-the-checkout).

## 2. Link the skills

Keep the checkout where it is: the skills link to files elsewhere in this tree. Link every skill folder into your client, skipping any name you already have:

```bash
mkdir -p ~/.claude/skills
for d in skills/*/; do
  name=$(basename "$d")
  dest=~/.claude/skills/"$name"
  [ -e "$dest" ] || [ -L "$dest" ] || ln -s "$PWD/skills/$name" "$dest"
done
```

For Codex, link the same folders into the skills directory your Codex version discovers. Details: [setup step 2](docs/setup.md#2-expose-the-skills).

## 3. Add the global instructions

These tell your agent to load DevStack for every change request. Fill in this checkout's path in a private temporary file, then install it only where nothing exists yet (existing files and links are left alone):

```bash
global=$(mktemp)
python3 -c 'import os, sys; sys.stdout.write(open(sys.argv[1]).read().replace("<DEVSTACK>", os.getcwd()))' examples/global-instructions/AGENTS.md > "$global"
python3 - "$global" <<'PY'
import os, sys
text = open(sys.argv[1]).read()
for name in ("~/.claude/CLAUDE.md", "~/.codex/AGENTS.md"):
    path = os.path.expanduser(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:  # O_EXCL: never replace or follow an existing file or link
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        print("kept your existing", name)
        continue
    with os.fdopen(fd, "w") as out:
        out.write(text)
    print("installed", name)
PY
```

Already have one of those files? Do not overwrite it: back it up and merge by hand as described in [setup step 3](docs/setup.md#3-add-your-global-instructions).

## 4. Start a new session and give it a task

Open a fresh Claude Code or Codex session in one of your projects, so it picks up the skills, and ask for a real change:

> Fix the redirect loop after login.

DevStack takes it from there: it picks the route and review depth, builds the change, proves it and reports what it ran. Questions and discussion stay questions; only change requests start the workflow. [What you say, what happens](README.md#what-you-say-what-happens) shows more examples.

## Optional next steps

- **Session status and KPI hooks:** `python3 monitoring/devstack/install.py --host mac` (`windows` on Windows, `devbox` for a Linux host), then `python3 scripts/setup_doctor.py --host mac` to check. See [setup step 6](docs/setup.md#6-session-status-kpi-hooks-and-outcomes).
- **Your own project rules:** add a private project pack from the [template](examples/project-pack/README.md).
- **How it all fits together:** [README](README.md), [architecture](docs/architecture.md) and [status and limits](docs/status-and-limits.md).
