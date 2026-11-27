from collections.abc import Iterable


def filtered_and_sorted_people(
    people: Iterable,
    search_query: str = "",
    sort_mode: str = "name_asc",
) -> list:
    items = list(people)
    query = (search_query or "").strip().lower()
    if query:
        items = [
            p
            for p in items
            if query in (p.full_name or "").lower()
            or query in (p.lifespan_label or "").lower()
            or query in (getattr(p, "birth_place", "") or "").lower()
        ]

    def birth_key(p):
        # Extract leading numeric year if available (e.g. "c. 1812" -> 1812), else push to end
        raw = (getattr(p, "birth_year", "") or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        return (0, int(digits[:4])) if len(digits) >= 4 else (1, 9999)

    if sort_mode == "name_asc":
        return sorted(items, key=lambda p: (p.full_name or "").lower())
    if sort_mode == "name_desc":
        return sorted(items, key=lambda p: (p.full_name or "").lower(), reverse=True)
    if sort_mode == "birth_asc":
        return sorted(items, key=lambda p: (birth_key(p), (p.full_name or "").lower()))
    if sort_mode == "birth_desc":
        return sorted(
            items,
            key=lambda p: (
                birth_key(p)[0],
                -birth_key(p)[1],
                (p.full_name or "").lower(),
            ),
        )
    return items
