import subprocess
from collections.abc import Callable

from nicegui import ui

from familytree.compiler.renderer import TreeCompiler
from familytree.storage.repository import FamilyRepository


class GraphvizCompileError(RuntimeError):
    """Raised when DOT generation or Graphviz rendering fails."""


class PreviewPanel:
    """Self-contained UI panel for live Graphviz SVG preview, zoom, and pan."""

    def __init__(
        self,
        repo: FamilyRepository,
        compiler: TreeCompiler,
        on_recompile: Callable[[], None],
    ) -> None:
        self.repo = repo
        self.compiler = compiler
        self.on_recompile = on_recompile

        self.zoom_level: float = 1.0
        self.zoom_label: ui.label | None = None
        self.svg_wrapper: ui.element | None = None

    def render(self) -> None:
        with ui.column().classes("w-full h-full relative bg-[#FAF8F5] overflow-hidden"):
            self._render_floating_controls()
            self._render_viewport()
            self._init_pan_zoom_js()

    def refresh(self) -> None:
        self._render_svg_preview.refresh()

    def _render_floating_controls(self) -> None:
        with ui.row().classes(
            "absolute top-3 right-3 z-10 bg-white/90 backdrop-blur "
            "px-3 py-1.5 rounded-lg shadow border border-stone-200 items-center gap-2"
        ):
            ui.button(icon="zoom_out", on_click=lambda: self._adjust_zoom(-0.15)).props(
                "flat dense"
            )
            self.zoom_label = ui.label(f"{int(self.zoom_level * 100)}%").classes(
                "text-xs font-mono w-12 text-center"
            )
            ui.button(icon="zoom_in", on_click=lambda: self._adjust_zoom(0.15)).props(
                "flat dense"
            )
            ui.button(icon="restart_alt", on_click=self._reset_zoom).props(
                "flat dense"
            ).tooltip("Reset view")
            ui.separator().props("vertical")
            ui.button(icon="refresh", on_click=self.on_recompile).props(
                "flat dense color=primary"
            ).tooltip("Recompile graph")

    def _render_viewport(self) -> None:
        with (
            ui.element("div")
            .props('id="tree-viewport"')
            .classes(
                "w-full h-full overflow-hidden cursor-grab active:cursor-grabbing select-none relative"
            )
        ):
            self.svg_wrapper = (
                ui.element("div")
                .props('id="tree-canvas"')
                .style(
                    "transform-origin: 0 0; position: absolute; top: 24px; left: 24px;"
                )
            )
            with self.svg_wrapper:
                self._render_svg_preview()

    @ui.refreshable_method
    def _render_svg_preview(self) -> None:
        snapshot = self.repo.get_snapshot()
        if not snapshot.people:
            with ui.column().classes("items-center justify-center p-12 text-stone-500"):
                ui.icon("nature_people", size="xl")
                ui.label("No family members yet. Add your first ancestor on the left!")
            return

        try:
            svg_markup = self.compiler.render_svg(snapshot)
            ui.html(svg_markup, sanitize=False)
        except GraphvizCompileError:
            raise
        except (OSError, subprocess.CalledProcessError, ValueError) as exc:
            raise GraphvizCompileError(str(exc)) from exc

    def _adjust_zoom(self, delta: float) -> None:
        self.zoom_level = max(0.15, min(3.5, round(self.zoom_level + delta, 2)))
        if self.zoom_label is not None:
            self.zoom_label.set_text(f"{int(self.zoom_level * 100)}%")
        ui.run_javascript(
            f"""
            if (window.__treeView) {{
                window.__treeView.scale = {self.zoom_level};
                window.__applyTreeTransform();
            }}
            """
        )

    def _reset_zoom(self) -> None:
        self.zoom_level = 1.0
        if self.zoom_label is not None:
            self.zoom_label.set_text("100%")
        ui.run_javascript(
            """
            if (window.__treeView) {
                window.__treeView = { x: 24, y: 24, scale: 1 };
                window.__applyTreeTransform();
            }
            """
        )

    def _init_pan_zoom_js(self) -> None:
        """Attaches smooth client-side click-and-drag panning and wheel zooming."""
        ui.run_javascript(
            """
            (() => {
                const viewport = document.getElementById('tree-viewport');
                const canvas = document.getElementById('tree-canvas');
                if (!viewport || !canvas || viewport.dataset.panZoomInit) return;
                viewport.dataset.panZoomInit = 'true';

                window.__treeView = { x: 24, y: 24, scale: 1 };
                let isDragging = false;
                let startX = 0;
                let startY = 0;

                window.__applyTreeTransform = () => {
                    const { x, y, scale } = window.__treeView;
                    canvas.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
                    const label = document.getElementById('zoom-readout');
                    if (label) label.textContent = `${Math.round(scale * 100)}%`;
                };

                viewport.addEventListener('pointerdown', (e) => {
                    if (e.button !== 0) return;
                    isDragging = true;
                    startX = e.clientX - window.__treeView.x;
                    startY = e.clientY - window.__treeView.y;
                    viewport.setPointerCapture(e.pointerId);
                });

                viewport.addEventListener('pointermove', (e) => {
                    if (!isDragging) return;
                    window.__treeView.x = e.clientX - startX;
                    window.__treeView.y = e.clientY - startY;
                    window.__applyTreeTransform();
                });

                const stopDrag = (e) => {
                    if (!isDragging) return;
                    isDragging = false;
                    if (viewport.hasPointerCapture(e.pointerId)) {
                        viewport.releasePointerCapture(e.pointerId);
                    }
                };
                viewport.addEventListener('pointerup', stopDrag);
                viewport.addEventListener('pointercancel', stopDrag);

                // Wheel zoom centered on cursor
                viewport.addEventListener('wheel', (e) => {
                    e.preventDefault();
                    const rect = viewport.getBoundingClientRect();
                    const mx = e.clientX - rect.left;
                    const my = e.clientY - rect.top;

                    const prevScale = window.__treeView.scale;
                    const factor = e.deltaY < 0 ? 1.12 : 0.89;
                    const nextScale = Math.min(3.5, Math.max(0.15, prevScale * factor));

                    window.__treeView.x = mx - (mx - window.__treeView.x) * (nextScale / prevScale);
                    window.__treeView.y = my - (my - window.__treeView.y) * (nextScale / prevScale);
                    window.__treeView.scale = nextScale;
                    window.__applyTreeTransform();
                }, { passive: false });
            })();
            """
        )
