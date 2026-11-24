"""Pydantic DSL schema for deterministic Logo Modernism specifications."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

Point2D = tuple[float, float]


class GridSpec(BaseModel):
    type: Literal["square", "isometric", "polar"] = "square"
    divisions: int = Field(default=8, ge=2, le=32)


class SymmetrySpec(BaseModel):
    type: Literal[
        "none",
        "mirror_x",
        "mirror_y",
        "mirror_xy",
        "rotate",
        "glide_x",
    ] = "none"
    count: int = Field(default=4, ge=2, le=36)
    step_deg: float | None = None
    scale_step: float = Field(default=1.0, gt=0.1, le=2.0)
    offset: float = 0.0


class GridPathShape(BaseModel):
    type: Literal["grid_path"]
    points: list[Point2D] = Field(min_length=2)
    closed: bool = False
    width: float = Field(default=1.0, ge=0.0)
    corner_radius: float = Field(default=0.0, ge=0.0)
    cap: Literal["butt", "round", "square"] = "butt"
    join: Literal["miter", "round", "bevel"] = "miter"


class ArcBandShape(BaseModel):
    type: Literal["arc_band"]
    center: Point2D = (0.0, 0.0)
    radius: float = Field(gt=0.0)
    start_deg: float
    end_deg: float
    width: float = Field(default=1.0, gt=0.0)
    fill_sector: bool = False
    cap: Literal["butt", "round", "square"] = "butt"


class CircleShape(BaseModel):
    type: Literal["circle"]
    center: Point2D = (0.0, 0.0)
    radius: float = Field(gt=0.0)


class RingShape(BaseModel):
    type: Literal["ring"]
    center: Point2D = (0.0, 0.0)
    outer_radius: float = Field(gt=0.0)
    inner_radius: float = Field(gt=0.0)


class RectShape(BaseModel):
    type: Literal["rect"]
    center: Point2D = (0.0, 0.0)
    width: float = Field(gt=0.0)
    height: float = Field(gt=0.0)
    corner_radius: float = Field(default=0.0, ge=0.0)
    angle_deg: float = 0.0


class PolygonShape(BaseModel):
    type: Literal["polygon"]
    center: Point2D = (0.0, 0.0)
    sides: int = Field(ge=3, le=32)
    radius: float = Field(gt=0.0)
    angle_deg: float = 0.0
    corner_radius: float = Field(default=0.0, ge=0.0)


class LineScreenShape(BaseModel):
    type: Literal["line_screen"]
    center: Point2D = (0.0, 0.0)
    angle_deg: float = 0.0
    count: int = Field(default=11, ge=2, le=80)
    pitch: float = Field(default=0.6, gt=0.05)
    length: float = Field(default=12.0, gt=0.1)
    min_width: float = Field(default=0.12, gt=0.01)
    max_width: float = Field(default=0.48, gt=0.01)
    profile: Literal[
        "constant",
        "linear",
        "center_bulge",
        "center_pinch",
        "sine",
        "exponential",
    ] = "linear"
    phase: float = 0.0
    wave_cycles: float = Field(default=1.0, gt=0.0)
    invert_profile: bool = False


class RadialBladesShape(BaseModel):
    type: Literal["radial_blades"]
    center: Point2D = (0.0, 0.0)
    count: int = Field(default=6, ge=2, le=36)
    inner_radius: float = Field(default=0.6, gt=0.0)
    outer_radius: float = Field(default=3.5, gt=0.1)
    angle_deg: float = 0.0
    twist_deg: float = 35.0
    inner_width_deg: float = Field(default=28.0, gt=1.0, lt=180.0)
    outer_width_deg: float = Field(default=16.0, gt=1.0, lt=180.0)
    curve_bias: float = Field(default=0.55, ge=0.1, le=0.95)


class HalftoneGridShape(BaseModel):
    type: Literal["halftone_grid"]
    center: Point2D = (0.0, 0.0)
    cols: int = Field(default=7, ge=2, le=25)
    rows: int = Field(default=7, ge=2, le=25)
    pitch: float = Field(default=0.8, gt=0.1)
    shape: Literal["circle", "square", "diamond"] = "circle"
    min_size: float = Field(default=0.14, gt=0.01)
    max_size: float = Field(default=0.72, gt=0.01)
    field: Literal[
        "radial_decay",
        "radial_grow",
        "linear_x",
        "linear_y",
        "diagonal",
        "sine_ripple",
    ] = "radial_decay"


ShapeSpec = Annotated[
    Union[
        GridPathShape,
        ArcBandShape,
        CircleShape,
        RingShape,
        RectShape,
        PolygonShape,
        LineScreenShape,
        RadialBladesShape,
        HalftoneGridShape,
    ],
    Field(discriminator="type"),
]


class LayerSpec(BaseModel):
    id: str
    op: Literal["unite", "subtract", "intersect", "xor"] = "unite"
    halo: float = Field(default=0.0, ge=0.0)
    shapes: list[ShapeSpec] = Field(min_length=1)
    clip_to: list[ShapeSpec] | None = None
    symmetry: SymmetrySpec | None = None


class PostProcessSpec(BaseModel):
    canvas_size: int = Field(default=1000, ge=256, le=4096)
    padding: float = Field(default=100.0, ge=0.0)
    optical_center: bool = True
    invert: bool = False
    precision: int = Field(default=2, ge=0, le=5)


class LogoSpec(BaseModel):
    schemaVersion: Literal[1] = 1
    name: str
    concept: str
    category: Literal["geometric", "effect", "monogram"] = "geometric"
    unit: float = Field(default=40.0, gt=1.0)
    grid: GridSpec = Field(default_factory=GridSpec)
    layers: list[LayerSpec] = Field(min_length=1)
    symmetry: SymmetrySpec | None = None
    post: PostProcessSpec = Field(default_factory=PostProcessSpec)
