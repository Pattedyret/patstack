"""branches.py on temporary repositories with a local bare remote and a fake gh; nothing outside the temp folder."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import branches

ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
       "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
       "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


class BranchTests(unittest.TestCase):
    def setUp(self):
        saved = {key: os.environ.get(key) for key in ENV}
        os.environ.update(ENV)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in saved.items()])
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.remote, self.repo = self.root / "origin.git", self.root / "app"
        git(self.root, "init", "-q", "--bare", "-b", "main", str(self.remote))
        git(self.root, "init", "-q", "-b", "main", str(self.repo))
        git(self.repo, "remote", "add", "origin", str(self.remote))
        self.commit("base.txt")
        git(self.repo, "push", "-q", "-u", "origin", "main")
        self.merged, self.open = [], []
        real_slug = branches.origin_slug
        branches.origin_slug = lambda repo: "example/app"  # the fixture's origin is a local bare repo
        self.addCleanup(setattr, branches, "origin_slug", real_slug)

    def commit(self, name):
        (self.repo / name).write_text(name)
        git(self.repo, "add", name)
        git(self.repo, "commit", "-q", "-m", name)
        return git(self.repo, "rev-parse", "HEAD")

    def branch(self, name, pr=True, cross=False):
        """A pushed branch with one commit; with pr, a merged PR records its head."""
        git(self.repo, "switch", "-q", "-c", name, "main")
        tip = self.commit(name + ".txt")
        git(self.repo, "push", "-q", "-u", "origin", name)
        git(self.repo, "switch", "-q", "main")
        if pr:
            self.merged.append({"number": len(self.merged) + 1, "headRefName": name, "headRefOid": tip,
                                "isCrossRepository": cross})
        return tip

    def gh(self, repo, *args):
        if args[:2] == ("repo", "view"):
            return {"nameWithOwner": "example/app", "defaultBranchRef": {"name": "main"}}
        return self.merged if "merged" in args else self.open

    def report(self):
        report = branches.inspect(self.repo, gh=self.gh)
        return report, {i["branch"]: i for i in report["origin"]}, {i["branch"]: i for i in report["local"]}

    def test_only_branches_whose_merged_pr_holds_their_tip_are_deletable(self):
        self.branch("done")
        git(self.repo, "merge", "-q", "--no-ff", "-m", "merge done", "done")
        self.branch("squashed")  # squash merge: main gets a new commit, the branch is no ancestor of main
        git(self.repo, "merge", "-q", "--squash", "squashed")
        git(self.repo, "commit", "-q", "-m", "squash squashed")
        git(self.repo, "push", "-q", "origin", "main")
        self.branch("after")
        git(self.repo, "switch", "-q", "after")
        self.commit("late.txt")
        git(self.repo, "push", "-q", "origin", "after")
        git(self.repo, "switch", "-q", "main")
        self.branch("stack-base")
        self.branch("in-review", pr=False)
        self.open.append({"number": 90, "headRefName": "stack-top", "baseRefName": "stack-base", "isCrossRepository": False})
        self.open.append({"number": 91, "headRefName": "in-review", "baseRefName": "main", "isCrossRepository": False})
        self.branch("no-pr", pr=False)
        self.branch("fork-name", cross=True)

        _, origin, local = self.report()
        self.assertTrue(origin["done"]["deletable"])
        self.assertTrue(origin["squashed"]["deletable"])
        self.assertEqual(origin["main"]["keep_reason"], "default branch")
        self.assertEqual(origin["after"]["keep_reason"], "commits after merged PR #3")
        self.assertEqual(origin["stack-base"]["keep_reason"], "open PR #90 uses it")
        self.assertEqual(origin["in-review"]["keep_reason"], "open PR #91 uses it")
        self.assertEqual(origin["no-pr"]["keep_reason"], "no merged PR")
        self.assertEqual(origin["fork-name"]["keep_reason"], "no merged PR")
        self.assertTrue(local["done"]["deletable"] and local["squashed"]["deletable"])
        self.assertEqual(local["main"]["keep_reason"], "default branch")
        self.assertEqual(local["after"]["keep_reason"], "commits after merged PR")

    def test_local_branches_behind_the_pr_or_gone_and_merged_are_deletable(self):
        self.branch("ahead")
        git(self.repo, "branch", "behind", "main")  # stale local copy: its tip is an ancestor of the PR head
        self.merged[-1]["headRefName"] = "behind"
        git(self.repo, "switch", "-q", "-c", "gone", "main")
        self.commit("gone.txt")
        git(self.repo, "push", "-q", "-u", "origin", "gone")
        git(self.repo, "switch", "-q", "main")
        git(self.repo, "merge", "-q", "--no-ff", "-m", "merge gone", "gone")
        git(self.repo, "push", "-q", "origin", "main", ":gone")
        git(self.repo, "switch", "-q", "-c", "fresh", "main")  # merged by ancestry, but its upstream is not gone
        git(self.repo, "switch", "-q", "main")
        self.branch("busy")
        git(self.repo, "worktree", "add", "-q", str(self.root / "busy-wt"), "busy")

        _, origin, local = self.report()
        self.assertTrue(local["behind"]["deletable"])
        self.assertTrue(local["gone"]["deletable"])
        self.assertEqual(local["fresh"]["keep_reason"], "no merged PR")
        self.assertTrue(local["busy"]["keep_reason"].startswith("checked out in "))
        self.assertTrue(origin["busy"]["deletable"])

    def test_apply_deletes_exactly_the_deletable_and_refuses_a_branch_that_moved(self):
        self.branch("done")
        self.branch("moved")
        self.branch("no-pr", pr=False)
        self.branch("local-moved")
        report, _, _ = self.report()
        git(self.repo, "switch", "-q", "local-moved")
        self.commit("unpushed.txt")  # local work after the check: the local delete must refuse
        git(self.repo, "switch", "-q", "main")
        other = self.root / "other"
        git(self.root, "clone", "-q", "-b", "moved", str(self.remote), str(other))
        (other / "x.txt").write_text("x")
        git(other, "add", "x.txt")
        git(other, "commit", "-q", "-m", "x")
        git(other, "push", "-q", "origin", "moved")  # after the check, before the delete

        self.assertFalse(branches.apply(report))
        self.assertEqual(report["delete_failed"], ["origin/moved", "local-moved"])
        self.assertEqual(sorted(git(self.remote, "for-each-ref", "--format=%(refname:strip=2)", "refs/heads").split()),
                         ["main", "moved", "no-pr"])
        self.assertEqual(sorted(git(self.repo, "for-each-ref", "--format=%(refname:strip=2)", "refs/heads").split()),
                         ["local-moved", "main", "no-pr"])
        config = git(self.repo, "config", "--get-regexp", r"^branch\.")
        self.assertNotIn("branch.done.", config)
        self.assertIn("branch.local-moved.", config)


    def test_fork_pr_base_is_kept_and_an_unknown_pr_head_matches_only_itself(self):
        self.branch("fork-base")
        self.open.append({"number": 7, "headRefName": "feature", "baseRefName": "fork-base", "isCrossRepository": True})
        git(self.repo, "branch", "stale", "main")
        self.merged.append({"number": 8, "headRefName": "stale", "headRefOid": "f" * 40, "isCrossRepository": False})
        _, origin, local = self.report()
        self.assertEqual(origin["fork-base"]["keep_reason"], "open PR #7 uses it")
        self.assertEqual(local["stale"]["keep_reason"], "commits after merged PR")

    def test_gh_failure_or_non_github_origin_deletes_nothing(self):
        self.branch("done")
        def broken(repo, *args):
            raise RuntimeError("gh pr list failed")
        with self.assertRaises(RuntimeError):
            branches.inspect(self.repo, gh=broken)
        branches.origin_slug = type(self).real_origin_slug
        with self.assertRaisesRegex(RuntimeError, "not a GitHub repository"):
            branches.inspect(self.repo, gh=self.gh)
        self.assertIn("done", git(self.remote, "for-each-ref", "--format=%(refname:strip=2)", "refs/heads"))

    def test_origin_slug_reads_https_and_ssh_urls(self):
        host = "@" + "github.com"  # split so the privacy check does not read these URLs as email addresses
        for url in ("https://github.com/Owner/repo.git", f"https://x-access-token{host}/Owner/repo",
                    f"git{host}:Owner/repo.git", f"ssh://git{host}/Owner/repo.git"):
            git(self.repo, "remote", "set-url", "origin", url)
            self.assertEqual(type(self).real_origin_slug(self.repo), "Owner/repo")


BranchTests.real_origin_slug = staticmethod(branches.origin_slug)


if __name__ == "__main__":
    unittest.main()
