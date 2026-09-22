"""Tech Noir utility nodes for ComfyUI.

General-purpose nodes that improve the dev workflow:

  GLBPreview     — OUTPUT_NODE that previews a GLB at any graph point.
                   Unlike SaveRiggedModel (auto-rig specific), this works
                   with ANY glb_path STRING — Trellis output, AniGen output,
                   composite_character, or a loaded file. Also handles GLBs
                   outside ComfyUI's output/ dir by symlinking them in.
                   The web extension adds an inline, rotatable 3D viewer
                   (powered by Three.js via ComfyUI-3D-Pack's iframe).

  GLBLoader      — typed GLB file selector. Instead of typing a raw path
                   STRING, the user picks from a dropdown of GLB files in
                   ComfyUI's input/ directory. Returns the same STRING type
                   so it drops into any existing glb_path input slot.

  TypedModelDir  — typed model-directory selector. Lists subdirectories of
                   a configured model root (env var or explicit path) as a
                   COMBO dropdown. AnigenLoader etc. can accept this in
                   place of their ckpt_root STRING input, giving users a
                   file picker instead of a text field.

  MotionPreview  — OUTPUT_NODE that previews a SOMA-77 motion NPZ file.
                   Renders a stick-figure skeleton at keyframe poses and
                   returns them as an animated preview. Accepts the NPZ
                   path STRING output of KimodoTextToPose or HYMotion nodes.

  MeliteUnload   — the film tail's memory boundary (roadmap §20, the
                   in-graph amendment): consumes the last window's
                   SaveVideo passthrough (the ordering wire — downstream
                   file-loaders wait for the saves) and flushes the CUDA
                   allocator WITHOUT dropping model weights (the next
                   run pays no reload; unload_models=True for a full wipe).

  MeliteConcatVideos — the film-assemble loader: decodes saved window
                   FILES back into the graph (output-dir prefixes →
                   IMAGE + AUDIO + fps), so the film is a pure graph
                   output assembled strictly after every save completed.
"""
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

WEB_DIRECTORY = "./web"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
