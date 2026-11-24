from pathlib import Path
import typer

from familytree.compiler.layout import LayoutConfig, PaperFormat
from familytree.compiler.renderer import TreeCompiler
from familytree.domain.models import Person, StoryNote, Union
from familytree.storage.database import init_db
from familytree.storage.repository import FamilyRepository
from familytree.web.app import start_server

app = typer.Typer(help="Programmatic Family Tree builder and Graphviz compiler.")


@app.command()
def serve(
    port: int = typer.Option(8080, help="Local port for the NiceGUI web interface."),
    reload: bool = typer.Option(False, help="Enable auto-reload during development."),
) -> None:
    """Launch the local NiceGUI family tree editor and live SVG viewer."""
    start_server(port=port, reload=reload)


@app.command()
def export(
    paper: PaperFormat = typer.Option(PaperFormat.A1, help="Target ISO paper size (A0, A1, A2, AUTO)."),
    orientation: str = typer.Option("landscape", help="landscape or portrait"),
    out_dir: Path = typer.Option(Path("output"), help="Directory to write tree.svg, tree.pdf, and tree.dot"),
) -> None:
    """Compile the SQLite database directly to print-ready SVG, PDF, and DOT files."""
    init_db()
    repo = FamilyRepository()
    snapshot = repo.get_snapshot()

    config = LayoutConfig(paper=paper, orientation=orientation)  # type: ignore[arg-type]
    compiler = TreeCompiler(config)
    paths = compiler.export_files(snapshot, out_dir)

    typer.echo(f"Compiled {len(snapshot.people)} people and {len(snapshot.story_notes)} story boxes:")
    for fmt, path in paths.items():
        typer.echo(f"  - {fmt.upper()}: {path.resolve()}")


@app.command()
def seed() -> None:
    """Populate SQLite with a sample multi-generation tree including an 1800s focus line."""
    init_db()
    repo = FamilyRepository()
    if repo.list_people():
        typer.echo("Database already contains records. Aborting seed.")
        raise typer.Exit(code=1)

    # 1790s Focus Ancestors
    thomas = repo.save_person(
        Person(
            full_name="Thomas Miller",
            birth_year="c. 1794",
            death_year="1868",
            birth_place="Yorkshire, England",
            bio_short="Master stonemason who walked 40 miles to find work on the new canal locks.",
            is_focus_line=True,
        )
    )
    sarah = repo.save_person(
        Person(
            full_name="Sarah Whittaker",
            birth_year="1798",
            death_year="1871",
            is_focus_line=True,
        )
    )
    u_1820 = repo.save_union(Union(partner1_id=thomas.id, partner2_id=sarah.id, marriage_year="1820"))

    repo.save_story_note(
        StoryNote(
            title="The 1832 Parish Ledger",
            body="Parish relief records note Thomas donated timber after the winter flood, the earliest written record of this branch.",
            union_id=u_1820.id,
        )
    )

    # Next Generation (Focus Line + Branch that stops earlier)
    arthur = repo.save_person(
        Person(
            full_name="Arthur Miller",
            birth_year="1824",
            death_year="1899",
            bio_short="Took over the masonry yard and trained three apprentices.",
            is_focus_line=True,
        )
    )
    clara = repo.save_person(
        Person(
            full_name="Clara Vance",
            birth_year="1829",
            death_year="1885",
            bio_short="Parents' lineage unrecorded prior to 1829 census.",
            is_focus_line=False,
        )
    )
    repo.add_child_to_union(u_1820.id, arthur.id, birth_order=1)

    u_1851 = repo.save_union(Union(partner1_id=arthur.id, partner2_id=clara.id, marriage_year="1851"))
    edward = repo.save_person(
        Person(
            full_name="Edward Miller",
            birth_year="1855",
            death_year="1931",
            is_focus_line=True,
        )
    )
    repo.add_child_to_union(u_1851.id, edward.id, birth_order=1)

    typer.echo("Seeded sample genealogy into data/family.db")


if __name__ == "__main__":
    app()