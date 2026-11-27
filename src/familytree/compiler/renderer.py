import textwrap
from pathlib import Path

import graphviz
from jinja2 import Environment, FileSystemLoader, select_autoescape

from familytree.compiler.layout import LayoutConfig
from familytree.domain.models import Person, StoryNote, Union
from familytree.storage.repository import TreeSnapshot

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _wrap_text(text: str | None, width: int = 38) -> list[str]:
    """Wraps narrative text into short lines so Graphviz cards stay compact."""
    if not text:
        return []
    lines: list[str] = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            lines.append("")
        else:
            lines.extend(textwrap.wrap(paragraph, width=width))
    return lines


class TreeCompiler:
    """Pure transformation layer: converts a TreeSnapshot into DOT, SVG, or PDF."""

    def __init__(self, config: LayoutConfig | None = None) -> None:
        self.config = config or LayoutConfig()
        self._env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            # Escapes &, <, >, " so arbitrary story text never breaks DOT HTML syntax
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._person_tpl = self._env.get_template("person_card.html")
        self._note_tpl = self._env.get_template("story_note.html")

    def build_digraph(self, snapshot: TreeSnapshot) -> graphviz.Digraph:
        """Constructs the complete Graphviz Digraph object in memory."""
        dot = graphviz.Digraph(
            name="FamilyTree",
            graph_attr=self.config.to_graph_attrs(),
            node_attr=self.config.to_default_node_attrs(),
            edge_attr=self.config.to_default_edge_attrs(),
        )

        people_by_id: dict[str, Person] = {p.id: p for p in snapshot.people}
        unions_by_id: dict[str, Union] = {u.id: u for u in snapshot.unions}

        # 1. Render all Person nodes
        for person in snapshot.people:
            html_label = self._person_tpl.render(
                person=person,
                bio_lines=_wrap_text(person.bio_short, width=34),
                theme=self.config.theme,
            )
            # Wrapping in <...> tells Graphviz to parse the label as HTML
            dot.node(person.id, label=f"<{html_label}>")

        # 2. Render Union junction points and connect partners -> union
        for union in snapshot.unions:
            p1 = people_by_id.get(union.partner1_id)
            p2 = people_by_id.get(union.partner2_id) if union.partner2_id else None
            is_focus = bool((p1 and p1.is_focus_line) or (p2 and p2.is_focus_line))
            edge_color = (
                self.config.theme.focus_edge_color
                if is_focus
                else self.config.theme.lineage_edge_color
            )
            penwidth = "2.0" if is_focus else "1.3"

            # Tiny visible dot acting as the marriage/partnership junction
            dot.node(
                union.id,
                label="",
                shape="circle",
                style="filled",
                fillcolor=edge_color,
                color=edge_color,
                width="0.10",
                height="0.10",
                fixedsize="true",
                tooltip=f"Married {union.marriage_year}"
                if union.marriage_year
                else "Union",
            )

            if p1:
                dot.edge(p1.id, union.id, color=edge_color, penwidth=penwidth)
            if p2:
                dot.edge(p2.id, union.id, color=edge_color, penwidth=penwidth)

        # 3. Connect Union junctions -> Children
        for link in snapshot.children:
            union = unions_by_id.get(link.union_id)
            child = people_by_id.get(link.child_id)
            if not union or not child:
                continue

            edge_color = (
                self.config.theme.focus_edge_color
                if child.is_focus_line
                else self.config.theme.lineage_edge_color
            )
            penwidth = "2.0" if child.is_focus_line else "1.3"
            edge_style = "dashed" if getattr(link, "uncertain", False) else "solid"
            dot.edge(
                union.id,
                child.id,
                color=edge_color,
                penwidth=penwidth,
                style=edge_style,
            )

        # 4. Render StoryNote callout boxes and attach via dashed tethers
        for note in snapshot.story_notes:
            self._add_story_note(dot, note, people_by_id, unions_by_id)

        return dot

    def _add_story_note(
        self,
        dot: graphviz.Digraph,
        note: StoryNote,
        people_by_id: dict[str, Person],
        unions_by_id: dict[str, Union],
    ) -> None:
        target_id = note.person_id or note.union_id
        if not target_id:
            return
        if target_id not in people_by_id and target_id not in unions_by_id:
            return

        html_label = self._note_tpl.render(
            note=note,
            body_lines=_wrap_text(note.body, width=35),
            theme=self.config.theme,
        )
        # dot.node(note.id, label=f"<{html_label}>")
        dot.node(note.id, label=f"<{html_label}>")

        # constraint="false" prevents the story box from artificially pushing
        # the target person/couple into a later generation column!
        dot.edge(
            target_id,
            note.id,
            style="dashed",
            color=self.config.theme.note_edge_color,
            penwidth="1.2",
            # constraint="false",
        )

    def to_dot_source(self, snapshot: TreeSnapshot) -> str:
        """Returns the raw Graphviz DOT source code for debugging or export."""
        return self.build_digraph(snapshot).source

    def render_svg(self, snapshot: TreeSnapshot) -> str:
        """Compiles the snapshot in memory and returns an SVG string."""
        dot = self.build_digraph(snapshot)
        return dot.pipe(format="svg").decode("utf-8")

    def export_files(
        self, snapshot: TreeSnapshot, output_dir: Path = Path("output")
    ) -> dict[str, Path]:
        """Writes DOT, print-ready SVG, and PDF files to disk."""
        output_dir.mkdir(parents=True, exist_ok=True)
        dot = self.build_digraph(snapshot)

        dot_path = output_dir / "tree.dot"
        dot_path.write_text(dot.source, encoding="utf-8")

        svg_bytes = dot.pipe(format="svg")
        svg_path = output_dir / "tree.svg"
        svg_path.write_bytes(svg_bytes)

        pdf_bytes = dot.pipe(format="pdf")
        pdf_path = output_dir / "tree.pdf"
        pdf_path.write_bytes(pdf_bytes)

        return {"dot": dot_path, "svg": svg_path, "pdf": pdf_path}
