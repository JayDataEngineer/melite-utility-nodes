"""Tech Noir utility nodes — GLB preview, typed GLB loader, typed model dirs.

Design rationale:

  GLBPreview   — ComfyUI-3D-Pack's viewer hooks into OUTPUT_NODE ui data
    under the key ``three_model``. But most GLB-producing nodes in our
    pipeline (Trellis, AniGen, composite_character) either aren't
    OUTPUT_NODEs or produce a STRING path that isn't in ComfyUI's
    output/ directory. GLBPreview bridges this gap: point it at any GLB
    path, and it will (a) symlink/copy the file into output/ if it lives
    elsewhere, and (b) emit the three_model UI data the viewer needs.

  GLBLoader    — ComfyUI's native loaders (CheckpointLoaderSimple,
    VAELoader, etc.) use ``folder_paths.get_filename_list()`` to populate
    a COMBO dropdown instead of forcing users to type paths. GLBLoader
    applies the same pattern to GLB files in the input/ directory. The
    output type is STRING (not a new custom type) so it drops into ANY
    existing glb_path input without graph changes.

  TypedModelDir — same idea but for directory roots. AnigenLoader's
    ``ckpt_root`` is a STRING defaulting to /mnt/data/models/3d/anigen/ckpts.
    TypedModelDir lists subdirectories of a configured root, returning a
    STRING path. Used as a drop-in replacement for raw STRING ckpt_root.
"""
from __future__ import annotations

import logging
import os
import shutil
from typing import Any

log = logging.getLogger(__name__)

# ── GLB file extensions we recognize ──────────────────────────────────
_GLB_EXTS = (".glb", ".gltf", ".obj", ".stl", ".fbx")
# Cap symlink/copy size at 500 MB — anything bigger is likely a mistake.
_MAX_COPY_BYTES = 500 * 1024 * 1024


def _list_glb_files(directory: str) -> list[str]:
    """List GLB-compatible files in a directory, sorted alphabetically."""
    if not os.path.isdir(directory):
        return []
    files = []
    for name in sorted(os.listdir(directory)):
        if name.lower().endswith(_GLB_EXTS):
            files.append(name)
    return files


def _list_subdirs(directory: str) -> list[str]:
    """List immediate subdirectories of a directory, sorted.

    Hidden entries (dotfiles, e.g. ``.cache``) are excluded so model
    dropdowns don't surface noise.
    """
    if not os.path.isdir(directory):
        return []
    return sorted(
        name for name in os.listdir(directory)
        if not name.startswith(".")
        and os.path.isdir(os.path.join(directory, name))
    )


def _ensure_in_output(glb_path: str) -> tuple[str, str, str]:
    """Ensure a GLB file is inside ComfyUI's output directory.

    Returns ``(filename, subfolder, type)`` for the three_model UI data.

    If the file is already in output/, returns its relative position.
    If it's elsewhere (input/, /tmp/, /mnt/data/), creates a symlink in
    output/ so /view can serve it. Falls back to copy if symlink fails
    (cross-device) and the file is under _MAX_COPY_BYTES.

    Raises FileNotFoundError if the path doesn't exist.
    """
    import folder_paths  # ComfyUI core — available at runtime

    if not glb_path or not glb_path.strip():
        raise ValueError("GLB path is empty")

    src = os.path.abspath(glb_path.strip())
    if not os.path.isfile(src):
        # Try resolving relative to input/ and output/ first.
        for d in (folder_paths.get_input_directory(), folder_paths.get_output_directory()):
            candidate = os.path.join(d, glb_path)
            if os.path.isfile(candidate):
                src = candidate
                break
        else:
            raise FileNotFoundError(
                f"GLB file not found: {glb_path} "
                f"(checked absolute path, input/, output/)"
            )

    output_dir = folder_paths.get_output_directory()
    # Check if already inside output/.
    try:
        rel = os.path.relpath(src, output_dir)
        if not rel.startswith(".."):
            # Already in output — return relative position.
            parent = os.path.dirname(rel)
            subfolder = parent if parent and parent != "." else ""
            return os.path.basename(src), subfolder, "output"
    except ValueError:
        pass  # different drive on Windows — fall through to symlink

    # Need to bring it into output/. Try symlink first (instant, zero space).
    filename = os.path.basename(src)
    # Add a prefix to avoid collisions with generated files.
    dest_name = f"preview_{filename}"
    dest = os.path.join(output_dir, dest_name)
    if os.path.exists(dest) or os.path.islink(dest):
        # Already linked from a previous preview — reuse.
        if os.path.islink(dest) and os.readlink(dest) == src:
            return dest_name, "", "output"
        os.remove(dest)
    try:
        os.symlink(src, dest)
        log.info("GLBPreview: symlinked %s → %s", src, dest)
    except OSError:
        # Cross-device or no symlink permission — copy if small enough.
        size = os.path.getsize(src)
        if size > _MAX_COPY_BYTES:
            raise RuntimeError(
                f"GLB file is {size / 1024 / 1024:.0f} MB and lives outside "
                f"ComfyUI's output directory. Symlink failed (likely "
                f"cross-device). Either move the file into output/ manually "
                f"or reduce its size. Path: {src}"
            )
        shutil.copy2(src, dest)
        log.info("GLBPreview: copied %s → %s (%d MB)", src, dest, size / 1024 / 1024)

    return dest_name, "", "output"


# ════════════════════════════════════════════════════════════════════════
# Node 1: GLBPreview — 3D preview at any graph point
# ════════════════════════════════════════════════════════════════════════
class GLBPreview:
    """Preview a GLB file in ComfyUI's 3D viewer at any point in the graph.

    Accepts a STRING glb_path (the output type of Trellis, AniGen,
    composite_character, etc.) and emits the ``three_model`` UI data that
    ComfyUI-3D-Pack's viewer renders. The path passes through unchanged
    so downstream nodes still receive it.

    If the GLB lives outside ComfyUI's output/ directory (e.g. in /tmp/
    or /mnt/data/), it's symlinked into output/ so the /view endpoint can
    serve it to the browser.

    Use cases:
      - Preview an intermediate Trellis mesh before auto-rigging.
      - Preview a composite character before motion baking.
      - Inspect any GLB file from disk in the canvas.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "glb_path": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "forceInput": True,
                        "tooltip": (
                            "Path to a GLB/GLTF/OBJ/FBX file. Can be "
                            "absolute or relative to ComfyUI's input/ "
                            "and output/ directories."
                        ),
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("glb_path",)
    FUNCTION = "preview"
    CATEGORY = "TechNoir/Utility"
    OUTPUT_NODE = True

    def preview(self, glb_path: str):
        filename, subfolder, file_type = _ensure_in_output(glb_path)
        return {
            "result": (glb_path,),
            "ui": {
                "three_model": [{
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": file_type,
                }],
            },
        }

    @classmethod
    def IS_CHANGED(cls, glb_path: str):
        # Re-preview whenever the file's mtime changes.
        try:
            return os.path.getmtime(glb_path) if glb_path else 0
        except OSError:
            return 0


# ════════════════════════════════════════════════════════════════════════
# Node 2: GLBLoader — typed GLB file dropdown
# ════════════════════════════════════════════════════════════════════════
class GLBLoader:
    """Load a GLB file from ComfyUI's input/ directory via dropdown.

    Instead of typing a raw path STRING, the user picks from a list of
    GLB-compatible files in input/. Returns the STRING path so it drops
    into any glb_path input slot without graph changes.

    The file list is populated at workflow-parse time via INPUT_TYPES,
    so the dropdown refreshes when the user clicks "refresh" on the node
    or reloads the page.
    """

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        input_dir = folder_paths.get_input_directory()
        files = _list_glb_files(input_dir)
        if not files:
            files = ["(no GLB files in input/)"]
        return {
            "required": {
                "glb_file": (
                    files,
                    {
                        "default": files[0],
                        "tooltip": (
                            "GLB file in ComfyUI's input/ directory. "
                            "Upload GLBs via the standard ComfyUI "
                            "image upload mechanism."
                        ),
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("glb_path",)
    FUNCTION = "load"
    CATEGORY = "TechNoir/Utility"
    OUTPUT_NODE = False

    def load(self, glb_file: str):
        import folder_paths
        if glb_file.startswith("("):
            raise ValueError(
                f"No GLB file selected ({glb_file}). "
                f"Upload a GLB to ComfyUI's input/ directory first."
            )
        input_dir = folder_paths.get_input_directory()
        path = os.path.join(input_dir, glb_file)
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"GLB file not found: {glb_file} "
                f"(expected at {path}). The file may have been moved or "
                f"deleted. Refresh the node to update the dropdown."
            )
        log.info("GLBLoader: loaded %s", path)
        return (path,)

    @classmethod
    def IS_CHANGED(cls, glb_file: str):
        import folder_paths
        input_dir = folder_paths.get_input_directory()
        path = os.path.join(input_dir, glb_file)
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0


# ════════════════════════════════════════════════════════════════════════
# Node 3: TypedModelDir — typed model directory dropdown
# ════════════════════════════════════════════════════════════════════════
class TypedModelDir:
    """Select a model subdirectory from a configured root via dropdown.

    Replaces the raw STRING inputs on nodes like AniGenLoader where users
    had to type paths like ``/mnt/data/models/3d/anigen/ckpts``. Instead,
    the user picks from a dropdown of subdirectories under the configured
    model root.

    The root is resolved from (in priority order):
      1. The ``model_root`` input slot (if wired).
      2. The ``MODEL_ROOT_<KEY>`` environment variable.
      3. The ``default_root`` parameter.

    Returns the full path as a STRING so it drops into any existing
    path input slot.
    """

    @classmethod
    def INPUT_TYPES(cls):
        # The root key determines which env var to check.
        # E.g. key="anigen" → MODEL_ROOT_ANIGEN.
        return {
            "required": {
                "root_key": (
                    ["anigen", "trellis", "somax", "custom"],
                    {
                        "default": "custom",
                        "tooltip": (
                            "Which model root to browse. Selects the "
                            "env var MODEL_ROOT_<KEY>. Use 'custom' to "
                            "type an explicit root path."
                        ),
                    },
                ),
                "custom_root": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "forceInput": True,
                        "tooltip": (
                            "Explicit root path (used when root_key="
                            "'custom' or when the env var is not set)."
                        ),
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("directory",)
    FUNCTION = "select"
    CATEGORY = "TechNoir/Utility"
    OUTPUT_NODE = False

    # Cache the last-seen subdirectory list so VALIDATE_INPUTS can check
    # without calling INPUT_TYPES again (which would re-scan the disk).
    _last_dirs: dict[str, list[str]] = {}

    def select(self, root_key: str, custom_root: str):
        root = self._resolve_root(root_key, custom_root)
        if not root or not os.path.isdir(root):
            raise FileNotFoundError(
                f"Model root not found or not a directory: {root}\n"
                f"Set MODEL_ROOT_{root_key.upper()} or provide custom_root."
            )
        # Return the root itself. Downstream nodes (AniGenLoader etc.)
        # take it from here. The user connects this output to ckpt_root.
        return (root,)

    @classmethod
    def _resolve_root(cls, root_key: str, custom_root: str) -> str:
        """Resolve the model root directory from env var or custom_root."""
        if root_key == "custom":
            return custom_root.strip()
        env_var = f"MODEL_ROOT_{root_key.upper()}"
        env_val = os.environ.get(env_var, "").strip()
        if env_val:
            return env_val
        # Fall back to custom_root if the env var isn't set.
        return custom_root.strip()

    @classmethod
    def IS_CHANGED(cls, root_key: str, custom_root: str):
        root = cls._resolve_root(root_key, custom_root)
        try:
            # Changed when the root directory's mtime changes
            # (new subdirectories added/removed).
            return os.path.getmtime(root)
        except OSError:
            return 0


# ════════════════════════════════════════════════════════════════════════
# Model-dir pickers — typed dropdowns for family-specific model roots
# ════════════════════════════════════════════════════════════════════════
# Each loader node (KimodoLoader ``model_name``, HYMotionTextTo3D
# ``model_path``, SeeThroughDecompose ``layerdiff_path``/``marigold_path``)
# exposes a raw STRING input. That forces canvas users to hand-type
# absolute paths like
#   /mnt/data/models/image-gen/comfyui/HY-Motion/ckpts/tencent/HY-Motion-1.0
#
# These pickers apply the same COMBO-dropdown pattern as GLBLoader: they
# enumerate the real model subdirectories on disk at INPUT_TYPES time and
# return a STRING, so they drop straight into the existing STRING inputs
# with zero graph changes. The headless server path (builders.py passing
# model_path/model_name explicitly) is untouched.

def _make_model_dir_picker(
    node_name: str,
    display_name: str,
    env_var: str,
    default_root: str,
    path_format: str = "path",
    tooltip: str = "",
):
    """Factory for a model-directory dropdown node.

    Args:
        node_name: ComfyUI node class name (also the mapping key).
        display_name: Human-readable name for the node menu.
        env_var: Environment variable holding the root directory.
        default_root: Fallback root when the env var is unset.
        path_format: What the node returns for the selected subdir:
            - "path"       → absolute path to the subdir
            - "name"       → bare subdir name (e.g. Kimodo model_name,
                             which load_model resolves against CHECKPOINT_DIR)
            - "nested"     → ``<root>/<subdir>/<subdir>`` (HY-Motion's
                             ckpt layout puts the model dir inside a
                             same-named wrapper dir).
    """
    if not tooltip:
        tooltip = (
            f"Model subdirectory under {default_root} "
            f"(set {env_var} to override)."
        )

    class _ModelDirPicker:
        @classmethod
        def INPUT_TYPES(cls):
            root = os.environ.get(env_var, default_root)
            dirs = _list_subdirs(root)
            if not dirs:
                dirs = ["(no model directories found)"]
            return {
                "required": {
                    "model_dir": (
                        dirs,
                        {
                            "default": dirs[0],
                            "tooltip": tooltip,
                        },
                    ),
                },
            }

        RETURN_TYPES = ("STRING",)
        RETURN_NAMES = ("model_path",)
        FUNCTION = "pick"
        CATEGORY = "TechNoir/Utility"
        OUTPUT_NODE = False

        def pick(self, model_dir: str):
            if model_dir.startswith("("):
                raise ValueError(
                    f"No model directories found under "
                    f"{os.environ.get(env_var, default_root)}. "
                    f"Set {env_var} or mount the models to enable this node."
                )
            root = os.environ.get(env_var, default_root)
            if path_format == "name":
                return (model_dir,)
            if path_format == "nested":
                return (os.path.join(root, model_dir, model_dir),)
            return (os.path.join(root, model_dir),)

        @classmethod
        def IS_CHANGED(cls, model_dir: str):
            root = os.environ.get(env_var, default_root)
            try:
                return os.path.getmtime(root)
            except OSError:
                return 0

    _ModelDirPicker.__name__ = node_name
    _ModelDirPicker.__qualname__ = node_name
    _ModelDirPicker.__doc__ = (
        f"Pick a {display_name} model directory from a dropdown. "
        f"Returns a STRING path compatible with the loader's raw input."
    )
    return _ModelDirPicker


# KimodoLoader.model_name — load_model() resolves the name against
# CHECKPOINT_DIR, so we return the bare subdir name.
KimodoModelDir = _make_model_dir_picker(
    node_name="KimodoModelDir",
    display_name="Kimodo",
    env_var="CHECKPOINT_DIR",
    default_root="/mnt/data/models/avatar/kimodo",
    path_format="name",
    tooltip=(
        "Kimodo checkpoint (model_name). The name is resolved against "
        "CHECKPOINT_DIR by kimodo.load_model."
    ),
)

# HYMotionTextTo3D.model_path — the ckpt lives at
# <root>/<variant>/<variant> (wrapper dir + same-named model dir).
HYMotionModelDir = _make_model_dir_picker(
    node_name="HYMotionModelDir",
    display_name="HY-Motion",
    env_var="HYMOTION_MODEL_ROOT",
    default_root="/mnt/data/models/image-gen/comfyui/HY-Motion/ckpts/tencent",
    path_format="nested",
    tooltip=(
        "HY-Motion checkpoint variant. Resolves to the nested model path "
        "<root>/<variant>/<variant> expected by HYMotionTextTo3D."
    ),
)

# SeeThroughDecompose.layerdiff_path / marigold_path — pick the model
# root once, wire the output to either input as needed.
SeeThroughModelDir = _make_model_dir_picker(
    node_name="SeeThroughModelDir",
    display_name="See-Through",
    env_var="SEETHROUGH_MODEL_ROOT",
    default_root="/mnt/data/models/image/see-through",
    path_format="path",
    tooltip=(
        "See-Through model subdirectory (layerdiff3d, marigold, …). "
        "Wire this into SeeThroughDecompose's layerdiff_path or "
        "marigold_path."
    ),
)

# AniGenLoader.ckpt_root — the root itself is the checkpoint directory;
# TypedModelDir already covers this via MODEL_ROOT_ANIGEN, so no separate
# picker node is needed here.


# ════════════════════════════════════════════════════════════════════════
# Node 4: MotionPreview — animated stick-figure preview for motion NPZ
# ════════════════════════════════════════════════════════════════════════

# SOMA-77 skeleton connectivity — pairs of joint indices forming bones.
# Joint indices follow the SOMA / Kimodo convention (22 joints).
# Reference: media/poser/soma_schema.py
_SOMA_BONES = [
    (0, 1),    # root → pelvis
    (1, 2),    # pelvis → spine
    (2, 3),    # spine → neck
    (3, 4),    # neck → head
    (2, 5),    # spine → left_shoulder
    (5, 6),    # left_shoulder → left_elbow
    (6, 7),    # left_elbow → left_wrist
    (2, 8),    # spine → right_shoulder
    (8, 9),    # right_shoulder → right_elbow
    (9, 10),   # right_elbow → right_wrist
    (1, 11),   # pelvis → left_hip
    (11, 12),  # left_hip → left_knee
    (12, 13),  # left_knee → left_ankle
    (1, 14),   # pelvis → right_hip
    (14, 15),  # right_hip → right_knee
    (15, 16),  # right_knee → right_ankle
]

_JOINT_NAMES = [
    "root", "pelvis", "spine", "neck", "head",
    "l_shoulder", "l_elbow", "l_wrist",
    "r_shoulder", "r_elbow", "r_wrist",
    "l_hip", "l_knee", "l_ankle",
    "r_hip", "r_knee", "r_ankle",
]


class MotionPreview:
    """Preview a SOMA-77 motion NPZ as animated stick-figure keyframes.

    Reads the joint 3D positions from the NPZ, renders N evenly-spaced
    keyframe poses as a single image grid, and returns it as a preview.
    This gives a quick visual summary of the motion without needing
    Blender or a full 3D viewport.

    The NPZ format follows the SOMA / Kimodo convention:
      - ``positions``: (T, J, 3) array of joint positions over T frames
        with J joints per frame.
      - ``quaternions``: (T, J, 4) array — optional, not used for preview.

    Use cases:
      - Inspect a KimodoTextToPose result before applying it to a rig.
      - Verify motion transfer quality before baking.
      - Debug motion interpolation artifacts.

    For a full 3D animated preview, use GLBPreview on the baked output.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "motion_path": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "forceInput": True,
                        "tooltip": (
                            "Path to a SOMA-77 motion NPZ file "
                            "(output of KimodoTextToPose or HYMotion)."
                        ),
                    },
                ),
                "num_keyframes": (
                    "INT",
                    {
                        "default": 6,
                        "min": 3,
                        "max": 12,
                        "tooltip": (
                            "Number of keyframe poses to render in the "
                            "grid. More frames = denser preview but "
                            "larger image."
                        ),
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("motion_path",)
    FUNCTION = "preview"
    CATEGORY = "TechNoir/Utility"
    OUTPUT_NODE = True

    def preview(self, motion_path: str, num_keyframes: int):
        if not motion_path or not motion_path.strip():
            raise ValueError("MotionPreview: motion_path is empty")

        path = motion_path.strip()
        # Resolve relative paths.
        if not os.path.isabs(path) or not os.path.isfile(path):
            import folder_paths
            for d in (folder_paths.get_input_directory(), folder_paths.get_output_directory()):
                candidate = os.path.join(d, path)
                if os.path.isfile(candidate):
                    path = candidate
                    break

        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"MotionPreview: NPZ not found: {motion_path}"
            )

        # Load the NPZ and render keyframes.
        import numpy as np

        data = np.load(path, allow_pickle=True)
        # Try common key names for joint positions.
        positions = None
        for key in ("positions", "joints", "joint_positions", "motion"):
            if key in data:
                arr = data[key]
                if arr.ndim == 3 and arr.shape[-1] == 3:
                    positions = arr
                    break
        if positions is None:
            # As a fallback, try the first array that looks like positions.
            for key in data.files:
                arr = data[key]
                if arr.ndim == 3 and arr.shape[-1] == 3:
                    positions = arr
                    break

        if positions is None:
            raise RuntimeError(
                f"MotionPreview: could not find joint positions in NPZ. "
                f"Expected (T, J, 3) array. Keys present: {list(data.files)}. "
                f"NPZ may not be a SOMA-77 motion file."
            )

        total_frames = positions.shape[0]
        n_joints = positions.shape[1]
        log.info(
            "MotionPreview: %s — %d frames, %d joints",
            os.path.basename(path), total_frames, n_joints,
        )

        # Select keyframe indices evenly across the motion.
        num_keyframes = max(3, min(num_keyframes, 12, total_frames))
        indices = np.linspace(0, total_frames - 1, num_keyframes, dtype=int)

        # Render the keyframe grid.
        preview_filename = self._render_keyframes(
            positions, indices, os.path.basename(path)
        )

        return {
            "result": (motion_path,),
            "ui": {
                "images": [{
                    "filename": preview_filename,
                    "subfolder": "",
                    "type": "output",
                }],
            },
        }

    def _render_keyframes(
        self,
        positions: Any,
        indices: Any,
        title: str,
    ) -> str:
        """Render keyframe poses as a grid image and save to output/.

        Returns the filename of the saved image.
        """
        import folder_paths

        # Use matplotlib (Agg backend — no display needed).
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        n_frames = len(indices)
        cols = min(3, n_frames)
        rows = (n_frames + cols - 1) // cols

        fig, axes = plt.subplots(
            rows, cols,
            figsize=(cols * 3, rows * 4),
            squeeze=False,
        )
        fig.suptitle(
            f"Motion Preview: {title}",
            fontsize=10, color="white", y=0.98,
        )
        fig.patch.set_facecolor("#1a1a2e")

        for i, frame_idx in enumerate(indices):
            ax = axes[i // cols][i % cols]
            pose = positions[frame_idx]

            # Plot bones.
            for parent, child in _SOMA_BONES:
                if parent < len(pose) and child < len(pose):
                    ys = [pose[parent, 2], pose[child, 2]]  # XZ plane (side view)
                    zs = [pose[parent, 1], pose[child, 1]]
                    ax.plot(ys, zs, "-", color="#e94560", linewidth=2.0)

            # Plot joints.
            ax.scatter(
                pose[:, 2], pose[:, 1],  # Y=XZ_side, Z=height
                c="#0f3460", s=20, zorder=5,
            )

            ax.set_title(
                f"Frame {frame_idx}",
                fontsize=8, color="#999",
            )
            ax.set_facecolor("#16213e")
            ax.set_aspect("equal")
            ax.tick_params(colors="#666", labelsize=6)

        # Hide unused subplots.
        for i in range(n_frames, rows * cols):
            axes[i // cols][i % cols].set_visible(False)

        plt.tight_layout(rect=[0, 0, 1, 0.95])

        # Save to ComfyUI's output directory.
        output_dir = folder_paths.get_output_directory()
        import time as _time
        filename = f"motion_preview_{int(_time.time())}.png"
        out_path = os.path.join(output_dir, filename)
        fig.savefig(out_path, dpi=100, facecolor=fig.get_facecolor())
        plt.close(fig)

        log.info("MotionPreview: rendered %d keyframes → %s", n_frames, filename)
        return filename

    @classmethod
    def IS_CHANGED(cls, motion_path: str, num_keyframes: int):
        try:
            return os.path.getmtime(motion_path) if motion_path else 0
        except OSError:
            return 0


# ════════════════════════════════════════════════════════════════════════
# Registration
# ════════════════════════════════════════════════════════════════════════
NODE_CLASS_MAPPINGS = {
    "GLBPreview": GLBPreview,
    "GLBLoader": GLBLoader,
    "TypedModelDir": TypedModelDir,
    "KimodoModelDir": KimodoModelDir,
    "HYMotionModelDir": HYMotionModelDir,
    "SeeThroughModelDir": SeeThroughModelDir,
    "MotionPreview": MotionPreview,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GLBPreview": "🖼️ GLB Preview",
    "GLBLoader": "📁 Load GLB (dropdown)",
    "TypedModelDir": "📂 Model Directory (dropdown)",
    "KimodoModelDir": "🧍 Kimodo Model (dropdown)",
    "HYMotionModelDir": "🕺 HY-Motion Model (dropdown)",
    "SeeThroughModelDir": "👕 See-Through Model (dropdown)",
    "MotionPreview": "🏃 Motion Preview",
}
