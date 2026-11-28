import os
from pathlib import Path
from nicegui import native, ui

from familytree.compiler.layout import LayoutConfig, PaperFormat
from familytree.compiler.renderer import TreeCompiler
from familytree.storage.database import init_db
from familytree.storage.repository import FamilyRepository
from familytree.web.panels.people import PeoplePanel
from familytree.web.panels.preview import PreviewPanel
from familytree.web.panels.stories import StoriesPanel
from familytree.web.panels.unions import UnionsPanel


class FamilyTreeApp:
    """Thin UI controller wiring NiceGUI forms to FamilyRepository and TreeCompiler."""

    def __init__(self, repo: FamilyRepository) -> None:
        self.repo = repo
        self.layout_config = LayoutConfig()
        self.compiler = TreeCompiler(self.layout_config)

        # Sort and Filter
        self.people_search: str = ""
        self.people_sort: str = (
            "name_asc"  # e.g., "name_asc", "name_desc", "birth_asc", "birth_desc"
        )

        # Pan/zoom state for the SVG viewport
        self.zoom_level: float = 1.0
        self.selected_person_id: str | None = None

    def build_ui(self) -> None:
        ui.colors(primary="#2E5A44", secondary="#8C7A6B", accent="#C29B40")

        # --- Top Header Bar ---
        with ui.header().classes("items-center justify-between px-4 py-2 shadow-sm"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("account_tree", size="sm")
                ui.label("Delta Family Tree Studio").classes(
                    "text-lg font-bold tracking-wide"
                )

            with ui.row().classes("items-center gap-3"):
                ui.select(
                    options=[p.value for p in PaperFormat],
                    value=self.layout_config.paper.value,
                    label="Paper",
                    on_change=self._on_paper_change,
                ).props("dense outlined dark").classes("w-28")

                ui.select(
                    options=["landscape", "portrait"],
                    value=self.layout_config.orientation,
                    label="Orientation",
                    on_change=self._on_orientation_change,
                ).props("dense outlined dark").classes("w-32")

                ui.button(
                    "Export A1/A0 Files",
                    icon="download",
                    on_click=self._export_files,
                ).props("outline color=white")

        # --- Main Split Workspace ---
        with ui.splitter(value=34).classes("w-full h-[calc(100vh-56px)]") as splitter:
            # LEFT PANE: Data Entry & Management Tabs
            with (
                splitter.before,
                ui.column().classes(
                    "w-full h-full p-4 overflow-y-auto bg-stone-50"
                ) as self.left_pane_scroll,
            ):
                with ui.tabs().classes("w-full") as tabs:
                    tab_people = ui.tab("People", icon="person")
                    tab_unions = ui.tab("Unions & Kids", icon="family_restroom")
                    tab_stories = ui.tab("Story Boxes", icon="auto_stories")

                with ui.tab_panels(tabs, value=tab_people).classes(
                    "w-full bg-transparent"
                ):
                    with ui.tab_panel(tab_people):
                        self.people_panel = PeoplePanel(
                            repo=self.repo,
                            on_change=self._refresh_all,
                            on_edit_started=self._scroll_left_pane_top,
                        )
                        self.people_panel.render()
                    with ui.tab_panel(tab_unions):
                        self.unions_panel = UnionsPanel(
                            repo=self.repo,
                            on_change=self._refresh_all,
                        )
                        self.unions_panel.render()
                    with ui.tab_panel(tab_stories):
                        self.stories_panel = StoriesPanel(
                            repo=self.repo,
                            on_change=self._refresh_all,
                        )
                        self.stories_panel.render()

            # RIGHT PANE: Live Graphviz SVG Preview
            with splitter.after:
                self.preview_panel = PreviewPanel(
                    repo=self.repo,
                    compiler=self.compiler,
                    on_recompile=self._refresh_all,
                )
                self.preview_panel.render()

    # --- UI Action Helpers ---
    def _scroll_left_pane_top(self) -> None:
        print("Running _scroll_left_pane_top", flush=True)
        ui.run_javascript(f"""
            const el = getHtmlElement({self.left_pane_scroll.id});
            console.log("Left pane el:", el, {{
                scrollTop: el?.scrollTop,
                clientHeight: el?.clientHeight,
                scrollHeight: el?.scrollHeight,
            }});
            if (el) {{
                el.scrollTop = 0;
            }}
        """)

    def _on_paper_change(self, e) -> None:
        self.layout_config.paper = PaperFormat(e.value)
        self.preview_panel.refresh()

    def _on_orientation_change(self, e) -> None:
        self.layout_config.orientation = e.value
        self.preview_panel.refresh()

    def _export_files(self) -> None:
        snapshot = self.repo.get_snapshot()
        paths = self.compiler.export_files(snapshot, Path("output"))
        ui.notify(
            f"Exported SVG & PDF to {paths['svg'].parent.resolve()}",
            type="positive",
        )

    def _refresh_all(self) -> None:
        self.people_panel.refresh()
        self.unions_panel.refresh()
        self.stories_panel.refresh()
        self.preview_panel.refresh()

    def _adjust_zoom(self, delta: float) -> None:
        self.zoom_level = max(0.15, min(3.5, round(self.zoom_level + delta, 2)))
        self.zoom_label.set_text(f"{int(self.zoom_level * 100)}%")
        ui.run_javascript(f"""
            if (window.__treeView) {{
                window.__treeView.scale = Math.min(3.5, Math.max(0.15, +(window.__treeView.scale + {delta}).toFixed(2)));
                window.__applyTreeTransform();
            }}
        """)

    def _reset_zoom(self) -> None:
        self.zoom_level = 1.0
        self.zoom_label.set_text("100%")
        ui.run_javascript("""
            if (window.__treeView) {
                window.__treeView = { x: 24, y: 24, scale: 1 };
                window.__applyTreeTransform();
            }
        """)


def start_server(
    port: int = 8080,
    reload: bool = False,
) -> None:
    """Initializes SQLite and launches the NiceGUI application."""
    init_db()
    repo = FamilyRepository()

    is_desktop = os.getenv("APP_MODE", "desktop").strip().lower() == "desktop"

    @ui.page("/")
    def index_page() -> None:
        tree_app = FamilyTreeApp(repo)
        tree_app.build_ui()

    run_kwargs = {
        "title": "Delta Family Tree Studio",
        "port": native.find_open_port() if is_desktop else port,
        "reload": reload,
        "native": is_desktop,
    }

    if is_desktop:
        run_kwargs.update({
            "window_size": (1024,768),
            "frameless": False
        })
    else:
        run_kwargs["show"] = True

    ui.run(**run_kwargs)


if __name__ in {"__main__", "__mp_main__"}:
    start_server(reload=False)
