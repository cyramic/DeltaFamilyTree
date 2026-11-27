from collections.abc import Callable

from nicegui import ui
from pydantic import ValidationError

from familytree.domain.models import Person
from familytree.storage.repository import FamilyRepository
from familytree.web.helpers.filters import filtered_and_sorted_people


class PeoplePanel:
    """Self-contained UI panel for creating, editing, filtering, and listing people."""

    def __init__(
        self,
        repo: FamilyRepository,
        on_change: Callable[[], None],
        on_edit_started: Callable[[], None] | None = None,
    ) -> None:
        self.repo = repo
        self.on_change = on_change
        self.on_edit_started = on_edit_started

        self.selected_person_id: str | None = None
        self.search_query: str = ""
        self.sort_mode: str = "name_asc"

    @ui.refreshable_method
    def render(self) -> None:
        people = self.repo.list_people()
        editing = (
            self.repo.get_person(self.selected_person_id)
            if self.selected_person_id
            else None
        )

        self._render_form_card(editing)
        self._render_controls()
        self._render_directory(people)

    def refresh(self) -> None:
        self.render.refresh()

    def _render_form_card(self, editing: Person | None) -> None:
        with (
            ui.card()
            .classes("w-full mb-2 p-3 gap-1 scroll-mt-4")
            .props('id="person-form-card"')
        ):
            ui.label("Edit Person" if editing else "Add Person").classes(
                "font-semibold text-sm leading-tight"
            )
            name_in = (
                ui.input("Full Name *", value=editing.full_name if editing else "")
                .props("dense outlined")
                .classes("w-full")
            )

            with ui.column().classes("w-full gap-1 mt-0.5"):
                # Birth Date inputs
                ui.label("Birth Date").classes(
                    "text-[11px] font-semibold text-stone-600 leading-none"
                )
                with ui.row().classes("w-full flex-nowrap gap-1.5 items-center"):
                    b_year = (
                        ui.input(
                            "Year (e.g. 1824 or c. 1812)",
                            value=(editing.birth_year or "") if editing else "",
                        )
                        .props("dense outlined")
                        .classes("flex-2 min-w-0")
                    )
                    b_month = (
                        ui.number(
                            "Month",
                            value=(editing.birth_month or None) if editing else None,
                            min=1,
                            max=12,
                            precision=0,
                        )
                        .props("dense outlined")
                        .classes("flex-1 min-w-0")
                    )
                    b_day = (
                        ui.number(
                            "Day",
                            value=(editing.birth_day or None) if editing else None,
                            min=1,
                            max=31,
                            precision=0,
                        )
                        .props("dense outlined")
                        .classes("flex-1 min-w-0")
                    )

                # Death Date inputs
                ui.label("Death Date").classes(
                    "text-[11px] font-semibold text-stone-600 leading-none mt-1"
                )
                with ui.row().classes("w-full flex-nowrap gap-1.5 items-center"):
                    d_year = (
                        ui.input(
                            "Year",
                            value=(editing.death_year or "") if editing else "",
                        )
                        .props("dense outlined")
                        .classes("flex-2 min-w-0")
                    )
                    d_month = (
                        ui.number(
                            "Month",
                            value=(editing.death_month or None) if editing else None,
                            min=1,
                            max=12,
                            precision=0,
                        )
                        .props("dense outlined")
                        .classes("flex-1 min-w-0")
                    )
                    d_day = (
                        ui.number(
                            "Day",
                            value=(editing.death_day or None) if editing else None,
                            min=1,
                            max=31,
                            precision=0,
                        )
                        .props("dense outlined")
                        .classes("flex-1 min-w-0")
                    )

            place_in = (
                ui.input(
                    "Birth / Home Place",
                    value=(editing.birth_place or "") if editing else "",
                )
                .props("dense outlined")
                .classes("w-full")
            )

            place_death = (
                ui.input(
                    "Death / Burial Place",
                    value=(editing.death_place or "") if editing else "",
                )
                .props("dense outlined")
                .classes("w-full")
            )

            bio_in = (
                ui.textarea(
                    "Short Card Bio (shown inside box)",
                    value=(editing.bio_short or "") if editing else "",
                )
                .props("dense outlined rows=2 autogrow=false")
                .classes("w-full")
            )

            focus_in = (
                ui.checkbox(
                    "Focus Line (extends past early 1800s)",
                    value=editing.is_focus_line if editing else False,
                )
                .props("dense")
                .classes("text-xs mt-0.5")
            )

            def on_save_click() -> None:
                common_fields = {
                    "full_name": name_in.value.strip(),
                    "birth_year": b_year.value.strip() or None,
                    "birth_month": int(b_month.value) if b_month.value else None,
                    "birth_day": int(b_day.value) if b_day.value else None,
                    "death_year": d_year.value.strip() or None,
                    "death_month": int(d_month.value) if d_month.value else None,
                    "death_day": int(d_day.value) if d_day.value else None,
                    "birth_place": place_in.value.strip() or None,
                    "death_place": place_death.value.strip() or None,
                    "bio_short": bio_in.value.strip() or None,
                    "is_focus_line": focus_in.value,
                }
                self._save_person(editing, common_fields)

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                if editing:
                    ui.button("Cancel", on_click=self._cancel_edit).props("flat")
                ui.button("Save Person", icon="save", on_click=on_save_click)

    def _save_person(self, editing: Person | None, fields: dict) -> None:
        try:
            if editing:
                person = Person(
                    id=editing.id,
                    share_code=editing.share_code,
                    **fields,
                )
            else:
                person = Person(**fields)

            self.repo.save_person(person)
            self.selected_person_id = None
            ui.notify(f"Saved {person.full_name}", type="positive")
            self.on_change()
        except ValidationError as err:
            ui.notify(err.errors()[0]["msg"], type="negative")

    def _select_person(self, person_id: str) -> None:
        self.selected_person_id = person_id
        self.render.refresh()
        if self.on_edit_started:
            self.on_edit_started()

    def _cancel_edit(self) -> None:
        self.selected_person_id = None
        self.render.refresh()

    def _delete_person(self, person_id: str) -> None:
        self.repo.delete_person(person_id)
        if self.selected_person_id == person_id:
            self.selected_person_id = None
        ui.notify("Person removed", type="info")
        self.on_change()

    def _render_controls(self) -> None:
        with ui.row().classes("w-full items-center gap-2 mb-2"):
            ui.input(
                placeholder="Filter by name, dates, place...",
                value=self.search_query,
                on_change=lambda e: self._update_people_filter(e.value),
            ).props("dense clearable outlined").classes("flex-1")

            ui.select(
                options={
                    "name_asc": "Name (A–Z)",
                    "name_desc": "Name (Z–A)",
                    "birth_asc": "Birth Year (Oldest)",
                    "birth_desc": "Birth Year (Newest)",
                },
                value=self.sort_mode,
                on_change=lambda e: self._update_people_sort(e.value),
            ).props("dense outlined").classes("w-44")

    @ui.refreshable
    def _render_directory(self, people: list) -> None:
        visible = filtered_and_sorted_people(
            people,
            search_query=self.search_query,
            sort_mode=self.sort_mode,
        )
        ui.label(f"Directory ({len(visible)} / {len(people)})").classes(
            "text-xs uppercase font-bold text-stone-500 mb-1"
        )
        with ui.column().classes("w-full gap-0.5"):
            for p in visible:
                with ui.card().classes(
                    "w-full py-1 px-2.5 !my-0.5 flex-row items-center justify-between"
                ):
                    with ui.column().classes("gap-0 leading-tight"):
                        ui.label(p.full_name).classes("font-medium text-sm")
                        if p.lifespan_label:
                            ui.label(p.lifespan_label).classes("text-xs text-stone-500")
                    with ui.row().classes("gap-0.5"):
                        ui.button(
                            icon="edit",
                            on_click=lambda _, pid=p.id: self._select_person(pid),
                        ).props("flat dense size=sm")
                        ui.button(
                            icon="delete",
                            on_click=lambda _, pid=p.id: self._delete_person(pid),
                        ).props("flat dense size=sm color=negative")

    def _update_people_filter(self, value: str) -> None:
        self.search_query = value or ""
        self._render_directory.refresh()

    def _update_people_sort(self, value: str) -> None:
        self.sort_mode = value or "name_asc"
        self._render_directory.refresh()
