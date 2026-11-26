from typing import Optional
from uuid import uuid4
from pydantic import model_validator
from sqlmodel import Field, SQLModel
from familytree.domain.flags import get_location_flag


def _new_id() -> str:
    """Short, Graphviz-safe alphanumeric ID (avoids hyphens in DOT node names)."""
    return f"n_{uuid4().hex[:10]}"

def _parse_num_val(val: object) -> Optional[int]:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    s = str(val).strip()
    return int(s) if s.isdigit() else None


def _format_date(year: Optional[str], month: Optional[int | str], day: Optional[int | str]) -> str:
    if not year:
        return ""
    month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    m_int: Optional[int] = None
    if isinstance(month, int):
        m_int = month
    elif isinstance(month, str) and month.strip().isdigit():
        m_int = int(month.strip())
    m_str = month_names[m_int] if m_int is not None and 1 <= m_int <= 12 else ""
    d_str = str(day).strip() if day is not None and str(day).strip() else ""

    parts = [p for p in [d_str, m_str, year] if p]
    return " ".join(parts)


class Person(SQLModel, table=True):
    __tablename__ = "people"

    id: str = Field(default_factory=_new_id, primary_key=True)
    full_name: str = Field(min_length=1, max_length=120, index=True)
    birth_year: Optional[str] = None  # Keeps support for "c. 1812", "abt 1794", etc.
    birth_month: Optional[int] = Field(default=None, ge=1, le=12)
    birth_day: Optional[int] = Field(default=None, ge=1, le=31)

    death_year: Optional[str] = None
    death_month: Optional[int] = Field(default=None, ge=1, le=12)
    death_day: Optional[int] = Field(default=None, ge=1, le=31)

    birth_place: Optional[str] = Field(default=None, max_length=120)
    death_place: Optional[str] = Field(default=None, max_length=120)
    bio_short: Optional[str] = Field(
        default=None,
        max_length=400,
        description="Concise summary rendered inside the person's tree card",
    )
    is_focus_line: bool = Field(
        default=False,
        description="Highlight branches extending past the early 1800s",
    )
    share_code: Optional[int] = Field(default=None, unique=True)

    @property
    def birth_label(self) -> str:
        """Formats dates cleanly for display on the Graphviz node."""
        b = _format_date(self.birth_year, self.birth_month, self.birth_day)
        if not b:
            return ""
        return f"{b}"

    @property
    def age_at_death_label(self) -> Optional[str]:
        """Returns age as '65' when exact enough, '~65' when rough, or None."""
        b_year = _parse_num_val(self.birth_year)
        d_year = _parse_num_val(self.death_year)

        if b_year is None or d_year is None:
            return "?"

        years = d_year - b_year
        if years < 0:
            return "?"

        b_month = _parse_num_val(self.birth_month)
        b_day = _parse_num_val(self.birth_day)
        d_month = _parse_num_val(self.death_month)
        d_day = _parse_num_val(self.death_day)
        has_full_months = self.birth_month is not None and self.death_month is not None

        if has_full_months:
            b_md = (b_month, b_day or 1)
            d_md = (d_month, d_day or 1)
            if d_md < b_md:
                years -= 1
            age = max(years, 0)
            # If day is missing on either side, the month boundary is approximate
            if self.birth_day is None or self.death_day is None:
                return f"~{age}"
            return str(age)

        # Missing one or both months: rough year-only estimate
        return f"~{max(years, 0)}"

    @property
    def death_label(self) -> str:
        """Formats dates cleanly for display on the Graphviz node."""
        d = _format_date(self.death_year, self.death_month, self.death_day)
        if not d:
            return ""
        return f"{d}"

    @property
    def lifespan_label(self) -> str:
        """Formats dates cleanly for display on the Graphviz node."""
        b = _format_date(self.birth_year, self.birth_month, self.birth_day)
        d = _format_date(self.death_year, self.death_month, self.death_day)
        if not b and not d:
            return ""
        return f"{b} – {d}"

    @property
    def birth_flag_emoji(self) -> str:
        return get_location_flag(self.birth_place)

    @property
    def death_flag_emoji(self) -> str:
        return get_location_flag(self.death_place)


class Union(SQLModel, table=True):
    """Represents a marriage or partnership node between two people."""

    __tablename__ = "unions"

    id: str = Field(default_factory=_new_id, primary_key=True)
    partner1_id: str = Field(foreign_key="people.id", index=True)
    partner2_id: Optional[str] = Field(
        default=None,
        foreign_key="people.id",
        index=True,
        description="Nullable when only one parent/ancestor is known in older lines",
    )
    marriage_year: Optional[str] = None
    marriage_month: Optional[int] = Field(default=None, ge=1, le=12)
    marriage_day: Optional[int] = Field(default=None, ge=1, le=31)

    location: Optional[str] = Field(default=None, max_length=120)

    @property
    def formatted_marriage_date(self) -> str:
        return _format_date(self.marriage_year, self.marriage_month, self.marriage_day)

    @property
    def marriage_flag_emoji(self) -> str:
        return get_location_flag(self.location)

    @model_validator(mode="after")
    def partners_must_differ(self) -> "Union":
        if self.partner2_id and self.partner1_id == self.partner2_id:
            raise ValueError("A person cannot form a union with themselves.")
        return self


class UnionChild(SQLModel, table=True):
    """Junction table linking a child to a parental Union."""

    __tablename__ = "union_children"

    union_id: str = Field(foreign_key="unions.id", primary_key=True)
    child_id: str = Field(foreign_key="people.id", primary_key=True)
    birth_order: Optional[int] = Field(default=None, ge=1)
    uncertain: bool = Field(default=False)


class StoryNote(SQLModel, table=True):
    """Narrative callout box linked to either a specific person or a couple."""

    __tablename__ = "story_notes"

    id: str = Field(default_factory=_new_id, primary_key=True)
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=1500)
    person_id: Optional[str] = Field(default=None, foreign_key="people.id", index=True)
    union_id: Optional[str] = Field(default=None, foreign_key="unions.id", index=True)

    @model_validator(mode="after")
    def validate_single_anchor(self) -> "StoryNote":
        has_person = bool(self.person_id)
        has_union = bool(self.union_id)
        if has_person == has_union:
            raise ValueError(
                "StoryNote must link to exactly one target: either person_id or union_id."
            )
        return self