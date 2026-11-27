from collections.abc import Callable

from nicegui import ui
from pydantic import ValidationError

from familytree.domain.models import StoryNote
from familytree.storage.repository import FamilyRepository


class StoriesPanel:
    """Self-contained UI panel for creating, editing, filtering, and deleting story notes."""

    def __init__(
        self,
        repo: FamilyRepository,
        on_change: Callable[[], None],
    ) -> None:
        self.repo = repo
        self.on_change = on_change

    @ui.refreshable_method
    def render(self) -> None:
        snapshot = self.repo.get_snapshot()
        person_options = {p.id: f"Person: {p.full_name}" for p in snapshot.people}
        people_map = {p.id: p.full_name for p in snapshot.people}
        union_options = {
            u.id: (
                f"Couple: {people_map.get(u.partner1_id, '?')} & "
                f"{people_map.get(u.partner2_id or '', 'Single')}"
            )
            for u in snapshot.unions
        }
        all_targets = {**person_options, **union_options}

        self._render_add_story_card(all_targets, person_options)
        self._render_notes_list_card(
            notes=snapshot.story_notes,
            person_options=person_options,
            union_options=union_options,
            all_targets=all_targets,
        )

    def refresh(self) -> None:
        self.render.refresh()

    # --- Helpers ---

    def _target_label(
        self,
        note: StoryNote,
        person_options: dict[str, str],
        union_options: dict[str, str],
    ) -> str:
        if note.person_id:
            return person_options.get(note.person_id, f"Person: {note.person_id}")
        if note.union_id:
            return union_options.get(note.union_id, f"Couple: {note.union_id}")
        return "Unattached"

    def _current_target_id(self, note: StoryNote) -> str | None:
        return note.person_id or note.union_id

    def _matches_note(
        self,
        note: StoryNote,
        query: str,
        attach_filter: str,
        person_options: dict[str, str],
        union_options: dict[str, str],
    ) -> bool:
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
                    self._target_label(note, person_options, union_options),
                ],
            )
        ).lower()
        return q in haystack

    def _delete_note(self, note_id: str) -> None:
        self.repo.delete_story_note(note_id)
        ui.notify("Story box removed", type="info")
        self.on_change()

    # --- Add & Edit Story UI ---

    def _open_edit_dialog(
        self,
        note: StoryNote,
        all_targets: dict[str, str],
        person_options: dict[str, str],
    ) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
            ui.label("Edit Story Box").classes("font-semibold text-lg")

            target_edit = ui.select(
                all_targets,
                label="Attach To (Person or Couple) *",
                value=self._current_target_id(note),
                with_input=True,
            ).classes("w-full")
            title_edit = ui.input("Story Box Title *", value=note.title).classes(
                "w-full"
            )
            body_edit = (
                ui.textarea("Story Narrative *", value=note.body)
                .props("rows=5")
                .classes("w-full")
            )

            def save_changes() -> None:
                target = target_edit.value
                if not target:
                    ui.notify(
                        "Select a person or couple to attach this story to",
                        type="warning",
                    )
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
                    self.on_change()
                except ValidationError as err:
                    ui.notify(err.errors()[0]["msg"], type="negative")

            with ui.row().classes("w-full justify-end gap-2 mt-3"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Save Changes", icon="save", on_click=save_changes)

        dialog.open()

    def _render_add_story_card(
        self,
        all_targets: dict[str, str],
        person_options: dict[str, str],
    ) -> None:
        with ui.card().classes("w-full mb-2 p-3 gap-1"):
            ui.label("Add Linked Story Box").classes(
                "font-semibold text-sm leading-tight"
            )
            target_sel = (
                ui.select(
                    all_targets,
                    label="Attach To (Person or Couple) *",
                    with_input=True,
                )
                .props("dense outlined")
                .classes("w-full")
            )
            title_in = (
                ui.input("Story Box Title *").props("dense outlined").classes("w-full")
            )
            body_in = (
                ui.textarea("Story Narrative *")
                .props("dense outlined rows=3 autogrow=false")
                .classes("w-full")
            )

            def save_story() -> None:
                target = target_sel.value
                if not target:
                    ui.notify(
                        "Select a person or couple to attach this story to",
                        type="warning",
                    )
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
                    self.on_change()
                except ValidationError as err:
                    ui.notify(err.errors()[0]["msg"], type="negative")

            ui.button("Attach Story Box", icon="note_add", on_click=save_story).classes(
                "mt-2"
            )

    def _render_notes_list_card(
        self,
        notes: list[StoryNote],
        person_options: dict[str, str],
        union_options: dict[str, str],
        all_targets: dict[str, str],
    ) -> None:
        with ui.card().classes("w-full p-3"):
            with ui.row().classes("w-full items-center justify-between mb-1"):
                ui.label("Linked Story Boxes").classes("font-semibold text-base")
                count_label = ui.label(f"{len(notes)} total").classes(
                    "text-xs text-stone-500"
                )

            with ui.row().classes("w-full gap-2 items-center mb-2"):
                search_in = (
                    ui.input(placeholder="Search title, narrative, or person/couple...")
                    .props("dense clearable outlined")
                    .classes("flex-2")
                )
                filter_sel = (
                    ui.select(
                        {
                            "all": "All Notes",
                            "person": "People Only",
                            "union": "Couples Only",
                        },
                        value="all",
                    )
                    .props("dense outlined")
                    .classes("flex-1")
                )

            @ui.refreshable
            def render_note_rows() -> None:
                query_val = search_in.value or ""
                filter_val = filter_sel.value or "all"
                filtered = [
                    n
                    for n in notes
                    if self._matches_note(
                        n, query_val, filter_val, person_options, union_options
                    )
                ]
                count_label.set_text(f"{len(filtered)} of {len(notes)}")

                if not filtered:
                    ui.label("No matching story boxes.").classes(
                        "text-xs text-stone-500 py-1"
                    )
                    return

                with ui.column().classes("w-full gap-1"):
                    for n in filtered:
                        with ui.row().classes(
                            "w-full flex-nowrap items-center justify-between gap-2 "
                            "py-1 px-2 border border-stone-200 rounded"
                        ):
                            with ui.column().classes("flex-1 min-w-0 gap-0"):
                                ui.label(n.title).classes(
                                    "text-xs font-semibold leading-tight truncate"
                                )
                                ui.label(
                                    self._target_label(n, person_options, union_options)
                                ).classes(
                                    "text-[11px] text-stone-500 leading-tight truncate"
                                )
                            with ui.row().classes("shrink-0 items-center gap-0.5"):
                                ui.button(
                                    icon="edit",
                                    on_click=lambda _, target_note=n: (
                                        self._open_edit_dialog(
                                            target_note, all_targets, person_options
                                        )
                                    ),
                                ).props("flat dense round size=xs").style(
                                    "min-height: 22px; min-width: 22px; padding: 0;"
                                )
                                ui.button(
                                    icon="delete",
                                    on_click=lambda _, nid=n.id: self._delete_note(nid),
                                ).props(
                                    "flat dense round size=xs color=negative"
                                ).style(
                                    "min-height: 22px; min-width: 22px; padding: 0;"
                                )

            search_in.on_value_change(lambda _: render_note_rows.refresh())
            filter_sel.on_value_change(lambda _: render_note_rows.refresh())
            render_note_rows()
