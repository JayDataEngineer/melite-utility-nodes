# Auto-load workflows for the ComfyUI canvas

ComfyUI serves this folder at `/api/workflow_templates/melite-utility-nodes/`.
The Vue frontend auto-loads a workflow into the canvas when the page opens
with `?template=<name>&source=melite-utility-nodes` (it fetches
`/api/workflow_templates/melite-utility-nodes/<name>.json`).

The melite server writes exported YAML-pipeline workflows here so they can be
deep-linked into a running ComfyUI canvas — no drag-and-drop:

    POST /v1/pipelines/yaml/export-comfyui
    {"yaml": "character_trellis_ref.yaml", "auto_load": true}
    → {"workflow": {...}, "load_url": "http://localhost:18465/?template=character_trellis_ref&source=melite-utility-nodes"}

Generated `.json` files are gitignored (see `.gitignore` in this folder).
The folder must exist when the ComfyUI container starts for the static
route to be registered.
