import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / ".github/scripts"))
import release
import source_version as source


@contextlib.contextmanager
def cwd(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def git(path, *args):
    location = ["--git-dir", str(path)] if path.name.endswith(".git") else ["-C", str(path)]
    return subprocess.run(
        ["git", *location, *args], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def entry(tag="v9.8.7", draft=False):
    return {"id": 42, "tag_name": tag, "draft": draft, "prerelease": False}


class AvailabilityTests(unittest.TestCase):
    def test_pagination_drafts_published_and_complete_absence(self):
        for draft in (True, False):
            with self.subTest(draft=draft), patch.object(release, "remote_ref", return_value=None), \
                    patch.object(release, "api", side_effect=[
                        [entry()] * 100, [entry("v1.2.3", draft)]
                    ]) as api:
                with self.assertRaisesRegex(ValueError, "draft or published"):
                    release.available("owner/repo", "v1.2.3")
                self.assertEqual(api.call_args_list[1].args[0],
                                 "repos/owner/repo/releases?per_page=100&page=2")
        with patch.object(release, "remote_ref", return_value=None), \
                patch.object(release, "api", side_effect=[[entry()] * 100, []]) as api:
            release.available("owner/repo", "v1.2.3")
            self.assertEqual(api.call_count, 2)

    def test_errors_and_malformed_every_page_fail_closed(self):
        failures = [
            *(subprocess.CalledProcessError(1, ["gh", "api", str(status)])
              for status in (401, 403, 404, 500)),
            OSError("network"), json.JSONDecodeError("bad", "?", 0),
            {}, None, "[]", [None], [{}], [dict(entry(), id=True)],
            [dict(entry(), id=0)], [dict(entry(), tag_name=None)],
            [dict(entry(), tag_name="")], [dict(entry(), draft="false")],
            [dict(entry(), prerelease=None)], [entry()] * 101,
        ]
        for page in (1, 2):
            for response in failures:
                with self.subTest(page=page, response=response), \
                        patch.object(release, "remote_ref", return_value=None), \
                        patch.object(release, "api", side_effect=(
                            [[entry()] * 100] * (page - 1) + [response])):
                    with self.assertRaises((ValueError, OSError, subprocess.CalledProcessError)):
                        release.available("owner/repo", "v1.2.3")

    def test_remote_errors_and_malformed_fail_closed(self):
        with patch.object(release, "remote_ref", return_value="a" * 40), \
                patch.object(release, "api") as api:
            with self.assertRaises(ValueError):
                release.available("o/r", "v1.2.3")
            api.assert_not_called()
        for output in ("invalid\trefs/tags/v1.2.3", "a" * 40,
                       "a" * 40 + "\trefs/tags/wrong",
                       ("a" * 40 + "\trefs/tags/v1.2.3\n") * 2):
            with self.subTest(output=output), patch.object(release, "run", return_value=output):
                with self.assertRaises(ValueError):
                    release.remote_ref("refs/tags/v1.2.3")
        with patch.object(release, "run", side_effect=OSError("network")):
            with self.assertRaises(OSError):
                release.available("o/r", "v1.2.3")

    def test_transport_explicit_methods_and_no_retry(self):
        with patch.object(release, "run", return_value="[]") as run:
            release.api("repos/o/r/releases?per_page=100&page=2")
            self.assertEqual(run.call_args.args, ("gh", "api", "--method", "GET",
                             "repos/o/r/releases?per_page=100&page=2"))
        with patch.object(release, "run", return_value='{"id": 7}') as run:
            payload = {"tag_name": "v1.2.3", "draft": False}
            release.api("repos/o/r/releases", payload)
            self.assertIn("POST", run.call_args.args)
            self.assertEqual(json.loads(run.call_args.kwargs["input"]), payload)
        with patch.object(release, "run", side_effect=subprocess.CalledProcessError(1, "gh")) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                release.api("repos/o/r/releases")
            self.assertEqual(run.call_count, 1)
        with patch.object(release, "run", return_value='{"id": 8}') as run:
            asset = Path("NSSpeechRecognizer-1.2.3.zip")
            release.api("https://uploads.github.com/repos/o/r/releases/123/assets", asset=asset)
            self.assertEqual(run.call_args.args, (
                "gh", "api", "--method", "POST",
                "https://uploads.github.com/repos/o/r/releases/123/assets",
                "--header", "Content-Type: application/octet-stream", "--input", str(asset)))


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.local = self.root / "local"
        self.peer = self.root / "peer"
        git(self.root, "init", "--bare", str(self.remote))
        git(self.root, "init", "-b", "selected", str(self.local))
        for key, value in (("user.name", "Lifecycle Test"), ("user.email", "test@example.invalid"),
                           ("push.followTags", "true")):
            git(self.local, "config", key, value)
        git(self.local, "commit", "--allow-empty", "-m", "ancestor")
        self.ancestor = git(self.local, "rev-parse", "HEAD")
        for path in source.SOURCE_PATHS:
            (self.local / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, self.local / path)
        shutil.copytree(ROOT / ".github/scripts", self.local / ".github/scripts",
                        ignore=shutil.ignore_patterns("__pycache__"))
        git(self.local, "add", ".")
        git(self.local, "commit", "-m", "fixture")
        git(self.local, "remote", "add", "origin", str(self.remote))
        git(self.local, "push", "origin", "HEAD:refs/heads/selected")
        self.sha = git(self.local, "rev-parse", "HEAD")
        self.version = source.read(self.local)
        self.tag = f"v{self.version}"
        self.published = None
        self.uploaded = []
        git(self.root, "clone", "--branch", "selected", str(self.remote), str(self.peer))
        git(self.peer, "config", "user.name", "Peer")
        git(self.peer, "config", "user.email", "peer@example.invalid")
        context = cwd(self.local)
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def advance_peer(self):
        (self.peer / "peer.txt").write_text("concurrent branch update")
        git(self.peer, "add", ".")
        git(self.peer, "commit", "-m", "peer")
        git(self.peer, "push", "origin", "HEAD:refs/heads/selected")

    def test_bump_only_explicit_branch_source_no_follow_tags(self):
        git(self.local, "tag", "-a", "unrelated-annotated", "-m", "must not follow")
        git(self.remote, "update-ref", "refs/heads/other", self.sha)
        release.bump_branch(self.sha, "selected", "patch")
        new = git(self.local, "rev-parse", "HEAD")
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/selected"), new)
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/other"), self.sha)
        self.assertEqual(git(self.remote, "tag", "--list"), "")
        self.assertEqual(git(self.local, "rev-list", "--parents", "-n", "1", new),
                         f"{new} {self.sha}")
        self.assertEqual(git(self.local, "status", "--porcelain"), "")
        self.assertEqual(set(git(self.local, "diff-tree", "--no-commit-id", "--name-only",
                                 "-r", "HEAD").splitlines()), set(map(str, source.SOURCE_PATHS)))

    def test_cli_bytecode_keeps_clean_checkout(self):
        env = os.environ.copy()
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        subprocess.run(
            [sys.executable, ".github/scripts/release.py", "bump", "--sha", self.sha,
             "--branch", "selected", "--mode", "patch"],
            env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(git(self.local, "status", "--porcelain"), "")
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_bump_postpush_exact_remote_verification_fail_closed(self):
        real_remote_ref = release.remote_ref
        reads = 0

        def wrong_verification(ref):
            nonlocal reads
            result = real_remote_ref(ref)
            reads += 1
            return self.sha if reads == 3 else result

        with patch.object(release, "remote_ref", side_effect=wrong_verification):
            with self.assertRaisesRegex(ValueError, "Pushed branch failed exact-SHA"):
                release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(reads, 3)
        self.assertEqual(real_remote_ref("refs/heads/selected"),
                         git(self.local, "rev-parse", "HEAD"))
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_preparation_race(self):
        self.advance_peer()
        with self.assertRaisesRegex(ValueError, "moved"):
            release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(git(self.local, "rev-parse", "HEAD"), self.sha)

    def test_race_during_preparation(self):
        real_bump = release.bump

        def concurrent_bump(mode):
            result = real_bump(mode)
            self.advance_peer()
            return result

        with patch.object(release, "bump", side_effect=concurrent_bump):
            with self.assertRaisesRegex(ValueError, "moved during"):
                release.bump_branch(self.sha, "selected", "minor")
        self.assertEqual(release.remote_ref("refs/heads/selected"),
                         git(self.peer, "rev-parse", "HEAD"))

    def advertised_race(self, kind):
        real_run = release.run
        expected = None
        pushes = 0

        def concurrent_push(*args, **kwargs):
            nonlocal expected, pushes
            # Real bare-Git changes after final ls-remote, before advertisement.
            if "push" in args:
                pushes += 1
                if kind == "rewind":
                    expected = self.ancestor
                    git(self.remote, "update-ref", "refs/heads/selected", expected)
                elif kind == "delete":
                    git(self.remote, "update-ref", "-d", "refs/heads/selected")
                elif kind == "advance":
                    self.advance_peer()
                    expected = git(self.peer, "rev-parse", "HEAD")
                elif kind == "same-result":
                    expected = git(self.local, "rev-parse", "HEAD")
                    git(self.remote, "fetch", "--no-tags", str(self.local), "HEAD")
                    git(self.remote, "update-ref", "refs/heads/selected", expected)
                else:
                    self.fail(kind)
            return real_run(*args, **kwargs)

        with patch.object(release, "run", side_effect=concurrent_push):
            with self.assertRaises(subprocess.CalledProcessError):
                release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(pushes, 1)
        self.assertEqual(release.remote_ref("refs/heads/selected"), expected)
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_advertised_rewind(self):
        self.advertised_race("rewind")

    def test_advertised_deletion(self):
        self.advertised_race("delete")

    def test_advertised_advance(self):
        self.advertised_race("advance")

    def test_advertised_same_result(self):
        self.advertised_race("same-result")

    def guard_loss(self, missing, late):
        runtime = self.root / "runtime"
        shutil.copytree(self.local / ".github/scripts", runtime)
        guard = runtime / "bump-hooks/pre-push"
        real_remote_ref = release.remote_ref
        reads = 0

        def remove_guard():
            if missing:
                guard.unlink()
            else:
                guard.chmod(0o644)

        def remote(ref):
            nonlocal reads
            result = real_remote_ref(ref)
            reads += 1
            if reads == 2:
                remove_guard()
            return result

        if not late:
            remove_guard()
        with patch.object(release, "__file__", str(runtime / "release.py")), \
                patch.object(release, "remote_ref", side_effect=remote):
            with self.assertRaisesRegex(ValueError, "guard is missing or not executable"):
                release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(reads, 2 if late else 0)
        self.assertEqual(real_remote_ref("refs/heads/selected"), self.sha)
        self.assertEqual(git(self.remote, "tag", "--list"), "")
        if not late:
            self.assertEqual(git(self.local, "rev-parse", "HEAD"), self.sha)

    def test_missing_guard_initial(self):
        self.guard_loss(True, False)

    def test_nonexecutable_guard_initial(self):
        self.guard_loss(False, False)

    def test_missing_guard_after_final_remote_read(self):
        self.guard_loss(True, True)

    def test_nonexecutable_guard_after_final_remote_read(self):
        self.guard_loss(False, True)

    def test_bump_rejects_merge_even_with_selected_first_parent(self):
        real_run = release.run

        def merge_after_commit(*args, **kwargs):
            result = real_run(*args, **kwargs)
            if args[:2] == ("git", "commit"):
                tree = git(self.local, "rev-parse", "HEAD^{tree}")
                merged = git(self.local, "commit-tree", tree, "-p", self.sha,
                             "-p", self.ancestor, "-m", "synthetic merge")
                git(self.local, "update-ref", "HEAD", merged)
            return result

        with patch.object(release, "run", side_effect=merge_after_commit):
            with self.assertRaisesRegex(ValueError, "clean direct child"):
                release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(release.remote_ref("refs/heads/selected"), self.sha)
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_dirty_source_and_invalid_context(self):
        for sha in ("selected", "a" * 40, "a" * 39, "a" * 41):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                release.selected_sha(sha)
        with self.assertRaises(subprocess.CalledProcessError):
            release.bump_branch(self.sha, "invalid..branch", "patch")
        (self.local / "dirty.txt").write_text("dirty")
        with self.assertRaisesRegex(ValueError, "clean checkout"):
            release.bump_branch(self.sha, "selected", "patch")

    def test_preflight_clean_and_final_source_drift(self):
        (self.local / source.PLIST).write_text("dirty source")
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api") as api:
            with self.assertRaisesRegex(ValueError, "clean source"):
                release.preflight(self.sha)
            api.assert_not_called()
        shutil.copy2(ROOT / source.PLIST, self.local / source.PLIST)
        paths = self.assets()
        source.bump("patch")
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api") as api:
            with self.assertRaisesRegex(ValueError, "differs from the selected commit"):
                release.publish(self.sha, paths)
            api.assert_not_called()

    def test_guard_literal_sha_head_target_exact_single_parent_update(self):
        guard = ROOT / ".github/scripts/bump-hooks/pre-push"
        git(self.local, "commit", "--allow-empty", "-m", "direct child")
        new = git(self.local, "rev-parse", "HEAD")
        env = {**os.environ, "BUMP_EXPECTED_SHA": self.sha,
               "BUMP_EXPECTED_REF": "refs/heads/selected", "BUMP_NEW_SHA": new}
        valid = f"{new} {new} refs/heads/selected {self.sha}\n"

        def invoke(row, environment=env):
            return subprocess.run([str(guard)], input=row, env=environment, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        result = invoke(valid)
        self.assertEqual(result.returncode, 0, result.stderr)
        for row in (
            f"{new} {new} refs/heads/wrong {self.sha}\n",
            f"HEAD {new} refs/heads/selected {self.sha}\n",
            f"{new} {self.ancestor} refs/heads/selected {self.sha}\n",
            f"{new} {new} refs/heads/selected {self.ancestor}\n",
            valid * 2, "",
        ):
            self.assertNotEqual(invoke(row).returncode, 0)
        self.assertNotEqual(invoke(valid, {}).returncode, 0)
        # A merge's first parent is not enough: require exactly one parent.
        tree = git(self.local, "rev-parse", "HEAD^{tree}")
        merged = git(self.local, "commit-tree", tree, "-p", self.sha,
                     "-p", self.ancestor, "-m", "synthetic merge")
        git(self.local, "update-ref", "HEAD", merged)
        env["BUMP_NEW_SHA"] = merged
        self.assertNotEqual(invoke(
            f"{merged} {merged} refs/heads/selected {self.sha}\n").returncode, 0)

    def assets(self):
        paths = [Path(f"NSSpeechRecognizer-{self.version}.{ext}") for ext in ("zip", "dmg")]
        for asset in paths:
            asset.write_bytes(b"fixture asset")
        return paths

    def publication_api(self, calls, fail=None, race=None, malformed=None):
        def api(endpoint, payload=None, asset=None):
            calls.append((endpoint, payload, asset))
            if "/releases?" in endpoint:
                return []
            if endpoint.endswith("/git/refs"):
                if race:
                    git(self.remote, "update-ref", f"refs/tags/{self.tag}", race)
                # Atomic create-only bare Git models POST refs, including same-SHA races.
                git(self.remote, "update-ref", payload["ref"], payload["sha"], "0" * 40)
                result = {"ref": payload["ref"], "object": {"sha": payload["sha"]}}
                kind = "tag"
            elif endpoint.endswith("/releases"):
                if fail == "release":
                    raise subprocess.CalledProcessError(1, ["gh", "api"])
                self.published = {"id": 123, "tag_name": self.tag,
                                  "draft": False, "prerelease": False}
                result = self.published
                kind = "release"
            elif asset is not None:
                if fail == asset.suffix:
                    raise subprocess.CalledProcessError(1, ["gh", "api"])
                self.uploaded.append(asset.name)
                result = {"id": 456, "name": asset.name,
                          "size": asset.stat().st_size, "state": "uploaded"}
                kind = "upload"
            else:
                raise AssertionError(endpoint)
            return {"id": None} if malformed == kind else result
        return api

    def test_create_only_sha_new_release_id_original_notes(self):
        calls = []
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls)):
            release.publish(self.sha, self.assets())
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)
        self.assertIn("/releases?", calls[0][0])
        self.assertTrue(calls[1][0].endswith("/git/refs"))
        self.assertEqual(calls[2][1], {
            "tag_name": self.tag, "target_commitish": self.sha, "name": self.tag,
            "draft": False, "prerelease": False, "body": ""})
        self.assertEqual(len(calls), 5)
        for endpoint, payload, asset in calls[3:]:
            self.assertIn("/releases/123/assets?name=NSSpeechRecognizer-", endpoint)
            self.assertIsNone(payload)
            self.assertIsNotNone(asset)

    def tag_race(self, sha):
        calls = []
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls, race=sha)):
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(self.sha, self.assets())
        self.assertEqual(len(calls), 2)
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), sha)
        self.assertIsNone(self.published)

    def test_same_sha_tag_race(self):
        self.tag_race(self.sha)

    def test_different_sha_tag_race(self):
        self.advance_peer()
        self.tag_race(git(self.peer, "rev-parse", "HEAD"))

    def retention_failure(self, fail=None, malformed=None):
        calls = []
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(
                    calls, fail=fail, malformed=malformed)):
            with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                release.publish(self.sha, self.assets())
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)
        return calls

    def test_release_post_failure_retains_tag(self):
        self.assertEqual(len(self.retention_failure(fail="release")), 3)
        self.assertIsNone(self.published)
        self.assertEqual(self.uploaded, [])

    def test_first_upload_failure_retains_tag_release(self):
        self.assertEqual(len(self.retention_failure(fail=".zip")), 4)
        self.assertEqual(self.published["id"], 123)
        self.assertEqual(self.uploaded, [])

    def test_later_upload_failure_retains_earlier_asset(self):
        self.assertEqual(len(self.retention_failure(fail=".dmg")), 5)
        self.assertEqual(self.published["id"], 123)
        self.assertEqual(self.uploaded, [f"NSSpeechRecognizer-{self.version}.zip"])

    def test_malformed_tag_post_retains_tag_stops_release(self):
        self.assertEqual(len(self.retention_failure(malformed="tag")), 2)
        self.assertIsNone(self.published)

    def test_malformed_release_post_retains_tag_release(self):
        self.assertEqual(len(self.retention_failure(malformed="release")), 3)
        self.assertEqual(self.published["id"], 123)

    def test_malformed_upload_retains_state(self):
        self.assertEqual(len(self.retention_failure(malformed="upload")), 4)
        self.assertEqual(self.published["id"], 123)
        self.assertEqual(self.uploaded, [f"NSSpeechRecognizer-{self.version}.zip"])

    def test_early_then_final_recheck_new_draft(self):
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=[
                    [], [entry(self.tag, True)]
                ]) as api:
            self.assertEqual(release.preflight(self.sha), (self.version, self.tag))
            with self.assertRaisesRegex(ValueError, "draft or published"):
                release.publish(self.sha, self.assets())
            self.assertEqual(api.call_count, 2)
        self.assertEqual(git(self.remote, "tag", "--list"), "")
        self.assertIsNone(self.published)

    def test_final_recheck_later_page_failure(self):
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=[
                    [entry()] * 100, subprocess.CalledProcessError(1, ["gh", "api"])
                ]) as api:
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(self.sha, self.assets())
            self.assertEqual(api.call_count, 2)
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_remote_verification_blocks_release_retains_tag(self):
        calls = []
        real_remote_ref = release.remote_ref

        def incorrect_verification(ref):
            return "a" * 40 if real_remote_ref(ref) else None

        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls)), \
                patch.object(release, "remote_ref", side_effect=incorrect_verification):
            with self.assertRaisesRegex(ValueError, "exact-SHA verification"):
                release.publish(self.sha, self.assets())
        self.assertEqual(len(calls), 2)
        self.assertIsNone(self.published)
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)

    def test_missing_empty_wrong_assets_before_mutation(self):
        for paths in (
            [Path(f"NSSpeechRecognizer-{self.version}.{ext}") for ext in ("zip", "dmg")],
            [Path("wrong.zip"), Path("wrong.dmg")],
        ):
            with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                    patch.object(release, "api") as api:
                with self.assertRaises(ValueError):
                    release.publish(self.sha, paths)
                api.assert_not_called()
        paths = self.assets()
        paths[0].write_bytes(b"")
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api") as api:
            with self.assertRaises(ValueError):
                release.publish(self.sha, paths)
            api.assert_not_called()


class WiringTests(unittest.TestCase):
    def test_native_steps_preserved_except_fresh_output_and_strict_architecture_gates(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        native = "      - name: import Developer ID certificate" + workflow.split(
            "      - name: import Developer ID certificate", 1
        )[1].split("      - name: final availability", 1)[0]
        baseline = git(ROOT, "show",
                       "a794ef61baedbd3c6f5955dc6142a0de3469a4f6:.github/workflows/release.yml")
        original = "      - name: import Developer ID certificate" + baseline.split(
            "      - name: import Developer ID certificate", 1
        )[1].split("      - name: create GitHub Release", 1)[0]
        original = original.replace(
            '          lipo -info "$BIN" | grep -q "arm64" && lipo -info "$BIN" | grep -q "x86_64"',
            '          lipo -info "$BIN" | grep -q "arm64"\n'
            '          lipo -info "$BIN" | grep -q "x86_64"',
        )
        original = original.replace(
            '      - name: build macOS plugin (universal)\n        run: |\n',
            '      - name: build macOS plugin (universal)\n        run: |\n'
            '          set -euo pipefail\n'
            '          PLUGINS_DIR="${{ env.PRODUCT_NAME }}.4dbase/Plugins"\n'
            '          BUNDLE_PATH="${PLUGINS_DIR}/${{ env.PRODUCT_NAME }}.bundle"\n'
            '          # Keep committed resources and legacy Windows files, not stale macOS output.\n'
            '          rm -rf "${BUNDLE_PATH}/Contents/MacOS" "${PLUGINS_DIR}/Default"\n',
        ).replace(
            '            CODE_SIGNING_ALLOWED=NO \\\n',
            '            CODE_SIGNING_ALLOWED=NO \\\n'
            '            CONFIGURATION_BUILD_DIR="$PWD/${PLUGINS_DIR}" \\\n',
        )
        self.assertEqual(native, original)

    def test_manual_zero_inputs_immutable_native_gate_wiring(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertRegex(workflow, r"(?m)^name: Build$")
        self.assertEqual(workflow.split("on:\n", 1)[1].split("\npermissions:", 1)[0].strip(),
                         "workflow_dispatch:")
        self.assertEqual(workflow.count("uses: actions/checkout@v4"), 2)
        self.assertEqual(workflow.count("ref: ${{ github.sha }}"), 2)
        self.assertIn("group: release-publication\n  cancel-in-progress: false", workflow)
        self.assertIn("needs: [version]", workflow)
        self.assertEqual(workflow.count("GH_TOKEN: ${{ github.token }}"), 2)
        gates = [
            "release.py preflight",
            "import Developer ID certificate", "store notarytool credentials",
            "build macOS plugin (universal)", "verify universal binary",
            "- name: codesign", "package, notarize & staple",
            "final availability check and create-only publication",
        ]
        self.assertEqual([workflow.index(gate) for gate in gates],
                         sorted(workflow.index(gate) for gate in gates))
        for required in ('ARCHS="arm64 x86_64"', "CODE_SIGNING_ALLOWED=NO",
                         "codesign --verify --deep --strict", 'stapler staple "$DMG_PATH"',
                         'notarytool submit "$ZIP_PATH"', 'notarytool submit "$DMG_PATH"',
                         '--keychain "$KEYCHAIN_PATH" --wait', "MACOS_DEPLOYMENT_TARGET: '11.0'",
                         "APPLE_DEVELOPER_ID_CERTIFICATE", "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
                         "KEYCHAIN_PASSWORD", "NOTARYTOOL_APPLE_ID", "NOTARYTOOL_TEAM_ID",
                         "NOTARYTOOL_PASSWORD", "runs-on: macos-latest"):
            self.assertIn(required, workflow)
        self.assertIn('CONFIGURATION_BUILD_DIR="$PWD/${PLUGINS_DIR}"', workflow)
        self.assertIn('rm -rf "${BUNDLE_PATH}/Contents/MacOS" "${PLUGINS_DIR}/Default"', workflow)
        self.assertNotIn('grep -q "arm64" &&', workflow)
        for prohibited in ("continue-on-error", "always()", "${{ inputs.", "softprops/",
                           "github.ref_name", "branches:", "REF_TYPE", "build-windows",
                           "windows-latest", "refs/heads/master"):
            self.assertNotIn(prohibited, workflow)
        final = workflow.split("- name: final availability", 1)[1]
        self.assertEqual(final.count("python3 "), 1)
        self.assertIn('publish --sha "$SELECTED_SHA" "$ZIP_PATH" "$DMG_PATH"', final)

    def test_bump_guarded_source_only_and_no_destructive_publication(self):
        workflow = (ROOT / ".github/workflows/bump-version.yml").read_text()
        self.assertIn("ref: ${{ github.sha }}", workflow)
        self.assertIn("SELECTED_BRANCH: ${{ github.ref_name }}", workflow)
        self.assertIn('test "$REF_TYPE" = branch', workflow)
        for mode in ("patch", "minor", "major"):
            self.assertIn(f"- {mode}", workflow)
        helper = (ROOT / ".github/scripts/release.py").read_text()
        for prohibited in ('"DELETE"', '"PATCH"', "--clobber", "--force",
                           '"gh", "release", "create"', '"git", "tag"'):
            self.assertNotIn(prohibited, helper)
        self.assertIn('"push.followTags=false"', helper)
        self.assertIn('"--no-follow-tags"', helper)
        self.assertNotIn("workflow_dispatch", helper)
        self.assertEqual(helper.count('not os.access(guard, os.X_OK)'), 2)

    def test_cli_asset_options(self):
        assets = [Path(f"NSSpeechRecognizer-1.2.3.{ext}") for ext in ("zip", "dmg")]
        with patch.object(sys, "argv", ["release.py", "publish", "--sha", "a" * 40,
                                       *map(str, assets)]), \
                patch.object(release, "publish") as publish:
            release.main()
        publish.assert_called_once_with("a" * 40, assets)


if __name__ == "__main__":
    unittest.main()
