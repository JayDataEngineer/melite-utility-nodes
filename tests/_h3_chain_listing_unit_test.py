#!/usr/bin/env python3
"""The chain-store listing routes' unit tests (the F19 deferred-upscale
discovery seat, 2026-11-12): a run name resolves to each scene's saved
revision ids, newest last — the selection headless graphs need before a
MiniMaxH3ChainCheckpointManager can claim a lineage.

Weight-free: folder_paths is stubbed to a temp output dir; the laws
judged here are the listing's own — revision grammar (clip_%04d.<rev32>
only, newest by mtime wins), contiguous scene enumeration, the loud
empty-run 404 naming live alternatives, and the bare-query 400.
"""

import importlib.util
import json
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class _FolderPaths(types.SimpleNamespace):
    pass


def _install_folder_paths(output_dir: str):
    """Stub ComfyUI's folder_paths for the TEST'S LIFETIME — the
    listing helpers import it at call time, not load time."""
    stub = _FolderPaths()
    stub.get_output_directory = lambda: output_dir
    prior = sys.modules.get("folder_paths")
    sys.modules["folder_paths"] = stub
    return prior


def _load_nodes():
    spec = importlib.util.spec_from_file_location(
        "melite_utility_chains_test", ROOT / "nodes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Request(types.SimpleNamespace):
    pass


def _checkpoint(root, run, scene, revision, mtime=None):
    path = os.path.join(root, "h3_chains", run, "checkpoints",
                        f"clip_{scene:04d}.{revision}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(b"{}")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


_REV_A = "a" * 32
_REV_B = "b" * 32


class ChainStoreListingUnitTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = self._tmp.name
        self._prior = _install_folder_paths(self.out)
        self.nodes = _load_nodes()
        # upstream's store layout, exactly as the format guide writes it
        _checkpoint(self.out, "run_alpha", 1, _REV_A, mtime=100.0)
        _checkpoint(self.out, "run_alpha", 2, _REV_B, mtime=100.0)
        # noise the listing must ignore
        junk_dir = os.path.join(self.out, "h3_chains", "run_alpha",
                                "checkpoints")
        for name in ("clip_1.not-a-rev.json", "clip_0009."
                     + _REV_A + ".txt", "notes.md",
                     "clip_0003.short.json"):
            with open(os.path.join(junk_dir, name), "wb") as handle:
                handle.write(b"")
        # a sibling run: present but EMPTY of checkpoints — not offered
        os.makedirs(os.path.join(self.out, "h3_chains", "run_empty"))

    def tearDown(self):
        if self._prior is None:
            sys.modules.pop("folder_paths", None)
        else:
            sys.modules["folder_paths"] = self._prior
        self._tmp.cleanup()

    def _body(self, response):
        return json.loads(response.text)

    def test_runs_listing_offers_only_runs_with_checkpoints(self):
        listing = self._body(self.nodes._h3_chain_runs_command(_Request()))
        self.assertEqual([r["run_name"] for r in listing["runs"]],
                         ["run_alpha"])
        self.assertEqual(listing["runs"][0]["scenes"], 2)

    def test_checkpoints_enumerate_revisions_newest_last(self):
        # a second revision for scene 1, saved LATER — newest wins `latest`
        time.sleep(0.01)
        newer = "c" * 32
        _checkpoint(self.out, "run_alpha", 1, newer, mtime=time.time())
        listing = self._body(
            self.nodes._h3_chain_checkpoints_command(
                _Request(query={"run": "run_alpha"})))
        self.assertEqual(listing["run_name"], "run_alpha")
        self.assertEqual(
            listing["scenes"],
            [
                {"scene": 1, "revisions": [_REV_A, newer], "latest": newer},
                {"scene": 2, "revisions": [_REV_B], "latest": _REV_B},
            ],
        )

    def test_unknown_run_refuses_loud_naming_live_runs(self):
        response = self.nodes._h3_chain_checkpoints_command(
            _Request(query={"run": "run_ghost"}))
        self.assertEqual(response.status, 404)
        body = self._body(response)
        self.assertIn("run_ghost", body["error"])
        self.assertEqual(body["runs"], ["run_alpha"])

    def test_missing_run_query_is_a_400(self):
        response = self.nodes._h3_chain_checkpoints_command(
            _Request(query={}))
        self.assertEqual(response.status, 400)
        self.assertIn("run", self._body(response)["error"])


if __name__ == "__main__":
    unittest.main()
