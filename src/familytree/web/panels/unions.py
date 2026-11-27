from collections.abc import Callable

from nicegui import ui
from pydantic import ValidationError

from familytree.domain.models import Union
from familytree.storage.repository import FamilyRepository


class UnionsPanel:
    """Self-contained UI panel for managing unions/partnerships and parent-child links."""

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
        people = self.repo.list_people()
        unions = self.repo.list_unions()

        person_options = {
            p.id: f"{p.full_name} ({p.lifespan_label or '?'})" for p in people
        }
        people_by_id = {p.id: p for p in people}
        unions_by_id = {u.id: u for u in unions}

        child_links = getattr(snapshot, "union_children", None)
        if child_links is None and hasattr(self.repo, "list_union_children"):
            child_links = self.repo.list_union_children()
        child_links = list(child_links or [])

        self._render_create_union_card(person_options)
        self._render_unions_list_card(unions, person_options)

        union_options = {
            u.id: self._format_union_label(u, person_options) for u in unions
        }
        self._render_link_child_card(union_options, person_options)
        self._render_relationships_card(
            child_links=child_links,
            unions=unions,
            people=people,
            unions_by_id=unions_by_id,
            people_by_id=people_by_id,
            person_options=person_options,
            union_options=union_options,
        )

    def refresh(self) -> None:
        self.render.refresh()

    # --- Label & Filter Helpers ---

    def _union_partners(
        self, union: Union, person_options: dict[str, str]
    ) -> tuple[str, str]:
        n1 = person_options.get(union.partner1_id, union.partner1_id)
        n2 = (
            person_options.get(union.partner2_id, "Single Parent")
            if union.partner2_id
            else "Single Parent"
        )
        return n1, n2

    def _format_union_label(self, union: Union, person_options: dict[str, str]) -> str:
        n1, n2 = self._union_partners(union, person_options)
        details = [f"{n1} + {n2}"]
        if union.formatted_marriage_date:
            details.append(union.formatted_marriage_date)
        if union.location:
            flag = f"{union.marriage_flag_emoji} " if union.marriage_flag_emoji else ""
            details.append(f"{flag}{union.location}")
        return " · ".join(details)

    def _matches_union_filter(
        self,
        union: Union,
        query: str,
        union_type: str,
        person_options: dict[str, str],
    ) -> bool:
        if union_type == "partnered" and not union.partner2_id:
            return False
        if union_type == "single" and union.partner2_id:
            return False
        q = query.strip().lower()
        if not q:
            return True
        n1, n2 = self._union_partners(union, person_options)
        haystack = " ".join(
            filter(
                None,
                [
                    n1,
                    n2,
                    union.marriage_year,
                    union.formatted_marriage_date,
                    union.location,
                ],
            )
        ).lower()
        return q in haystack

    # --- Create & Edit Unions ---

    def _render_create_union_card(self, person_options: dict[str, str]) -> None:
        with ui.card().classes("w-full mb-4"):
            ui.label("Create Partnership / Union").classes(
                "font-semibold text-sm leading-tight"
            )
            p1_sel = (
                ui.select(person_options, label="Partner 1 *", with_input=True)
                .props("dense outlined")
                .classes("w-full")
            )
            p2_sel = (
                ui.select(
                    person_options,
                    label="Partner 2 (optional for single-parent lines)",
                    clearable=True,
                    with_input=True,
                )
                .props("dense outlined")
                .classes("w-full")
            )

            ui.label("Marriage Date").classes(
                "text-[11px] font-semibold text-stone-600 leading-none mt-0.5"
            )
            with ui.row().classes("w-full flex-nowrap gap-1.5 items-center"):
                m_year = (
                    ui.input("Year").props("dense outlined").classes("flex-2 min-w-0")
                )
                m_month = (
                    ui.number("Month", min=1, max=12, precision=0)
                    .props("dense outlined")
                    .classes("flex-1 min-w-0")
                )
                m_day = (
                    ui.number("Day", min=1, max=31, precision=0)
                    .props("dense outlined")
                    .classes("flex-1 min-w-0")
                )

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
                    self.on_change()
                except ValidationError as err:
                    ui.notify(err.errors()[0]["msg"], type="negative")

            ui.button("Add Union", icon="link", on_click=create_union).classes("mt-2")

    def _open_edit_union_dialog(
        self, union: Union, person_options: dict[str, str]
    ) -> None:
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

            ui.label("Marriage Date").classes(
                "text-xs font-semibold text-stone-600 mt-1"
            )
            with ui.row().classes("w-full gap-2"):
                year_edit = ui.input("Year", value=union.marriage_year or "").classes(
                    "flex-2"
                )
                month_edit = ui.number(
                    "Month", value=union.marriage_month, min=1, max=12, precision=0
                ).classes("flex-1")
                day_edit = ui.number(
                    "Day", value=union.marriage_day, min=1, max=31, precision=0
                ).classes("flex-1")

            loc_edit = ui.input("Location", value=union.location or "").classes(
                "w-full"
            )

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
                        marriage_month=int(month_edit.value)
                        if month_edit.value
                        else None,
                        marriage_day=int(day_edit.value) if day_edit.value else None,
                        location=loc_edit.value.strip() or None,
                    )
                    self.repo.save_union(updated)
                    dialog.close()
                    ui.notify("Union updated", type="positive")
                    self.on_change()
                except ValidationError as err:
                    ui.notify(err.errors()[0]["msg"], type="negative")

            with ui.row().classes("w-full justify-end gap-2 mt-3"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Save Changes", icon="save", on_click=save_changes)

        dialog.open()

    def _render_unions_list_card(
        self, unions: list[Union], person_options: dict[str, str]
    ) -> None:
        with ui.card().classes("w-full mb-4"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Existing Unions").classes("font-semibold text-base")
                count_label = ui.label(f"{len(unions)} total").classes(
                    "text-xs text-stone-500"
                )

            with ui.row().classes("w-full gap-2 items-center"):
                search_in = (
                    ui.input(placeholder="Search partner, year, or location...")
                    .props("dense clearable outlined")
                    .classes("flex-2")
                )
                type_sel = (
                    ui.select(
                        {
                            "all": "All Unions",
                            "partnered": "Partnered",
                            "single": "Single Parent",
                        },
                        value="all",
                    )
                    .props("dense outlined")
                    .classes("flex-1")
                )

            @ui.refreshable
            def render_union_rows() -> None:
                query_val = search_in.value or ""
                type_val = type_sel.value or "all"
                filtered = [
                    u
                    for u in unions
                    if self._matches_union_filter(
                        u, query_val, type_val, person_options
                    )
                ]
                count_label.set_text(f"{len(filtered)} of {len(unions)}")

                with ui.scroll_area().classes(
                    "w-full h-56 border border-stone-200 rounded px-1.5 py-1"
                ):
                    if not filtered:
                        ui.label("No matching unions.").classes(
                            "text-xs text-stone-500 py-1 px-1"
                        )
                    else:
                        for u in filtered:
                            with ui.row().classes(
                                "w-full flex-nowrap items-start justify-between gap-1 py-0.5 "
                                "border-b border-stone-100 last:border-b-0"
                            ):
                                ui.label(
                                    self._format_union_label(u, person_options)
                                ).classes(
                                    "flex-1 min-w-0 text-xs leading-tight break-words"
                                )
                                ui.button(
                                    icon="edit",
                                    on_click=lambda _, target=u: (
                                        self._open_edit_union_dialog(
                                            target, person_options
                                        )
                                    ),
                                ).props("flat dense round size=xs").classes(
                                    "shrink-0"
                                ).style(
                                    "min-height: 22px; min-width: 22px; padding: 0;"
                                )

            search_in.on_value_change(lambda _: render_union_rows.refresh())
            type_sel.on_value_change(lambda _: render_union_rows.refresh())
            render_union_rows()

    # --- Child Linking & Parent-Child Relationships ---

    def _render_link_child_card(
        self,
        union_options: dict[str, str],
        person_options: dict[str, str],
    ) -> None:
        with ui.card().classes("w-full p-3 gap-1"):
            ui.label("Link Child to Parents").classes(
                "font-semibold text-sm leading-tight"
            )
            u_sel = (
                ui.select(union_options, label="Parental Union *", with_input=True)
                .props("dense outlined")
                .classes("w-full")
            )
            c_sel = (
                ui.select(person_options, label="Child *", with_input=True)
                .props("dense outlined")
                .classes("w-full")
            )
            order_in = (
                ui.number("Birth Order (1, 2, 3...)", min=1, precision=0)
                .props("dense outlined")
                .classes("w-full")
            )
            unc_in = (
                ui.checkbox("Uncertain relationship")
                .props("dense")
                .classes("text-xs mt-0.5")
            )

            def link_child() -> None:
                if not u_sel.value or not c_sel.value:
                    ui.notify("Select both a union and a child", type="warning")
                    return
                self.repo.add_child_to_union(
                    union_id=u_sel.value,
                    child_id=c_sel.value,
                    uncertain=bool(unc_in.value),
                    birth_order=int(order_in.value) if order_in.value else None,
                )
                ui.notify("Child linked to union", type="positive")
                self.on_change()

            ui.button("Link Child", icon="child_care", on_click=link_child).props(
                "dense"
            ).classes("mt-1")

    def _link_child_name(self, link, people_by_id: dict) -> str:
        child = people_by_id.get(link.child_id)
        return child.full_name if child else link.child_id

    def _link_parents_label(
        self, link, unions_by_id: dict, person_options: dict[str, str]
    ) -> str:
        u = unions_by_id.get(link.union_id)
        if not u:
            return link.union_id
        n1, n2 = self._union_partners(u, person_options)
        return f"{n1} + {n2}"

    def _link_birth_order_key(self, link) -> tuple[int, int]:
        return (0, link.birth_order) if link.birth_order is not None else (1, 9999)

    def _matches_child_link(
        self,
        link,
        query: str,
        child_filter: str,
        parent_filter: str,
        certainty_filter: str,
        people_by_id: dict,
        unions_by_id: dict,
        person_options: dict[str, str],
    ) -> bool:
        if child_filter and child_filter != "all" and link.child_id != child_filter:
            return False
        if parent_filter and parent_filter != "all" and link.union_id != parent_filter:
            return False
        is_uncertain = bool(getattr(link, "uncertain", False))
        if certainty_filter == "uncertain" and not is_uncertain:
            return False
        if certainty_filter == "certain" and is_uncertain:
            return False

        q = query.strip().lower()
        if not q:
            return True
        haystack = " ".join(
            filter(
                None,
                [
                    self._link_child_name(link, people_by_id),
                    self._link_parents_label(link, unions_by_id, person_options),
                    str(link.birth_order or ""),
                    "uncertain dashed" if is_uncertain else "certain solid",
                ],
            )
        ).lower()
        return q in haystack

    def _sort_child_links(
        self,
        links: list,
        sort_mode: str,
        people_by_id: dict,
        unions_by_id: dict,
        person_options: dict[str, str],
    ) -> list:
        if sort_mode == "child_asc":
            return sorted(
                links,
                key=lambda l: (
                    self._link_child_name(l, people_by_id).lower(),
                    self._link_parents_label(l, unions_by_id, person_options).lower(),
                ),
            )
        if sort_mode == "child_desc":
            return sorted(
                links,
                key=lambda l: (
                    self._link_child_name(l, people_by_id).lower(),
                    self._link_parents_label(l, unions_by_id, person_options).lower(),
                ),
                reverse=True,
            )
        if sort_mode == "parents_asc":
            return sorted(
                links,
                key=lambda l: (
                    self._link_parents_label(l, unions_by_id, person_options).lower(),
                    self._link_child_name(l, people_by_id).lower(),
                ),
            )
        if sort_mode == "parents_desc":
            return sorted(
                links,
                key=lambda l: (
                    self._link_parents_label(l, unions_by_id, person_options).lower(),
                    self._link_child_name(l, people_by_id).lower(),
                ),
                reverse=True,
            )
        if sort_mode == "order_asc":
            return sorted(
                links,
                key=lambda l: (
                    self._link_birth_order_key(l),
                    self._link_child_name(l, people_by_id).lower(),
                ),
            )
        if sort_mode == "uncertain_first":
            return sorted(
                links,
                key=lambda l: (
                    0 if getattr(l, "uncertain", False) else 1,
                    self._link_child_name(l, people_by_id).lower(),
                ),
            )
        return links

    def _open_edit_link_dialog(
        self,
        link,
        union_options: dict[str, str],
        person_options: dict[str, str],
    ) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-md p-3 gap-2"):
            ui.label("Edit Parent-Child Link").classes("font-semibold text-base")

            u_edit = (
                ui.select(
                    union_options,
                    label="Parental Union *",
                    value=link.union_id,
                    with_input=True,
                )
                .props("dense outlined")
                .classes("w-full")
            )
            c_edit = (
                ui.select(
                    person_options,
                    label="Child *",
                    value=link.child_id,
                    with_input=True,
                )
                .props("dense outlined")
                .classes("w-full")
            )
            order_edit = (
                ui.number(
                    "Birth Order (1, 2, 3...)",
                    value=link.birth_order,
                    min=1,
                    precision=0,
                )
                .props("dense outlined")
                .classes("w-full")
            )
            uncertain_edit = (
                ui.checkbox(
                    "Uncertain relationship (dashed line)",
                    value=bool(getattr(link, "uncertain", False)),
                )
                .props("dense")
                .classes("text-xs")
            )

            def save_link_changes() -> None:
                if not u_edit.value or not c_edit.value:
                    ui.notify("Select both a union and a child", type="warning")
                    return
                new_order = int(order_edit.value) if order_edit.value else None
                new_uncertain = bool(uncertain_edit.value)

                if u_edit.value != link.union_id or c_edit.value != link.child_id:
                    self.repo.delete_child_from_union(link.union_id, link.child_id)
                self.repo.add_child_to_union(
                    union_id=u_edit.value,
                    child_id=c_edit.value,
                    birth_order=new_order,
                    uncertain=new_uncertain,
                )
                dialog.close()
                ui.notify("Relationship updated", type="positive")
                self.on_change()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat dense")
                ui.button(
                    "Save Changes", icon="save", on_click=save_link_changes
                ).props("dense")

        dialog.open()

    def _delete_link(self, link) -> None:
        self.repo.delete_child_from_union(link.union_id, link.child_id)
        ui.notify("Relationship removed", type="info")
        self.on_change()

    def _render_relationships_card(
        self,
        child_links: list,
        unions: list[Union],
        people: list,
        unions_by_id: dict,
        people_by_id: dict,
        person_options: dict[str, str],
        union_options: dict[str, str],
    ) -> None:
        child_filter_options = {
            "all": "All Children",
            **{p.id: p.full_name for p in people},
        }
        parent_filter_options = {
            "all": "All Parents / Unions",
            **{u.id: self._format_union_label(u, person_options) for u in unions},
        }

        with ui.card().classes("w-full p-2.5 gap-1.5 mt-3"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Parent–Child Relationships").classes(
                    "font-semibold text-sm leading-tight"
                )
                rel_count_label = ui.label(f"{len(child_links)} total").classes(
                    "text-[11px] text-stone-500"
                )

            rel_search = (
                ui.input(placeholder="Search child, parents, or order...")
                .props("dense clearable outlined")
                .classes("w-full")
            )

            with ui.row().classes("w-full gap-1.5 items-center"):
                child_filter_sel = (
                    ui.select(
                        child_filter_options,
                        value="all",
                        label="Child",
                        with_input=True,
                    )
                    .props("dense outlined")
                    .classes("flex-1 min-w-0")
                )
                parent_filter_sel = (
                    ui.select(parent_filter_options, value="all", label="Parents")
                    .props("dense outlined")
                    .classes("flex-1 min-w-0")
                )

            with ui.row().classes("w-full gap-1.5 items-center"):
                certainty_sel = (
                    ui.select(
                        {
                            "all": "All Lines",
                            "uncertain": "Uncertain (Dashed)",
                            "certain": "Certain (Solid)",
                        },
                        value="all",
                        label="Line Style",
                    )
                    .props("dense outlined")
                    .classes("flex-1 min-w-0")
                )

                rel_sort_sel = (
                    ui.select(
                        {
                            "child_asc": "Child (A–Z)",
                            "child_desc": "Child (Z–A)",
                            "parents_asc": "Parents (A–Z)",
                            "parents_desc": "Parents (Z–A)",
                            "order_asc": "Birth Order",
                            "uncertain_first": "Uncertain First",
                        },
                        value="child_asc",
                        label="Sort By",
                    )
                    .props("dense outlined")
                    .classes("flex-1 min-w-0")
                )

            @ui.refreshable
            def render_relationship_rows() -> None:
                filtered = [
                    l
                    for l in child_links
                    if self._matches_child_link(
                        l,
                        rel_search.value or "",
                        child_filter_sel.value or "all",
                        parent_filter_sel.value or "all",
                        certainty_sel.value or "all",
                        people_by_id,
                        unions_by_id,
                        person_options,
                    )
                ]
                ordered = self._sort_child_links(
                    filtered,
                    rel_sort_sel.value or "child_asc",
                    people_by_id,
                    unions_by_id,
                    person_options,
                )
                rel_count_label.set_text(f"{len(ordered)} of {len(child_links)}")

                with ui.scroll_area().classes(
                    "w-full h-56 border border-stone-200 rounded px-1 py-0.5"
                ):
                    if not ordered:
                        ui.label("No matching relationships.").classes(
                            "text-xs text-stone-500 py-1 px-1"
                        )
                    else:
                        for l in ordered:
                            is_uncertain = bool(getattr(l, "uncertain", False))
                            meta_parts = [
                                f"Parents: {self._link_parents_label(l, unions_by_id, person_options)}"
                            ]
                            if l.birth_order is not None:
                                meta_parts.append(f"#{l.birth_order}")
                            if is_uncertain:
                                meta_parts.append("Dashed (Uncertain)")

                            with ui.row().classes(
                                "w-full flex-nowrap items-center justify-between gap-1 py-0.5 px-1 "
                                "border-b border-stone-100 last:border-b-0"
                            ):
                                with ui.column().classes("flex-1 min-w-0 gap-0"):
                                    ui.label(
                                        self._link_child_name(l, people_by_id)
                                    ).classes(
                                        "text-xs font-medium leading-tight truncate"
                                    )
                                    ui.label(" · ".join(meta_parts)).classes(
                                        "text-[11px] leading-tight truncate "
                                        + (
                                            "text-amber-700 font-medium"
                                            if is_uncertain
                                            else "text-stone-500"
                                        )
                                    )

                                with ui.row().classes("shrink-0 items-center gap-0.5"):
                                    ui.button(
                                        icon="edit",
                                        on_click=lambda _, target=l: (
                                            self._open_edit_link_dialog(
                                                target, union_options, person_options
                                            )
                                        ),
                                    ).props("flat dense round size=xs").style(
                                        "min-height: 22px; min-width: 22px; padding: 0;"
                                    )
                                    ui.button(
                                        icon="delete",
                                        on_click=lambda _, target=l: self._delete_link(
                                            target
                                        ),
                                    ).props(
                                        "flat dense round size=xs color=negative"
                                    ).style(
                                        "min-height: 22px; min-width: 22px; padding: 0;"
                                    )

            rel_search.on_value_change(lambda _: render_relationship_rows.refresh())
            child_filter_sel.on_value_change(
                lambda _: render_relationship_rows.refresh()
            )
            parent_filter_sel.on_value_change(
                lambda _: render_relationship_rows.refresh()
            )
            certainty_sel.on_value_change(lambda _: render_relationship_rows.refresh())
            rel_sort_sel.on_value_change(lambda _: render_relationship_rows.refresh())
            render_relationship_rows()
