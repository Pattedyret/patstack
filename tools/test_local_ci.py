"""local_ci on throwaway git repositories; gh is mocked, nothing reaches GitHub."""
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import local_ci

PASS = "#!/usr/bin/env bash\nset -e\ntest -f base.txt -o ! -f needs-base\necho ok\n"
FAIL = "#!/usr/bin/env bash\necho broken >&2\nexit 3\n"
SCRIPT = "scripts/ci_local.py" if os.name == "nt" else "scripts/ci-local.sh"
if os.name == "nt":
    PASS = "from pathlib import Path\nassert Path('base.txt').is_file() or not Path('needs-base').is_file()\nprint('ok')\n"
    FAIL = "raise SystemExit(3)\n"


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class CiEnvironmentTests(unittest.TestCase):
    def test_runtime_git_config_is_removed_as_a_complete_group(self):
        source = {"PATH": "keep", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "credential.helper",
                  "GIT_CONFIG_VALUE_0": "sensitive", "OWNER_SETTING": "keep"}
        with mock.patch.object(local_ci.os, "environ", source):
            env = local_ci.ci_env()
        self.assertEqual(env, {"PATH": "keep", "OWNER_SETTING": "keep"})
        self.assertEqual(source["GIT_CONFIG_VALUE_0"], "sensitive")


class LocalCiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        sh(self.repo, "git", "init", "-q", "-b", "main")
        sh(self.repo, "git", "config", "user.email", "t@example.invalid")
        sh(self.repo, "git", "config", "user.name", "t")
        (self.repo / "scripts").mkdir()
        self.commit(SCRIPT, PASS)

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, name, text):
        (self.repo / name).write_text(text)
        sh(self.repo, "git", "add", name)
        sh(self.repo, "git", "commit", "-qm", name)
        return sh(self.repo, "git", "rev-parse", "HEAD")

    def main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = local_ci.main(["--path", str(self.repo), *args])
        return code, out.getvalue() + err.getvalue()

    def test_passing_script_exits_0_and_leaves_no_worktree(self):
        code, out = self.main()
        self.assertEqual(code, 0, out)
        self.assertIn("PASSED", out)
        self.assertEqual(len(sh(self.repo, "git", "worktree", "list").splitlines()), 1)

    def test_failing_script_exits_1(self):
        self.commit(SCRIPT, FAIL)
        self.assertEqual(self.main()[0], 1)

    def test_uncommitted_changes_are_refused(self):
        (self.repo / SCRIPT).write_text(FAIL)
        code, out = self.main()
        self.assertEqual(code, 2)
        self.assertIn("uncommitted", out)

    def test_python_script_is_found_when_there_is_no_shell_script(self):
        sh(self.repo, "git", "rm", "-q", SCRIPT)
        (self.repo / "scripts").mkdir(exist_ok=True)
        self.commit("scripts/ci_local.py", "import sys\nprint('py ok')\nsys.exit(0)\n")
        code, out = self.main()
        self.assertEqual(code, 0, out)
        self.assertIn("scripts/ci_local.py", out)

    def test_missing_script_is_a_setup_error(self):
        code, out = self.main("--script", "scripts/nothing.sh")
        self.assertEqual(code, 2)
        self.assertIn("not found", out)

    def test_runs_on_the_merge_into_the_base(self):
        sh(self.repo, "git", "branch", "base")
        sh(self.repo, "git", "checkout", "-q", "-b", "feature")
        self.commit("needs-base", "the script now requires base.txt\n")
        self.assertEqual(self.main()[0], 1)  # base.txt exists only on the base branch
        sh(self.repo, "git", "checkout", "-q", "base")
        self.commit("base.txt", "on base\n")
        sh(self.repo, "git", "checkout", "-q", "feature")
        self.assertEqual(self.main("--base", "base")[0], 0)

    def test_conflict_with_the_base_fails(self):
        sh(self.repo, "git", "checkout", "-q", "-b", "other")
        self.commit("x.txt", "base side\n")
        sh(self.repo, "git", "checkout", "-q", "main")
        self.commit("x.txt", "head side\n")
        code, out = self.main("--base", "other")
        self.assertEqual(code, 1)
        self.assertIn("CONFLICT", out)

    def pr_setup(self):
        """A bare origin holding main, and a pushed feature head one commit ahead."""
        origin = Path(self.tmp.name) / "origin.git"
        sh(self.tmp.name, "git", "init", "-q", "--bare", str(origin))
        sh(self.repo, "git", "remote", "add", "origin", str(origin))
        sh(self.repo, "git", "push", "-q", "origin", "main")
        base = sh(self.repo, "git", "rev-parse", "HEAD")
        sh(self.repo, "git", "checkout", "-q", "-b", "feature")
        head = self.commit("feature.txt", "change\n")
        return head, base

    def pr_main(self, head, base, origin="o/r", tip=None, extra=(), cross=False, permission="write", omit=()):
        calls = []

        def fake_gh(*args):
            calls.append(args)
            if args[:2] == ("pr", "view"):
                view = {"headRefOid": head, "baseRefName": "main", "state": "OPEN",
                        "isCrossRepository": cross, "author": {"login": "dev"}}
                return json.dumps({k: v for k, v in view.items() if k not in omit})
            if args[0] == "api" and args[1].endswith("/permission"):
                return permission
            return ""
        with mock.patch.object(local_ci, "gh", fake_gh), \
                mock.patch.object(local_ci, "base_tip", lambda repo, branch: tip or base), \
                mock.patch("project_tier.identity", lambda url: origin):
            code, out = self.main("--repo", "o/r", "--pr", "4", "--runner", "Anthropic/Claude-Opus-5-5", *extra)
        return code, out, calls

    def test_pr_mode_runs_on_the_current_base_and_posts_one_full_record_line(self):
        head, base = self.pr_setup()
        code, out, calls = self.pr_main(head, base)
        self.assertEqual(code, 0, out)
        self.assertEqual(calls[-1], ("pr", "comment", "4", "-R", "o/r", "-b",
                                     "Patstack-CI: result=pass head=%s runner=anthropic/claude-opus-5-5 base=%s" % (head, base)))

    def test_pr_mode_refuses_forks_and_authors_who_cannot_push(self):
        head, base = self.pr_setup()
        code, out, calls = self.pr_main(head, base, cross=True)
        self.assertEqual(code, 2)
        self.assertIn("another repository", out)
        for permission in ("read", "triage", "none", ""):
            code, out, calls = self.pr_main(head, base, permission=permission)
            self.assertEqual(code, 2, permission)
            self.assertIn("cannot push", out)
            self.assertFalse(any(c[:2] == ("pr", "comment") for c in calls))
        for missing in ("isCrossRepository", "author"):  # an answer without the field is refused, not assumed
            code, out, _ = self.pr_main(head, base, omit=(missing,))
            self.assertEqual(code, 2, missing)
        self.assertEqual(self.pr_main(head, base, permission="maintain")[0], 0)

    def test_pr_mode_refuses_a_stale_base(self):
        head, base = self.pr_setup()
        code, out, calls = self.pr_main(head, base, tip="e" * 40)
        self.assertEqual(code, 2)
        self.assertIn("fetch again", out)
        self.assertFalse(any(c[:2] == ("pr", "comment") for c in calls))

    def test_pr_mode_refuses_another_repository_as_origin(self):
        head, base = self.pr_setup()
        code, out, _ = self.pr_main(head, base, origin="someone/fork")
        self.assertEqual(code, 2)
        self.assertIn("not o/r", out)

    def test_pr_mode_refuses_base_and_script_overrides(self):
        for extra in (("--base", "main"), ("--script", "scripts/ci-local.sh")):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                local_ci.main(["--path", str(self.repo), "--repo", "o/r", "--pr", "4",
                               "--runner", "anthropic/claude-opus-5-5", *extra])

    def test_pr_head_must_match_the_checkout(self):
        head, base = self.pr_setup()
        code, out, _ = self.pr_main("0" * 40, base)
        self.assertEqual(code, 2)
        self.assertIn("push or check out the PR head", out)

    def test_credentials_in_the_environment_do_not_reach_ci(self):
        self.commit(SCRIPT, "import os\nassert not any(os.getenv(k) for k in ('GH_TOKEN', 'HEROKU_API_KEY', 'MY_SECRET'))\nassert os.getenv('PATH')\n"
                    if os.name == "nt" else 'test -z "${GH_TOKEN:-}${HEROKU_API_KEY:-}${MY_SECRET:-}" && test -n "$PATH"\n')
        with mock.patch.dict("os.environ", {"GH_TOKEN": "x", "HEROKU_API_KEY": "y", "MY_SECRET": "z"}):
            self.assertEqual(self.main()[0], 0)

    def test_urls_carrying_credentials_do_not_reach_ci(self):
        self.commit(SCRIPT,
                    "import os\nassert not any(os.getenv(k) for k in ('DATABASE_URL', 'LEGACY', 'CACHE', 'STRIPE_SK', 'JWT'))\nassert os.getenv('PLAIN_URL')\n"
                    if os.name == "nt" else 'test -z "${DATABASE_URL:-}${LEGACY:-}${CACHE:-}${STRIPE_SK:-}${JWT:-}" && test -n "${PLAIN_URL:-}"\n')
        env = {"DATABASE_URL": "postgres://u:p@db/x", "LEGACY": "postgres://u:p@db/x", "PLAIN_URL": "https://example.com/x",
               "CACHE": "redis://:pw@cache:6379", "STRIPE_SK": "x", "JWT": "x"}
        with mock.patch.dict("os.environ", env):
            self.assertEqual(self.main()[0], 0)

    def test_base_branch_names_are_encoded_and_the_returned_ref_must_match(self):
        calls = []

        def fake_gh(*args):
            calls.append(args[1])
            return json.dumps({"ref": "refs/heads/main", "object": {"sha": "a" * 40}})
        with mock.patch.object(local_ci, "gh", fake_gh), self.assertRaises(local_ci.SetupError):
            local_ci.base_tip("o/r", "main#review")
        self.assertEqual(calls, ["repos/o/r/git/ref/heads/main%23review"])

    def test_a_failed_worktree_setup_leaves_no_worktree_behind(self):
        hooks = Path(self.tmp.name) / "hooks"
        hooks.mkdir()
        (hooks / "post-checkout").write_text("#!/bin/sh\nexit 1\n")
        (hooks / "post-checkout").chmod(0o755)
        sh(self.repo, "git", "config", "core.hooksPath", str(hooks))
        code, _ = self.main()
        self.assertEqual(code, 2)
        self.assertEqual(len(sh(self.repo, "git", "worktree", "list").splitlines()), 1)

    def test_pr_needs_a_runner_identity(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            local_ci.main(["--path", str(self.repo), "--repo", "o/r", "--pr", "4"])


if __name__ == "__main__":
    unittest.main()
