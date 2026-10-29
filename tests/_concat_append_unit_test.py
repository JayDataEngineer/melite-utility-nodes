#!/usr/bin/env python3
"""The append member's unit tests (the compose face of the film tail,
2026-11-12 multi-window unification): an EXACT saved-file path joins
as the concat's LAST member after the prefix list — the in-chain
assembly (ChainAssemble's wired video_path) joining a by-file head.

Weight-free: folder_paths is stubbed to a temp output dir; the laws
judged here are the member grammar's own — exact resolution (absolute
+ output-relative), the loud missing-file refusal, append-last film
order, and the prefix law's unchanged behavior beside it.
"""

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class _FolderPaths(types.SimpleNamespace):
    pass


def _install_folder_paths(output_dir: str):
    """Stub ComfyUI's folder_paths for the TEST'S LIFETIME — the
    resolution helpers import it at call time, not load time."""
    stub = _FolderPaths()
    stub.get_output_directory = lambda: output_dir
    prior = sys.modules.get("folder_paths")
    sys.modules["folder_paths"] = stub
    return prior


def _load_nodes():
    spec = importlib.util.spec_from_file_location(
        "melite_utility_concat_test", ROOT / "nodes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConcatAppendUnitTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = self._tmp.name
        # a legal prefix member: SaveVideo's counter-named write
        self.prefix_file = os.path.join(self.out, "run_x0_00001_.mp4")
        with open(self.prefix_file, "wb") as handle:
            handle.write(b"")
        self._prior = _install_folder_paths(self.out)
        self.nodes = _load_nodes()

    def tearDown(self):
        if self._prior is None:
            sys.modules.pop("folder_paths", None)
        else:
            sys.modules["folder_paths"] = self._prior
        self._tmp.cleanup()

    def test_append_resolves_absolute_and_relative(self):
        exact = os.path.join(self.out, "assembled.mp4")
        with open(exact, "wb") as handle:
            handle.write(b"")
        self.assertEqual(
            self.nodes._resolve_append_path(exact), exact)
        self.assertEqual(
            self.nodes._resolve_append_path("assembled.mp4"), exact)

    def test_append_missing_file_refuses_loud(self):
        with self.assertRaises(RuntimeError) as caught:
            self.nodes._resolve_append_path("nowhere.mp4")
        self.assertIn("resolves to no file", str(caught.exception))

    def test_append_empty_refuses_loud(self):
        with self.assertRaises(RuntimeError) as caught:
            self.nodes._resolve_append_path("  ")
        self.assertIn("'append' is empty", str(caught.exception))

    def test_members_append_lasts_in_film_order(self):
        os.makedirs(os.path.join(self.out, "run"), exist_ok=True)
        nested = os.path.join(self.out, "run", "x0_00001_.mp4")
        with open(nested, "wb") as handle:
            handle.write(b"")
        exact = os.path.join(self.out, "chain_final.mp4")
        with open(exact, "wb") as handle:
            handle.write(b"")
        members = self.nodes._concat_members("run/x0", exact)
        self.assertEqual(len(members), 2)
        self.assertEqual(members[0][0], "run/x0")
        self.assertEqual(members[0][1], nested)
        self.assertEqual(members[1][0], exact)
        self.assertEqual(members[1][1], exact)

    def test_members_without_append_keep_the_prefix_law(self):
        members = self.nodes._concat_members("run_x0", "")
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0][1], self.prefix_file)

    def test_append_is_an_optional_input(self):
        # the compose face's seat: append rides OPTIONAL (omitted by
        # every plain film join; the required seat would demand the
        # field even where no assembly exists)
        inputs = self.nodes.MeliteConcatVideos.INPUT_TYPES()
        self.assertNotIn("append", inputs["required"])
        self.assertIn("append", inputs["optional"])
        self.assertEqual(inputs["optional"]["append"][1]["default"], "")

    def test_prefix_member_still_globbed_by_counter(self):
        newer = os.path.join(self.out, "run_x0_00002_.mp4")
        with open(newer, "wb") as handle:
            handle.write(b"")
        members = self.nodes._concat_members("run_x0", "")
        self.assertEqual(members[0][1], newer)


if __name__ == "__main__":
    unittest.main()
