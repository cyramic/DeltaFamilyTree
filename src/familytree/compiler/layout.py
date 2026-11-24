from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class PaperFormat(str, Enum):
    """ISO 216 paper sizes (1 : sqrt(2) aspect ratio)."""

    AUTO = "AUTO"  # Unconstrained bounding box for quick previewing
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"


_ISO_PORTRAIT_INCHES: dict[PaperFormat, tuple[float, float]] = {
    PaperFormat.A0: (33.11, 46.81),
    PaperFormat.A1: (23.39, 33.11),
    PaperFormat.A2: (16.54, 23.39),
}


class ThemePalette(BaseModel):
    """Color and typography tokens passed to Graphviz attributes and HTML templates."""

    font_family: str = "Helvetica, Arial, sans-serif"
    background_color: str = "#FAF8F5"

    card_bg: str = "#FFFFFF"
    card_border: str = "#8C7A6B"
    card_header_bg: str = "#EFECE6"
    text_primary: str = "#2B2623"
    text_muted: str = "#6E655F"

    focus_card_bg: str = "#FDFBF7"
    focus_card_border: str = "#2E5A44"
    focus_header_bg: str = "#E3EDE8"

    note_bg: str = "#FFFDF2"
    note_border: str = "#C29B40"
    note_header_bg: str = "#F7EED3"

    lineage_edge_color: str = "#5C534C"
    focus_edge_color: str = "#2E5A44"
    note_edge_color: str = "#B08D3B"


class LayoutConfig(BaseModel):
    """Controls Graphviz global layout, paper aspect ratio, and spacing."""

    paper: PaperFormat = PaperFormat.AUTO
    orientation: Literal["landscape", "portrait"] = "landscape"
    rankdir: Literal["LR", "TB"] = "LR"
    splines: Literal["ortho", "polyline", "spline"] = "polyline"

    ranksep: float = Field(default=0.85, ge=0.2, le=4.0)
    nodesep: float = Field(default=0.35, ge=0.1, le=2.0)

    ratio_mode: Literal["compress", "fill", "auto"] = "compress"
    margin_inches: float = Field(default=0.5, ge=0.0, le=2.0)

    theme: ThemePalette = Field(default_factory=ThemePalette)

    @property
    def target_dimensions_inches(self) -> tuple[float, float] | None:
        if self.paper == PaperFormat.AUTO:
            return None

        short_side, long_side = _ISO_PORTRAIT_INCHES[self.paper]
        if self.orientation == "landscape":
            return (long_side, short_side)
        return (short_side, long_side)

    def to_graph_attrs(self) -> dict[str, str]:
        attrs: dict[str, str] = {
            "rankdir": self.rankdir,
            "splines": self.splines,
            "ranksep": str(self.ranksep),
            "nodesep": str(self.nodesep),
            "bgcolor": self.theme.background_color,
            "fontname": self.theme.font_family,
            "margin": str(self.margin_inches),
            "compound": "true",
            "overlap": "false",
            "ordering": "out",
        }

        dims = self.target_dimensions_inches
        if dims is not None:
            width, height = dims
            attrs["size"] = f"{width:.2f},{height:.2f}!"
            if self.ratio_mode != "auto":
                attrs["ratio"] = self.ratio_mode

        return attrs

    def to_default_node_attrs(self) -> dict[str, str]:
        return {
            "shape": "plain",
            "fontname": self.theme.font_family,
            "fontsize": "11",
        }

    def to_default_edge_attrs(self) -> dict[str, str]:
        return {
            "color": self.theme.lineage_edge_color,
            "penwidth": "1.3",
            "arrowhead": "none",
        }