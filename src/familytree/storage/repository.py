from pydantic import BaseModel, Field
from sqlalchemy import Engine, delete, or_
from sqlmodel import select

from familytree.domain.models import Person, StoryNote, Union, UnionChild
from familytree.storage.database import engine as default_engine
from familytree.storage.database import get_session


class TreeSnapshot(BaseModel):
    """Immutable, detached snapshot of the entire genealogy graph for compilation."""

    people: list[Person] = Field(default_factory=list)
    unions: list[Union] = Field(default_factory=list)
    children: list[UnionChild] = Field(default_factory=list)
    story_notes: list[StoryNote] = Field(default_factory=list)
    union_children: list[UnionChild] = Field(default_factory=list)


class FamilyRepository:
    """Encapsulates all persistence operations for the family tree."""

    def __init__(self, target_engine: Engine | None = None) -> None:
        self._engine = target_engine or default_engine

    # --- People ---

    def save_person(self, person: Person) -> Person:
        """Insert or update a Person record."""
        with get_session(self._engine) as session:
            merged = session.merge(person)
            session.flush()
            session.refresh(merged)
            return merged

    def get_person(self, person_id: str) -> Person | None:
        with get_session(self._engine) as session:
            return session.get(Person, person_id)

    def list_people(self) -> list[Person]:
        with get_session(self._engine) as session:
            stmt = select(Person).order_by(Person.full_name)
            return list(session.exec(stmt).all())

    def delete_person(self, person_id: str) -> None:
        """Safely removes a person and cleans up dependent links/unions."""
        with get_session(self._engine) as session:
            # 1. Remove any story notes attached directly to this person
            session.exec(delete(StoryNote).where(StoryNote.person_id == person_id))

            # 2. Remove child links where this person is a child
            session.exec(delete(UnionChild).where(UnionChild.child_id == person_id))

            # 3. Clean up unions involving this person
            unions = session.exec(
                select(Union).where(
                    or_(Union.partner1_id == person_id, Union.partner2_id == person_id)
                )
            ).all()

            for union in unions:
                if union.partner1_id == person_id and union.partner2_id:
                    # Promote partner2 to partner1 so the remaining lineage stays intact
                    union.partner1_id = union.partner2_id
                    union.partner2_id = None
                    session.add(union)
                elif union.partner2_id == person_id:
                    union.partner2_id = None
                    session.add(union)
                else:
                    # Sole partner in this union: remove union notes, child links, and union
                    session.exec(
                        delete(StoryNote).where(StoryNote.union_id == union.id)
                    )
                    session.exec(
                        delete(UnionChild).where(UnionChild.union_id == union.id)
                    )
                    session.delete(union)

            # 4. Delete the person record itself
            person = session.get(Person, person_id)
            if person:
                session.delete(person)

    # --- Unions & Children ---

    def save_union(self, union: Union) -> Union:
        """Insert or update a Union record."""
        # Re-run model validation explicitly in case fields were mutated in UI
        Union.model_validate(union.model_dump())
        with get_session(self._engine) as session:
            merged = session.merge(union)
            session.flush()
            session.refresh(merged)
            return merged

    def list_unions(self) -> list[Union]:
        with get_session(self._engine) as session:
            return list(session.exec(select(Union)).all())

    def add_child_to_union(
        self,
        union_id: str,
        child_id: str,
        uncertain: bool,
        birth_order: int | None = None,
    ) -> UnionChild:
        """Links an existing Person as a child of a Union."""
        if not self.get_person(child_id):
            raise ValueError(f"Child person '{child_id}' does not exist.")

        link = UnionChild(
            union_id=union_id,
            child_id=child_id,
            birth_order=birth_order,
            uncertain=uncertain,
        )
        with get_session(self._engine) as session:
            merged = session.merge(link)
            session.flush()
            session.refresh(merged)
            return merged

    def remove_child_from_union(self, union_id: str, child_id: str) -> None:
        with get_session(self._engine) as session:
            session.exec(
                delete(UnionChild).where(
                    UnionChild.union_id == union_id,
                    UnionChild.child_id == child_id,
                )
            )

    # --- Story Notes ---

    def save_story_note(self, note: StoryNote) -> StoryNote:
        """Insert or update a narrative box attached to a person or union."""
        StoryNote.model_validate(note.model_dump())
        with get_session(self._engine) as session:
            merged = session.merge(note)
            session.flush()
            session.refresh(merged)
            return merged

    def delete_story_note(self, note_id: str) -> None:
        with get_session(self._engine) as session:
            note = session.get(StoryNote, note_id)
            if note:
                session.delete(note)

    # --- Full Graph Read ---

    def get_snapshot(self) -> TreeSnapshot:
        """Fetches all entities in one read pass for the Graphviz compiler."""
        with get_session(self._engine) as session:
            people = list(session.exec(select(Person)).all())
            unions = list(session.exec(select(Union)).all())
            children = list(
                session.exec(
                    select(UnionChild).order_by(
                        UnionChild.union_id,
                        UnionChild.birth_order.asc(),
                    )
                ).all()
            )
            union_children = list(
                session.exec(
                    select(UnionChild).order_by(
                        UnionChild.union_id,
                        UnionChild.birth_order.asc(),
                    )
                ).all()
            )
            notes = list(session.exec(select(StoryNote)).all())

            return TreeSnapshot(
                people=people,
                unions=unions,
                children=children,
                story_notes=notes,
                union_children=union_children,
            )
