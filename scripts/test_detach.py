"""detach.py tests in temporary trees; never touch live client folders."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("detach", Path(__file__).with_name("detach.py"))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
WIN = os.name == "nt"


def installer_hooks(checkout, runtime, host="devbox"):
    """The hook entries monitoring/devstack/install.py writes, in its exact command form."""
    python = sys.executable
    kpi = str(Path(checkout) / "monitoring/devstack/kpi_monitor.py")
    doctor = str(Path(checkout) / "scripts/setup_doctor.py")

    def audit(event):
        return shlex.join([python, kpi, "audit-hook", "--host", host, "--runtime", runtime, "--event", event])
    hooks = {"Stop": [{"hooks": [{"type": "command", "command": audit("Stop"), "timeout": 5, "async": True}]}],
             "PostToolUse": [{"matcher": "*" if runtime == "claude" else ".*",
                              "hooks": [{"type": "command", "command": audit("PostToolUse"), "timeout": 5, "async": True}]}],
             "SessionStart": [{"hooks": [{"type": "command", "timeout": 5,
                                          "command": shlex.join([python, doctor, "--host", host, "--hook", runtime])}]}]}
    if runtime == "claude":
        hooks["PostToolUseFailure"] = [{"matcher": "*", "hooks": [
            {"type": "command", "command": audit("PostToolUseFailure"), "timeout": 5, "async": True}]}]
    return hooks


class Fixture(unittest.TestCase):
    """A home, a checkout named devstack[1] and its sibling devstack1, in a temporary folder."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base / "home"
        self.checkout = self.make_checkout("devstack[1]")
        self.sibling = self.make_checkout("devstack1")
        for client in d.CLIENT_SKILL_DIRS:
            (self.home / client).mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def make_checkout(self, name):
        root = self.base / name
        for skill in ("alpha", "beta"):
            (root / "skills" / skill).mkdir(parents=True)
            (root / "skills" / skill / "SKILL.md").write_text(f"{skill}\n", encoding="utf-8")
        (root / "skills/alpha/sub").mkdir()
        (root / "skills/alpha/sub/data.txt").write_bytes(b"payload\n")
        return root

    def link_skills(self, checkout, prefix=""):
        for client in d.CLIENT_SKILL_DIRS:
            for skill in ("alpha", "beta"):
                os.symlink(str(checkout / "skills" / skill), str(self.home / client / (prefix + skill)))

    def write_json(self, relative, data):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def uninstall(self, checkout=None, apply=True):
        checkout = checkout or self.checkout
        return d.run(self.home, checkout, source=checkout / "skills", apply=apply)

    def snapshot(self, root):
        return {str(p): p.read_bytes() for p in Path(root).rglob("*") if p.is_file() and not p.is_symlink()}


@unittest.skipIf(WIN, "uses POSIX symlinks and shell quoting")
class DetachTests(Fixture):
    def test_bracket_checkout_never_matches_its_sibling(self):
        self.link_skills(self.checkout)
        self.link_skills(self.sibling, prefix="sibling-")
        report = self.uninstall()
        self.assertEqual(4, sum(c["action"] == "remove link" for c in report["changes"]))
        for client in d.CLIENT_SKILL_DIRS:
            self.assertEqual(["sibling-alpha", "sibling-beta"], sorted(p.name for p in (self.home / client).iterdir()))

    def test_mirror_cleanup_never_crosses_a_directory_symlink(self):
        # Probe: mirror/alpha/sub -> external dir holding a byte-identical sub/data.txt.
        external = self.base / "external"
        external.mkdir()
        (external / "data.txt").write_bytes(b"payload\n")
        mirror = self.home / ".claude/skills/alpha"
        mirror.mkdir()
        (mirror / "SKILL.md").write_bytes(d.load_mirrors().transform(self.checkout / "skills/alpha/SKILL.md",
                                                                      self.checkout / "skills"))
        os.symlink(str(external), str(mirror / "sub"))
        report = self.uninstall()
        self.assertEqual(b"payload\n", (external / "data.txt").read_bytes())
        self.assertTrue((mirror / "sub").is_symlink())
        self.assertFalse((mirror / "SKILL.md").exists())
        self.assertIn(str(mirror / "sub/data.txt"), [k["path"] for k in report["kept"]])

    def test_mirror_cleanup_keeps_edited_added_files_and_symlinked_roots(self):
        transform = d.load_mirrors().transform
        mirror = self.home / ".agents/skills/alpha"
        (mirror / "sub").mkdir(parents=True)
        for relative in ("SKILL.md", "sub/data.txt"):
            (mirror / relative).write_bytes(transform(self.checkout / "skills/alpha" / relative, self.checkout / "skills"))
        (mirror / "notes.md").write_text("mine\n", encoding="utf-8")
        (mirror / "sub/data.txt").write_bytes(b"edited\n")
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "SKILL.md").write_text("beta\n", encoding="utf-8")
        os.symlink(str(elsewhere), str(self.home / ".claude/skills/beta"))  # a link elsewhere is not a mirror
        self.uninstall()
        self.assertEqual(["notes.md", "sub"], sorted(p.name for p in mirror.iterdir()))
        self.assertEqual(b"edited\n", (mirror / "sub/data.txt").read_bytes())
        self.assertEqual("beta\n", (elsewhere / "SKILL.md").read_text(encoding="utf-8"))
        self.assertTrue((self.home / ".claude/skills/beta").is_symlink())

    def test_identical_mirrors_are_removed_with_their_empty_folders(self):
        transform = d.load_mirrors().transform
        for client in d.CLIENT_SKILL_DIRS:
            for skill in ("alpha", "beta"):
                for src in (self.checkout / "skills" / skill).rglob("*"):
                    if src.is_file():
                        dest = self.home / client / src.relative_to(self.checkout / "skills")
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(transform(src, self.checkout / "skills"))
        self.uninstall()
        for client in d.CLIENT_SKILL_DIRS:
            self.assertEqual([], list((self.home / client).iterdir()))

    def test_move_never_writes_through_a_symlinked_instruction_file(self):
        # Probe: ~/.claude/CLAUDE.md -> an external shared file naming the old path.
        old = self.base / "old/devstack"
        shared = self.base / "shared-CLAUDE.md"
        shared.write_text(f"Read `{old}/skills/devstack/SKILL.md`\n", encoding="utf-8")
        os.symlink(str(shared), str(self.home / ".claude/CLAUDE.md"))
        agents = self.home / ".codex/AGENTS.md"
        agents.parent.mkdir(parents=True)
        agents.write_text(f"Read `{old}/skills/devstack/SKILL.md`, not `{old}1/skills` or `{old}-x/a`\n", encoding="utf-8")
        report = d.run(self.home, old, new=self.checkout, apply=True)
        self.assertEqual(f"Read `{old}/skills/devstack/SKILL.md`\n", shared.read_text(encoding="utf-8"))
        self.assertTrue((self.home / ".claude/CLAUDE.md").is_symlink())
        self.assertIn(str(self.home / ".claude/CLAUDE.md"), [k["path"] for k in report["kept"]])
        self.assertEqual(f"Read `{self.checkout}/skills/devstack/SKILL.md`, not `{old}1/skills` or `{old}-x/a`\n",
                         agents.read_text(encoding="utf-8"))

    def test_only_the_installers_own_hooks_are_removed(self):
        # Probe: user hooks that mention the checkout must survive.
        old = str(self.checkout)
        hooks = installer_hooks(self.checkout, "claude")
        user = [f'cat "{old}/README.md"',
                shlex.join([sys.executable, old + "/monitoring/devstack/kpi_monitor.py", "report"]),
                shlex.join([sys.executable, "-u", old + "/monitoring/devstack/kpi_monitor.py", "audit-hook", "--host",
                            "devbox", "--runtime", "claude", "--event", "Stop"]),
                shlex.join(["bash", old + "/scripts/setup_doctor.py", "--host", "devbox", "--hook", "claude"])]
        hooks["Stop"][0]["hooks"] += [{"type": "command", "command": c} for c in user]
        hooks["Notification"] = installer_hooks(self.sibling, "claude")["Stop"]  # the sibling's own hook stays
        settings = self.write_json(".claude/settings.json", {"model": "x", "permissions": {"allow": ["Read"]},
                                                              "hooks": hooks, "custom": {"keep": [1, 2]}})
        report = self.uninstall()
        self.assertEqual([4], [c["count"] for c in report["changes"] if c["action"] == "remove hooks"])
        data = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(user, [h["command"] for h in data["hooks"]["Stop"][0]["hooks"]])
        self.assertIn("Notification", data["hooks"])
        self.assertNotIn("PostToolUse", data["hooks"])
        self.assertEqual(({"allow": ["Read"]}, "x", {"keep": [1, 2]}), (data["permissions"], data["model"], data["custom"]))

    def test_relocation_removes_old_links_and_seven_hooks_and_a_rerun_is_a_no_op(self):
        old = self.base / "moved/away/devstack"
        self.link_skills(old)
        self.write_json(".claude/settings.json", {"hooks": installer_hooks(old, "claude")})
        self.write_json(".codex/hooks.json", {"hooks": installer_hooks(old, "codex")})
        report = d.run(self.home, old, new=self.checkout, apply=True)
        self.assertEqual(7, sum(c.get("count", 0) for c in report["changes"]))
        self.assertEqual(4, sum(c["action"] == "remove link" for c in report["changes"]))
        self.assertIsNotNone(report["backup"])
        again = d.run(self.home, old, new=self.checkout, apply=True)
        self.assertEqual(([], None, "nothing to change"), (again["changes"], again["backup"], again["note"]))

    def test_dry_run_changes_nothing(self):
        self.link_skills(self.checkout)
        settings = self.write_json(".claude/settings.json", {"hooks": installer_hooks(self.checkout, "claude")})
        before = settings.read_bytes()
        report = self.uninstall(apply=False)
        self.assertEqual(5, len(report["changes"]))  # 4 links and 1 hook file
        self.assertEqual(before, settings.read_bytes())
        self.assertEqual(2, len(list((self.home / ".claude/skills").iterdir())))
        self.assertFalse((self.home / ".local/state/devstack/detach-backups").exists())

    def test_backups_get_new_folders_and_never_overwrite(self):
        fixed = d.datetime(2026, 1, 1, tzinfo=d.timezone.utc)
        with mock.patch.object(d, "datetime") as clock:
            clock.now.return_value = fixed
            self.link_skills(self.checkout)
            first = self.uninstall()["backup"]
            self.link_skills(self.checkout)
            second = self.uninstall()["backup"]
        self.assertNotEqual(first, second)
        self.assertEqual(4, len([p for p in Path(first).rglob("*") if p.is_symlink()]))
        self.assertEqual(4, len([p for p in Path(second).rglob("*") if p.is_symlink()]))

    def test_symlinked_hook_file_is_not_written_through(self):
        real = self.base / "shared-settings.json"
        real.write_text(json.dumps({"hooks": installer_hooks(self.checkout, "claude")}), encoding="utf-8")
        before = real.read_bytes()
        os.symlink(str(real), str(self.home / ".claude/settings.json"))
        report = self.uninstall()
        self.assertEqual(before, real.read_bytes())
        self.assertIn(str(self.home / ".claude/settings.json"), [k["path"] for k in report["kept"]])

    def test_uninstall_reports_instructions_instead_of_editing_them(self):
        path = self.home / ".claude/CLAUDE.md"
        path.write_text(f"Read `{self.checkout}/skills/devstack/SKILL.md`\n", encoding="utf-8")
        before = path.read_bytes()
        report = self.uninstall()
        self.assertEqual(before, path.read_bytes())
        self.assertEqual([str(path)], [m["path"] for m in report["manual"]])


@unittest.skipIf(WIN, "uses POSIX symlinks")
class SymlinkedClientFolderTests(Fixture):
    """The reviewer's setup: HOME/.claude -> external/shared-client holding DevStack pieces."""

    def share_claude(self, old):
        shared = self.base / "external/shared-client"
        (shared / "skills/alpha").mkdir(parents=True)
        (self.home / ".claude/skills").rmdir()
        (self.home / ".claude").rmdir()
        os.symlink(str(shared), str(self.home / ".claude"))
        transform = d.load_mirrors().transform
        for relative in ("SKILL.md", "sub/data.txt"):
            dest = shared / "skills/alpha" / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(transform(self.checkout / "skills/alpha" / relative, self.checkout / "skills"))
        (shared / "skills/alpha/mine.md").write_text("mine\n", encoding="utf-8")
        hooks = installer_hooks(old, "claude")
        hooks["Stop"][0]["hooks"].append({"type": "command", "command": f'cat "{old}/README.md"'})
        (shared / "settings.json").write_text(json.dumps({"hooks": hooks, "model": "x"}), encoding="utf-8")
        (shared / "CLAUDE.md").write_text(f"Read `{old}/skills/devstack/SKILL.md`\n", encoding="utf-8")
        return shared

    def test_default_uninstall_leaves_a_symlinked_client_folder_untouched(self):
        shared = self.share_claude(self.checkout)
        before = self.snapshot(shared)
        report = d.run(self.home, self.checkout, source=self.checkout / "skills", apply=True)
        self.assertEqual(before, self.snapshot(shared))
        self.assertEqual(3, d.exit_code(report))
        self.assertEqual({str(self.home / ".claude")}, {item["link"] for item in report["left_in_place"]})
        self.assertTrue(any("--follow-client-links" in k["reason"] for k in report["kept"]))

    def test_follow_flag_changes_only_devstack_items_with_backups(self):
        shared = self.share_claude(self.checkout)
        report = d.run(self.home, self.checkout, source=self.checkout / "skills", apply=True, follow=True)
        self.assertEqual(0, d.exit_code(report))
        self.assertEqual(["mine.md"], sorted(p.name for p in (shared / "skills/alpha").iterdir()))
        data = json.loads((shared / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual([f'cat "{self.checkout}/README.md"'], [h["command"] for h in data["hooks"]["Stop"][0]["hooks"]])
        self.assertEqual("x", data["model"])
        self.assertEqual(f"Read `{self.checkout}/skills/devstack/SKILL.md`\n", (shared / "CLAUDE.md").read_text(encoding="utf-8"))
        saved = [p.name for p in Path(report["backup"]).rglob("*") if p.is_file()]
        self.assertIn("settings.json", saved)
        self.assertIn("SKILL.md", saved)

    def test_relocation_leaves_external_instructions_alone_unless_followed(self):
        old = self.base / "moved/devstack"
        shared = self.share_claude(old)
        before = (shared / "CLAUDE.md").read_bytes()
        report = d.run(self.home, old, new=self.checkout, apply=True)
        self.assertEqual(before, (shared / "CLAUDE.md").read_bytes())
        self.assertEqual(3, d.exit_code(report))
        report = d.run(self.home, old, new=self.checkout, apply=True, follow=True)
        self.assertEqual(f"Read `{self.checkout}/skills/devstack/SKILL.md`\n", (shared / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertIn("CLAUDE.md", [p.name for p in Path(report["backup"]).rglob("*")])

    def test_symlinked_codex_folder_keeps_its_hooks_by_default(self):
        shared = self.base / "external/codex"
        shared.mkdir(parents=True)
        (shared / "hooks.json").write_text(json.dumps({"hooks": installer_hooks(self.checkout, "codex")}), encoding="utf-8")
        before = (shared / "hooks.json").read_bytes()
        os.symlink(str(shared), str(self.home / ".codex"))
        report = d.run(self.home, self.checkout, source=self.checkout / "skills", apply=True)
        self.assertEqual(before, (shared / "hooks.json").read_bytes())
        self.assertEqual(3, d.exit_code(report))

    def test_a_folder_that_becomes_a_symlink_after_the_plan_stops_the_run(self):
        settings = self.home / ".claude/settings.json"
        settings.write_text(json.dumps({"hooks": installer_hooks(self.checkout, "claude")}), encoding="utf-8")
        actions, _, _, _ = d.plan(self.home, self.checkout, source=self.checkout / "skills",
                                  transform=d.load_mirrors().transform)
        shared = self.base / "swapped"
        os.rename(str(self.home / ".claude"), str(shared))
        os.symlink(str(shared), str(self.home / ".claude"))
        before = (shared / "settings.json").read_bytes()
        with self.assertRaises(RuntimeError):
            d.execute(actions, d.Backup(self.home))
        self.assertEqual(before, (shared / "settings.json").read_bytes())


@unittest.skipIf(WIN, "uses POSIX symlinks")
class SymlinkedSkillsFolderTests(Fixture):
    """A terminal skills folder linked to a shared folder, and aliased client folders."""

    def shared_skills(self, client, owner):
        """CLIENT/skills -> external folder holding an identical alpha mirror and a link to OWNER's beta."""
        shared = self.base / ("external-" + client.strip(".").replace("/", "-"))
        (shared / "alpha/sub").mkdir(parents=True)
        transform = d.load_mirrors().transform
        for relative in ("SKILL.md", "sub/data.txt"):
            (shared / "alpha" / relative).write_bytes(transform(self.checkout / "skills/alpha" / relative,
                                                                self.checkout / "skills"))
        os.symlink(str(owner / "skills/beta"), str(shared / "beta"))
        (shared / "mine").mkdir()
        (shared / "mine/SKILL.md").write_text("mine\n", encoding="utf-8")
        (self.home / client).rmdir()
        os.symlink(str(shared), str(self.home / client))
        return shared

    def test_linked_skills_folder_is_left_alone_by_default(self):
        for client in d.CLIENT_SKILL_DIRS:
            shared = self.shared_skills(client, self.checkout)
            before = self.snapshot(shared)
            report = self.uninstall()
            self.assertEqual(before, self.snapshot(shared))
            self.assertTrue((shared / "beta").is_symlink())
            self.assertEqual(3, d.exit_code(report))
            self.assertIn(str(self.home / client), [x["link"] for x in report["left_in_place"]])
            os.unlink(str(self.home / client))
            (self.home / client).mkdir()

    def test_linked_skills_folder_is_cleaned_with_backups_when_followed(self):
        shared = self.shared_skills(".agents/skills", self.checkout)
        report = d.run(self.home, self.checkout, source=self.checkout / "skills", apply=True, follow=True)
        self.assertEqual(0, d.exit_code(report))
        self.assertEqual(["mine"], sorted(p.name for p in shared.iterdir()))
        saved = [p for p in Path(report["backup"]).rglob("*")]
        self.assertIn("SKILL.md", [p.name for p in saved if p.is_file()])
        self.assertIn("beta", [p.name for p in saved if p.is_symlink()])

    def test_relocation_handles_a_linked_skills_folder(self):
        old = self.base / "moved/devstack"
        shared = self.shared_skills(".claude/skills", old)
        report = d.run(self.home, old, new=self.checkout, apply=True)
        self.assertEqual(3, d.exit_code(report))
        self.assertTrue((shared / "beta").is_symlink())
        report = d.run(self.home, old, new=self.checkout, apply=True, follow=True)
        self.assertEqual(0, d.exit_code(report))
        self.assertFalse(os.path.lexists(str(shared / "beta")))
        self.assertTrue((shared / "alpha/SKILL.md").is_file())  # relocation never removes mirrors

    def test_skills_folder_linked_to_the_checkout_itself_is_removed(self):
        (self.home / ".claude/skills").rmdir()
        os.symlink(str(self.checkout / "skills"), str(self.home / ".claude/skills"))
        report = self.uninstall()
        self.assertEqual(0, d.exit_code(report))
        self.assertFalse(os.path.lexists(str(self.home / ".claude/skills")))

    def test_aliased_client_folders_are_cleaned_once(self):
        shared = self.base / "shared-client"
        (shared / "skills/alpha/sub").mkdir(parents=True)
        transform = d.load_mirrors().transform
        for relative in ("SKILL.md", "sub/data.txt"):
            (shared / "skills/alpha" / relative).write_bytes(transform(self.checkout / "skills/alpha" / relative,
                                                                       self.checkout / "skills"))
        os.symlink(str(self.checkout / "skills/beta"), str(shared / "skills/beta"))
        (shared / "settings.json").write_text(json.dumps({"hooks": installer_hooks(self.checkout, "claude")}), encoding="utf-8")
        for client in (".claude", ".agents"):
            (self.home / client / "skills").rmdir()
            (self.home / client).rmdir()
            os.symlink(str(shared), str(self.home / client))
        report = d.run(self.home, self.checkout, source=self.checkout / "skills", apply=True, follow=True)
        self.assertNotIn("error", report)
        self.assertEqual(0, d.exit_code(report))
        self.assertEqual(4, len(report["changes"]))  # 2 mirror files, 1 link, 1 hook file: each once
        self.assertEqual([], list((shared / "skills").iterdir()))
        self.assertNotIn("Stop", json.loads((shared / "settings.json").read_text(encoding="utf-8"))["hooks"])

    def test_aliased_skills_folders_are_cleaned_once(self):
        shared = self.shared_skills(".claude/skills", self.checkout)
        (self.home / ".agents/skills").rmdir()
        os.symlink(str(shared), str(self.home / ".agents/skills"))
        report = d.run(self.home, self.checkout, source=self.checkout / "skills", apply=True, follow=True)
        self.assertEqual((0, 3), (d.exit_code(report), len(report["changes"])))
        self.assertEqual(["mine"], sorted(p.name for p in shared.iterdir()))


class PathTests(unittest.TestCase):
    def test_windows_hook_forms_compare_case_insensitively_and_literally(self):
        command = "D:/Tools/Python39/python.exe D:/dev/DevStack/monitoring/devstack/kpi_monitor.py audit-hook --host windows --runtime codex --event Stop"
        self.assertEqual("kpi", d.hook_kind(command, ["d:\\DEV\\devstack"], windows=True))
        self.assertIsNone(d.hook_kind(command.replace("DevStack/", "DevStack1/"), ["d:\\DEV\\devstack"], windows=True))
        status = "py D:/dev/DevStack/scripts/setup_doctor.py --host windows --hook claude"
        self.assertEqual("status", d.hook_kind(status, ["D:\\dev\\DevStack"], windows=True))

    def test_within_is_component_based(self):
        self.assertTrue(d.within("/a/devstack[1]/skills/x", "/a/devstack[1]/skills", windows=False))
        self.assertFalse(d.within("/a/devstack1/skills/x", "/a/devstack[1]/skills", windows=False))
        self.assertFalse(d.within("/a/devstack[1]/skills-old/x", "/a/devstack[1]/skills", windows=False))
        self.assertTrue(d.within("D:/X/skills/a", "d:\\x\\skills", windows=True))


if __name__ == "__main__":
    unittest.main()
