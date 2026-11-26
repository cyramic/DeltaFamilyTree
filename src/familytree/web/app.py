from pathlib import Path
from typing import Optional

from nicegui import app, ui
from pydantic import ValidationError

from familytree.compiler.layout import LayoutConfig, PaperFormat
from familytree.compiler.renderer import TreeCompiler
from familytree.domain.models import Person, StoryNote, Union
from familytree.storage.database import init_db
from familytree.storage.repository import FamilyRepository


class FamilyTreeApp:
    """Thin UI controller wiring NiceGUI forms to FamilyRepository and TreeCompiler."""

    def __init__(self, repo: FamilyRepository) -> None:
        self.repo = repo
        self.layout_config = LayoutConfig()
        self.compiler = TreeCompiler(self.layout_config)

        # Sort and Filter
        self.people_search: str = ""
        self.people_sort: str = "name_asc" # e.g., "name_asc", "name_desc", "birth_asc", "birth_desc"

        # Pan/zoom state for the SVG viewport
        self.zoom_level: float = 1.0
        self.selected_person_id: Optional[str] = None

    def build_ui(self) -> None:
        ui.colors(primary="#2E5A44", secondary="#8C7A6B", accent="#C29B40")

        # --- Top Header Bar ---
        with ui.header().classes("items-center justify-between px-4 py-2 shadow-sm"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("account_tree", size="sm")
                ui.label("Delta Family Tree Studio").classes("text-lg font-bold tracking-wide")

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
            with splitter.before:
                with ui.column().classes("w-full h-full p-4 overflow-y-auto bg-stone-50") as self.left_pane_scroll:
                    with ui.tabs().classes("w-full") as tabs:
                        tab_people = ui.tab("People", icon="person")
                        tab_unions = ui.tab("Unions & Kids", icon="family_restroom")
                        tab_stories = ui.tab("Story Boxes", icon="auto_stories")

                    with ui.tab_panels(tabs, value=tab_people).classes("w-full bg-transparent"):
                        with ui.tab_panel(tab_people):
                            self._render_people_panel()
                        with ui.tab_panel(tab_unions):
                            self._render_unions_panel()
                        with ui.tab_panel(tab_stories):
                            self._render_stories_panel()

            # RIGHT PANE: Live Graphviz SVG Preview
            with splitter.after:
                with ui.column().classes("w-full h-full relative bg-[#FAF8F5] overflow-hidden"):
                    # Floating Zoom & Layout Controls
                    with ui.row().classes(
                            "absolute top-3 right-3 z-10 bg-white/90 backdrop-blur "
                            "px-3 py-1.5 rounded-lg shadow border border-stone-200 items-center gap-2"
                    ):
                        ui.button(icon="zoom_out", on_click=lambda: self._adjust_zoom(-0.15)).props(
                            "flat dense"
                        )
                        self.zoom_label = ui.label("100%").classes("text-xs font-mono w-12 text-center")
                        ui.button(icon="zoom_in", on_click=lambda: self._adjust_zoom(0.15)).props(
                            "flat dense"
                        )
                        ui.button(icon="restart_alt", on_click=self._reset_zoom).props(
                            "flat dense"
                        ).tooltip("Reset view")
                        ui.separator().props("vertical")
                        ui.button(icon="refresh", on_click=self._refresh_all).props(
                            "flat dense color=primary"
                        ).tooltip("Recompile graph")

                    # Interactive Pan & Zoom Viewport
                    with ui.element("div").props('id="tree-viewport"').classes(
                            "w-full h-full overflow-hidden cursor-grab active:cursor-grabbing select-none relative"
                    ):
                        self.svg_wrapper = (
                            ui.element("div")
                            .props('id="tree-canvas"')
                            .style("transform-origin: 0 0; position: absolute; top: 24px; left: 24px;")
                        )
                        with self.svg_wrapper:
                            self._render_svg_preview()

                    self._init_pan_zoom_js()

    # --- Refreshable UI Fragments ---
    @ui.refreshable
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
        except Exception as exc:
            ui.notify(f"Graphviz compile error: {exc}", type="negative")

    @ui.refreshable
    def _render_people_panel(self) -> None:
        people = self.repo.list_people()
        editing = self.repo.get_person(self.selected_person_id) if self.selected_person_id else None

        with ui.card().classes("w-full mb-2 scroll-mt-4").props('id="person-form-card"') as self.person_form_card:
            ui.label("Edit Person" if editing else "Add Person").classes("font-semibold text-base")

            name_in = ui.input("Full Name *", value=editing.full_name if editing else "").classes("w-full")
            with ui.row().classes("w-full gap-2"):
                # Birth Date inputs
                ui.label("Birth Date").classes("text-xs font-semibold text-stone-600 mt-1")
                with ui.row().classes("w-full gap-2"):
                    b_year = ui.input("Year (e.g. 1824 or c. 1812)",
                                      value=(editing.birth_year or "") if editing else "").classes("flex-2")
                    b_month = ui.number("Month (1-12)", value=(editing.birth_month or None) if editing else None, min=1,
                                        max=12, precision=0).classes("flex-1")
                    b_day = ui.number("Day (1-31)", value=(editing.birth_day or None) if editing else None, min=1,
                                      max=31, precision=0).classes("flex-1")

                # Death Date inputs
                ui.label("Death Date").classes("text-xs font-semibold text-stone-600 mt-1")
                with ui.row().classes("w-full gap-2"):
                    d_year = ui.input("Year", value=(editing.death_year or "") if editing else "").classes("flex-2")
                    d_month = ui.number("Month", value=(editing.death_month or None) if editing else None, min=1,
                                        max=12, precision=0).classes("flex-1")
                    d_day = ui.number("Day", value=(editing.death_day or None) if editing else None, min=1, max=31,
                                      precision=0).classes("flex-1")

            place_in = ui.input(
                "Birth / Home Place",
                value=(editing.birth_place or "") if editing else "",
            ).classes("w-full")

            place_death = ui.input(
                "Death / Burial Place",
                value=(editing.death_place or "") if editing else "",
            ).classes("w-full")

            bio_in = ui.textarea(
                "Short Card Bio (shown inside box)",
                value=(editing.bio_short or "") if editing else "",
            ).props("rows=2").classes("w-full")

            focus_in = ui.checkbox(
                "Focus Line (extends past early 1800s)",
                value=editing.is_focus_line if editing else False,
            )

            def save_person() -> None:
                try:
                    common_fields = dict(
                        full_name=name_in.value.strip(),
                        birth_year=b_year.value.strip() or None,
                        birth_month=int(b_month.value) if b_month.value else None,
                        birth_day=int(b_day.value) if b_day.value else None,
                        death_year=d_year.value.strip() or None,
                        death_month=int(d_month.value) if d_month.value else None,
                        death_day=int(d_day.value) if d_day.value else None,
                        birth_place=place_in.value.strip() or None,
                        death_place=place_death.value.strip() or None,
                        bio_short=bio_in.value.strip() or None,
                        is_focus_line=focus_in.value,
                    )
                    # Strip None id so default_factory generates a new n_<hex> id
                    if editing:
                        person = Person(
                            id=editing.id,
                            share_code=editing.share_code,
                            **common_fields
                        )
                    if not editing:
                        person = Person(**common_fields)
                    self.repo.save_person(person)
                    self.selected_person_id = None
                    ui.notify(f"Saved {person.full_name}", type="positive")
                    self._refresh_all()
                except ValidationError as err:
                    ui.notify(err.errors()[0]["msg"], type="negative")

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                if editing:
                    ui.button("Cancel", on_click=self._cancel_edit).props("flat")
                ui.button("Save Person", icon="save", on_click=save_person)

        # Existing People List
        with ui.row().classes("w-full items-center gap-2 mb-2"):
            search_in = ui.input(
                placeholder="Filter by name, dates, place...",
                value=self.people_search,
                on_change=lambda e: self._update_people_filter(e.value),
            ).props("dense clearable outlined").classes("flex-1")

            ui.select(
                options={
                    "name_asc": "Name (A–Z)",
                    "name_desc": "Name (Z–A)",
                    "birth_asc": "Birth Year (Oldest)",
                    "birth_desc": "Birth Year (Newest)",
                },
                value=self.people_sort,
                on_change=lambda e: self._update_people_sort(e.value),
            ).props("dense outlined").classes("w-44")

        self._render_people_directory(people)

    @ui.refreshable
    def _render_unions_panel(self) -> None:
        people = self.repo.list_people()
        person_options = {p.id: f"{p.full_name} ({p.lifespan_label or '?'})" for p in people}
        unions = self.repo.list_unions()

        def union_partners(u: Union) -> tuple[str, str]:
            n1 = person_options.get(u.partner1_id, u.partner1_id)
            n2 = person_options.get(u.partner2_id, "Single Parent") if u.partner2_id else "Single Parent"
            return n1, n2

        def format_union_label(u: Union) -> str:
            n1, n2 = union_partners(u)
            details = [f"{n1} + {n2}"]
            if u.formatted_marriage_date:
                details.append(u.formatted_marriage_date)
            if u.location:
                flag = f"{u.marriage_flag_emoji} " if u.marriage_flag_emoji else ""
                details.append(f"{flag}{u.location}")
            return " · ".join(details)

        def matches_filter(u: Union, query: str, union_type: str) -> bool:
            if union_type == "partnered" and not u.partner2_id:
                return False
            if union_type == "single" and u.partner2_id:
                return False
            q = query.strip().lower()
            if not q:
                return True
            n1, n2 = union_partners(u)
            haystack = " ".join(
                filter(
                    None,
                    [
                        n1,
                        n2,
                        u.marriage_year,
                        u.formatted_marriage_date,
                        u.location,
                    ],
                )
            ).lower()
            return q in haystack

        def open_edit_dialog(union: Union) -> None:
            with ui.dialog() as dialog, ui.card().classes("w-full max-w-md"):
                ui.label("Edit Partnership / Union").classes("font-semibold text-lg")

                p1_edit = ui.select(
                    person_options, label="Partner 1 *", value=union.partner1_id
                ).classes("w-full")
                p2_edit = ui.select(
                    person_options,
                    label="Partner 2 (optional for single-parent lines)",
                    value=union.partner2_id,
                    clearable=True,
                ).classes("w-full")

                ui.label("Marriage Date").classes("text-xs font-semibold text-stone-600 mt-1")
                with ui.row().classes("w-full gap-2"):
                    year_edit = ui.input("Year", value=union.marriage_year or "").classes("flex-2")
                    month_edit = ui.number(
                        "Month", value=union.marriage_month, min=1, max=12, precision=0
                    ).classes("flex-1")
                    day_edit = ui.number(
                        "Day", value=union.marriage_day, min=1, max=31, precision=0
                    ).classes("flex-1")

                loc_edit = ui.input("Location", value=union.location or "").classes("w-full")

                def save_changes() -> None:
                    if not p1_edit.value:
                        ui.notify("Select at least Partner 1", type="warning")
                        return
                    try:
                        updated = Union(
                            id=union.id,
                            partner1_id=p1_edit.value,
                            partner2_id=p2_edit.value or None,
                            marriage_year=year_edit.value.strip() or None,
                            marriage_month=int(month_edit.value) if month_edit.value else None,
                            marriage_day=int(day_edit.value) if day_edit.value else None,
                            location=loc_edit.value.strip() or None,
                        )
                        self.repo.save_union(updated)
                        dialog.close()
                        ui.notify("Union updated", type="positive")
                        self._refresh_all()
                    except ValidationError as err:
                        ui.notify(err.errors()[0]["msg"], type="negative")

                with ui.row().classes("w-full justify-end gap-2 mt-3"):
                    ui.button("Cancel", on_click=dialog.close).props("flat")
                    ui.button("Save Changes", icon="save", on_click=save_changes)

            dialog.open()

        # Create Union Card
        with ui.card().classes("w-full mb-4"):
            ui.label("Create Partnership / Union").classes("font-semibold text-base")
            p1_sel = ui.select(person_options, label="Partner 1 *").classes("w-full")
            p2_sel = ui.select(
                person_options, label="Partner 2 (optional for single-parent lines)", clearable=True
            ).classes("w-full")
            ui.label("Marriage Date").classes("text-xs font-semibold text-stone-600 mt-1")
            with ui.row().classes("w-full gap-2"):
                m_year = ui.input("Year").classes("flex-2")
                m_month = ui.number("Month", min=1, max=12, precision=0).classes("flex-1")
                m_day = ui.number("Day", min=1, max=31, precision=0).classes("flex-1")

            def create_union() -> None:
                if not p1_sel.value:
                    ui.notify("Select at least Partner 1", type="warning")
                    return
                try:
                    u = Union(
                        partner1_id=p1_sel.value,
                        partner2_id=p2_sel.value or None,
                        marriage_year=m_year.value.strip() or None,
                        marriage_month=int(m_month.value) if m_month.value else None,
                        marriage_day=int(m_day.value) if m_day.value else None,
                    )
                    self.repo.save_union(u)
                    ui.notify("Union created", type="positive")
                    self._refresh_all()
                except ValidationError as err:
                    ui.notify(err.errors()[0]["msg"], type="negative")

            ui.button("Add Union", icon="link", on_click=create_union).classes("mt-2")

        # Existing Unions Card (Searchable, Filterable, Scrollable)
        with ui.card().classes("w-full mb-4"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Existing Unions").classes("font-semibold text-base")
                count_label = ui.label(f"{len(unions)} total").classes("text-xs text-stone-500")

            with ui.row().classes("w-full gap-2 items-center"):
                search_in = ui.input(
                    placeholder="Search partner, year, or location..."
                ).props("dense clearable outlined").classes("flex-2")
                type_sel = ui.select(
                    {
                        "all": "All Unions",
                        "partnered": "Partnered",
                        "single": "Single Parent",
                    },
                    value="all",
                ).props("dense outlined").classes("flex-1")

            @ui.refreshable
            def render_union_rows() -> None:
                query_val = search_in.value or ""
                type_val = type_sel.value or "all"
                filtered = [u for u in unions if matches_filter(u, query_val, type_val)]
                count_label.set_text(f"{len(filtered)} of {len(unions)}")

                with ui.scroll_area().classes("w-full h-56 border border-stone-200 rounded px-1.5 py-1"):
                    if not filtered:
                        ui.label("No matching unions.").classes("text-xs text-stone-500 py-1 px-1")
                    else:
                        for u in filtered:
                            with ui.row().classes(
                                    "w-full flex-nowrap items-start justify-between gap-1 py-0.5 border-b border-stone-100 last:border-b-0"
                            ):
                                ui.label(format_union_label(u)).classes(
                                    "flex-1 min-w-0 text-xs leading-tight break-words"
                                )
                                ui.button(
                                    icon="edit",
                                    on_click=lambda _, target=u: open_edit_dialog(target),
                                ).props("flat dense round size=xs").classes("shrink-0").style(
                                    "min-height: 22px; min-width: 22px; padding: 0;"
                                )

            search_in.on_value_change(lambda _: render_union_rows.refresh())
            type_sel.on_value_change(lambda _: render_union_rows.refresh())
            render_union_rows()

        # Link Child to Union Card
        union_options = {u.id: format_union_label(u) for u in unions}

        with ui.card().classes("w-full"):
            ui.label("Link Child to Parents").classes("font-semibold text-base")
            u_sel = ui.select(union_options, label="Parental Union *").classes("w-full")
            c_sel = ui.select(person_options, label="Child *").classes("w-full")
            order_in = ui.number("Birth Order (1, 2, 3...)", min=1, precision=0).classes("w-full")

            def link_child() -> None:
                if not u_sel.value or not c_sel.value:
                    ui.notify("Select both a union and a child", type="warning")
                    return
                self.repo.add_child_to_union(
                    union_id=u_sel.value,
                    child_id=c_sel.value,
                    birth_order=int(order_in.value) if order_in.value else None,
                )
                ui.notify("Child linked to union", type="positive")
                self._refresh_all()

            ui.button("Link Child", icon="child_care", on_click=link_child).classes("mt-2")

    @ui.refreshable
    def _render_stories_panel(self) -> None:
        snapshot = self.repo.get_snapshot()
        person_options = {p.id: f"Person: {p.full_name}" for p in snapshot.people}
        people_map = {p.id: p.full_name for p in snapshot.people}
        union_options = {
            u.id: f"Couple: {people_map.get(u.partner1_id, '?')} & {people_map.get(u.partner2_id or '', 'Single')}"
            for u in snapshot.unions
        }
        all_targets = {**person_options, **union_options}

        def target_label(note: StoryNote) -> str:
            if note.person_id:
                return person_options.get(note.person_id, f"Person: {note.person_id}")
            if note.union_id:
                return union_options.get(note.union_id, f"Couple: {note.union_id}")
            return "Unattached"

        def current_target_id(note: StoryNote) -> str | None:
            return note.person_id or note.union_id

        def matches_note(note: StoryNote, query: str, attach_filter: str) -> bool:
            if attach_filter == "person" and not note.person_id:
                return False
            if attach_filter == "union" and not note.union_id:
                return False
            q = query.strip().lower()
            if not q:
                return True
            haystack = " ".join(
                filter(
                    None,
                    [
                        note.title,
                        note.body,
                        target_label(note),
                    ],
                )
            ).lower()
            return q in haystack

        def open_edit_dialog(note: StoryNote) -> None:
            with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
                ui.label("Edit Story Box").classes("font-semibold text-lg")

                target_edit = ui.select(
                    all_targets,
                    label="Attach To (Person or Couple) *",
                    value=current_target_id(note),
                ).classes("w-full")
                title_edit = ui.input("Story Box Title *", value=note.title).classes("w-full")
                body_edit = (
                    ui.textarea("Story Narrative *", value=note.body)
                    .props("rows=5")
                    .classes("w-full")
                )

                def save_changes() -> None:
                    target = target_edit.value
                    if not target:
                        ui.notify("Select a person or couple to attach this story to", type="warning")
                        return
                    is_person = target in person_options
                    try:
                        updated = StoryNote(
                            id=note.id,
                            title=title_edit.value.strip(),
                            body=body_edit.value.strip(),
                            person_id=target if is_person else None,
                            union_id=None if is_person else target,
                        )
                        self.repo.save_story_note(updated)
                        dialog.close()
                        ui.notify("Story box updated", type="positive")
                        self._refresh_all()
                    except ValidationError as err:
                        ui.notify(err.errors()[0]["msg"], type="negative")

                with ui.row().classes("w-full justify-end gap-2 mt-3"):
                    ui.button("Cancel", on_click=dialog.close).props("flat")
                    ui.button("Save Changes", icon="save", on_click=save_changes)

            dialog.open()

        # Add Story Card
        with ui.card().classes("w-full mb-3 p-3"):
            ui.label("Add Linked Story Box").classes("font-semibold text-base")
            target_sel = ui.select(all_targets, label="Attach To (Person or Couple) *").classes("w-full")
            title_in = ui.input("Story Box Title *").classes("w-full")
            body_in = ui.textarea("Story Narrative *").props("rows=4").classes("w-full")

            def save_story() -> None:
                target = target_sel.value
                if not target:
                    ui.notify("Select a person or couple to attach this story to", type="warning")
                    return
                is_person = target in person_options
                try:
                    note = StoryNote(
                        title=title_in.value.strip(),
                        body=body_in.value.strip(),
                        person_id=target if is_person else None,
                        union_id=None if is_person else target,
                    )
                    self.repo.save_story_note(note)
                    title_in.value = ""
                    body_in.value = ""
                    ui.notify("Story box added", type="positive")
                    self._refresh_all()
                except ValidationError as err:
                    ui.notify(err.errors()[0]["msg"], type="negative")

            ui.button("Attach Story Box", icon="note_add", on_click=save_story).classes("mt-2")

        # Search, Filter & Compact Notes List
        with ui.card().classes("w-full p-3"):
            with ui.row().classes("w-full items-center justify-between mb-1"):
                ui.label("Linked Story Boxes").classes("font-semibold text-base")
                count_label = ui.label(f"{len(snapshot.story_notes)} total").classes("text-xs text-stone-500")

            with ui.row().classes("w-full gap-2 items-center mb-2"):
                search_in = ui.input(
                    placeholder="Search title, narrative, or person/couple..."
                ).props("dense clearable outlined").classes("flex-2")
                filter_sel = ui.select(
                    {
                        "all": "All Notes",
                        "person": "People Only",
                        "union": "Couples Only",
                    },
                    value="all",
                ).props("dense outlined").classes("flex-1")

            @ui.refreshable
            def render_note_rows() -> None:
                query_val = search_in.value or ""
                filter_val = filter_sel.value or "all"
                filtered = [n for n in snapshot.story_notes if matches_note(n, query_val, filter_val)]
                count_label.set_text(f"{len(filtered)} of {len(snapshot.story_notes)}")

                if not filtered:
                    ui.label("No matching story boxes.").classes("text-xs text-stone-500 py-1")
                    return

                with ui.column().classes("w-full gap-1"):
                    for n in filtered:
                        with ui.row().classes(
                                "w-full flex-nowrap items-center justify-between gap-2 py-1 px-2 border border-stone-200 rounded"
                        ):
                            with ui.column().classes("flex-1 min-w-0 gap-0"):
                                ui.label(n.title).classes("text-xs font-semibold leading-tight truncate")
                                ui.label(target_label(n)).classes("text-[11px] text-stone-500 leading-tight truncate")
                            with ui.row().classes("shrink-0 items-center gap-0.5"):
                                ui.button(
                                    icon="edit",
                                    on_click=lambda _, target_note=n: open_edit_dialog(target_note),
                                ).props("flat dense round size=xs").style(
                                    "min-height: 22px; min-width: 22px; padding: 0;"
                                )
                                ui.button(
                                    icon="delete",
                                    on_click=lambda _, nid=n.id: self._delete_note(nid),
                                ).props("flat dense round size=xs color=negative").style(
                                    "min-height: 22px; min-width: 22px; padding: 0;"
                                )

            search_in.on_value_change(lambda _: render_note_rows.refresh())
            filter_sel.on_value_change(lambda _: render_note_rows.refresh())
            render_note_rows()

    # --- UI Sort and Filter Helpers ---
    def _filtered_and_sorted_people(self, people: list) -> list:
        query = (self.people_search or "").strip().lower()
        if query:
            people = [
                p for p in people
                if query in (p.full_name or "").lower()
                   or query in (p.lifespan_label or "").lower()
                   or query in (getattr(p, "birth_place", "") or "").lower()
            ]

        def birth_key(p):
            # Extract leading numeric year if available (e.g. "c. 1812" -> 1812), else push to end
            raw = (getattr(p, "birth_year", "") or "").strip()
            digits = "".join(ch for ch in raw if ch.isdigit())
            return (0, int(digits[:4])) if len(digits) >= 4 else (1, 9999)

        if self.people_sort == "name_asc":
            return sorted(people, key=lambda p: (p.full_name or "").lower())
        if self.people_sort == "name_desc":
            return sorted(people, key=lambda p: (p.full_name or "").lower(), reverse=True)
        if self.people_sort == "birth_asc":
            return sorted(people, key=lambda p: (birth_key(p), (p.full_name or "").lower()))
        if self.people_sort == "birth_desc":
            return sorted(people, key=lambda p: (birth_key(p)[0], -birth_key(p)[1], (p.full_name or "").lower()))
        return people

    def _update_people_filter(self, value: str) -> None:
        self.people_search = value or ""
        self._render_people_directory.refresh()

    def _update_people_sort(self, value: str) -> None:
        self.people_sort = value or "name_asc"
        self._render_people_directory.refresh()

    @ui.refreshable
    def _render_people_directory(self, people: list) -> None:
        visible = self._filtered_and_sorted_people(people)
        ui.label(f"Directory ({len(visible)} / {len(people)})").classes(
            "text-xs uppercase font-bold text-stone-500 mb-1"
        )
        with ui.column().classes("w-full gap-0.5"):
            for p in visible:
                with ui.card().classes("w-full py-1 px-2.5 !my-0.5 flex-row items-center justify-between"):
                    with ui.column().classes("gap-0 leading-tight"):
                        ui.label(p.full_name).classes("font-medium text-sm")
                        if p.lifespan_label:
                            ui.label(p.lifespan_label).classes("text-xs text-stone-500")
                    with ui.row().classes("gap-0.5"):
                        ui.button(
                            icon="edit",
                            on_click=lambda pid=p.id: self._select_person(pid),
                        ).props("flat dense size=sm")
                        ui.button(
                            icon="delete",
                            on_click=lambda pid=p.id: self._delete_person(pid),
                        ).props("flat dense size=sm color=negative")

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

    def _select_person(self, person_id: str) -> None:
        self.selected_person_id = person_id
        self._render_people_panel.refresh()
        ui.run_javascript(f"""
            const el = getHtmlElement({self.left_pane_scroll.id});
            if (el) {{
                el.scrollTop = 0;
            }}
        """)

    def _cancel_edit(self) -> None:
        self.selected_person_id = None
        self._render_people_panel.refresh()

    def _delete_person(self, person_id: str) -> None:
        self.repo.delete_person(person_id)
        if self.selected_person_id == person_id:
            self.selected_person_id = None
        ui.notify("Person removed", type="info")
        self._refresh_all()

    def _delete_note(self, note_id: str) -> None:
        self.repo.delete_story_note(note_id)
        self._refresh_all()

    def _on_paper_change(self, e) -> None:
        self.layout_config.paper = PaperFormat(e.value)
        self._render_svg_preview.refresh()

    def _on_orientation_change(self, e) -> None:
        self.layout_config.orientation = e.value
        self._render_svg_preview.refresh()

    def _adjust_zoom(self, delta: float) -> None:
        self.zoom_level = max(0.2, min(3.0, round(self.zoom_level + delta, 2)))
        self.zoom_label.set_text(f"{int(self.zoom_level * 100)}%")
        self.svg_wrapper.style(f"transform: scale({self.zoom_level});")

    def _reset_zoom(self) -> None:
        self.zoom_level = 1.0
        self.zoom_label.set_text("100%")
        self.svg_wrapper.style("transform: scale(1.0);")

    def _export_files(self) -> None:
        snapshot = self.repo.get_snapshot()
        paths = self.compiler.export_files(snapshot, Path("output"))
        ui.notify(
            f"Exported SVG & PDF to {paths['svg'].parent.resolve()}",
            type="positive",
        )

    def _refresh_all(self) -> None:
        self._render_people_panel.refresh()
        self._render_unions_panel.refresh()
        self._render_stories_panel.refresh()
        self._render_svg_preview.refresh()

    def _init_pan_zoom_js(self) -> None:
        """Attaches smooth client-side click-and-drag panning and wheel zooming."""
        ui.run_javascript("""
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
        """)

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


def start_server(port: int = 8080, reload: bool = False) -> None:
    """Initializes SQLite and launches the NiceGUI application."""
    init_db()
    repo = FamilyRepository()
    tree_app = FamilyTreeApp(repo)

    @ui.page("/")
    def index_page() -> None:
        tree_app.build_ui()

    ui.run(
        title="Delta Family Tree Studio",
        port=port,
        reload=reload,
        show=True,
    )


if __name__ in {"__main__", "__mp_main__"}:
    start_server(reload=True)