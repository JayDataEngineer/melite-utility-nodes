/**
 * Tech Noir Utility — Inline GLB Preview Extension
 *
 * Adds an inline, rotatable 3D viewer to GLBPreview nodes — the same
 * UX as PreviewImage but for 3D models. Leverages ComfyUI-3D-Pack's
 * threeVisualizer iframe (if available) so we don't ship a duplicate
 * Three.js bundle.
 *
 * Behavior:
 *   - On node creation: adds a 400×400 widget area and creates the
 *     iframe-based visualizer overlay.
 *   - On execution: reads the three_model UI data returned by the
 *     GLBPreview Python node and feeds the filepath to the iframe.
 *   - The viewer supports orbit rotation, zoom, and pan via Three.js
 *     OrbitControls (already loaded inside threeVisualizer.html).
 *
 * If ComfyUI-3D-Pack is not installed, the widget shows a message
 * directing the user to install it. The node's STRING passthrough
 * still works — only the visual preview is affected.
 */
import { app } from "/scripts/app.js"

const COMFY3D_HTML = "/extensions/ComfyUI-3D-Pack/html/threeVisualizer.html"
const WIDGET_TYPE = "ray_glb_preview_3d"
const MIN_W = 400
const MIN_H = 400

function createGLBVisualizer(node) {
    const container = document.createElement("div")
    container.id = `ray_glb_preview_${node.id}`
    container.style.cssText = "position:absolute;overflow:hidden;"

    const iframe = document.createElement("iframe")
    iframe.src = COMFY3D_HTML
    iframe.style.cssText = "width:100%;height:100%;border:0;"
    container.appendChild(iframe)

    // Fallback message shown if ComfyUI-3D-Pack isn't installed.
    // The iframe will 404 and show the browser's error page — we
    // overlay a helpful message instead.
    const fallback = document.createElement("div")
    fallback.style.cssText = `
        position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
        text-align:center;color:#999;font-family:sans-serif;font-size:13px;
        max-width:300px;line-height:1.5;
    `
    fallback.innerHTML = `
        <p>📦 ComfyUI-3D-Pack required</p>
        <p style="font-size:11px;color:#666">
            Install ComfyUI-3D-Pack for interactive 3D preview.
            The GLB path still passes through to downstream nodes.
        </p>
    `
    container.appendChild(fallback)

    // Hide fallback once the iframe loads successfully.
    iframe.addEventListener("load", () => {
        try {
            // If the iframe loaded real content (not a 404), hide fallback.
            if (iframe.contentWindow?.document?.getElementById("visualizer")) {
                fallback.style.display = "none"
            }
        } catch (e) {
            // Cross-origin — assume it loaded fine.
            fallback.style.display = "none"
        }
    })

    document.body.appendChild(container)
    return { container, iframe }
}

function updateVisualizerPath(node, filepath) {
    const widget = node.widgets?.find((w) => w.type === WIDGET_TYPE)
    if (!widget?.visualizer?.iframe) return

    const iframe = widget.visualizer.iframe
    try {
        const doc = iframe.contentWindow?.document
        if (!doc) return
        const script = doc.getElementById("visualizer")
        if (!script) return
        script.setAttribute("filepath", filepath)
        script.setAttribute("timestamp", Date.now().toString())
    } catch (e) {
        // Cross-origin — try postMessage as fallback.
        iframe.contentWindow?.postMessage(
            { type: "load_glb", filepath },
            "*"
        )
    }
}

app.registerExtension({
    name: "TechNoir.GLBPreview",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "GLBPreview") return

        const onNodeCreated = nodeType.prototype.onNodeCreated
        nodeType.prototype.onNodeCreated = async function () {
            const r = onNodeCreated?.apply(this, arguments)

            // Create the visualizer iframe.
            const viz = createGLBVisualizer(this)

            // Register as a custom widget so LiteGraph positions it.
            const widget = {
                type: WIDGET_TYPE,
                name: "preview3d",
                callback: () => {},
                visualizer: viz,
                draw(ctx, node, widgetWidth, widgetY, widgetHeight) {
                    const margin = 30
                    const topOffset = LiteGraph.NODE_TITLE_HEIGHT + margin
                    const scale = app.canvas?.ds?.scale ?? 1
                    const visible = scale > 0.5 && !node.flags?.collapsed

                    const [x, y] = node.getBounding()
                    const [left, top] = app.canvasPosToClientPos([x, y])
                    const w = node.width * scale
                    const h = (node.height - topOffset) * scale

                    Object.assign(this.visualizer.container.style, {
                        left: `${left}px`,
                        top: `${top + topOffset * scale}px`,
                        width: `${w}px`,
                        height: `${h}px`,
                        display: visible ? "block" : "none",
                    })
                },
            }

            this.addCustomWidget(widget)
            this.setSize([MIN_W, MIN_H])

            // Enforce minimum size so the 3D viewport stays usable.
            this.onResize = function () {
                let [w, h] = this.size
                let changed = false
                if (w < MIN_W) { w = MIN_W; changed = true }
                if (h < MIN_H) { h = MIN_H; changed = true }
                if (changed) this.size = [w, h]
            }

            // Clean up the DOM element when node is removed.
            const origOnRemoved = this.onRemoved
            this.onRemoved = function () {
                viz.container.remove()
                origOnRemoved?.apply(this, arguments)
            }

            // Toggle visibility on collapse/expand.
            this.onDrawBackground = function (ctx) {
                if (!this.flags?.collapsed) {
                    viz.container.style.display = "block"
                } else {
                    viz.container.style.display = "none"
                }
            }

            return r
        }

        // On execution, feed the returned filepath to the visualizer.
        nodeType.prototype.onExecuted = async function (message) {
            if (message?.three_model?.[0]) {
                const m = message.three_model[0]
                const params = new URLSearchParams({
                    filename: m.filename,
                    subfolder: m.subfolder || "",
                    type: m.type || "output",
                })
                updateVisualizerPath(this, `/view?${params}`)
            }
        }
    },
})
