"""Type definitions for Cloudcraft blueprint payloads.

These are intentionally partial — Cloudcraft's schema has 200+ node types and
many service-specific fields. The TypedDicts below document the *shape* that
create_blueprint / update_blueprint expect; callers can freely add extra
service-specific keys on nodes.
"""
from __future__ import annotations

from typing import Any, Literal

# pydantic 2.x refuses to introspect ``typing.TypedDict`` on Python < 3.12 when
# it appears in an MCP tool signature (PydanticUserError "typed-dict-version").
# typing_extensions.TypedDict works on every supported version. typing_extensions
# ships as a pydantic transitive dependency, so it's always available.
from typing_extensions import TypedDict

MapPos = tuple[float, float] | list[float]


class BlueprintNode(TypedDict, total=False):
    """A single AWS resource node in a Cloudcraft blueprint."""

    id: str
    type: str  # e.g. "ec2", "rds", "s3", "elb", "cloudfront", "r53", "user"
    mapPos: MapPos
    region: str
    # Extra service-specific fields are allowed (e.g. instanceType, engine).


# "from" is a Python keyword, so BlueprintEdge uses the functional TypedDict
# syntax to keep the JSON key exact.
BlueprintEdge = TypedDict(
    "BlueprintEdge",
    {
        "id": str,
        "to": str,
        "from": str,
        "type": Literal["edge", "autoedge"],
        "width": int,
        "dashed": bool,
        "endCap": Literal["arrow"],
    },
    total=False,
)


class BlueprintGroup(TypedDict, total=False):
    """A grouping (e.g. Auto Scaling group) around a set of node ids."""

    id: str
    type: str  # "asg", etc.
    nodes: list[str]
    layout: Literal["manual", "even"]
    mapPos: MapPos
    region: str
    mapSize: list[float]


class BlueprintSurface(TypedDict, total=False):
    """Background shape — zone or free-form area."""

    id: str
    type: Literal["zone", "area"]
    mapPos: MapPos
    region: str
    mapSize: list[float]


class BlueprintText(TypedDict, total=False):
    """Isometric text label."""

    id: str
    text: str
    type: Literal["isotext"]
    mapPos: MapPos
    textSize: int
    direction: Literal["up", "down", "left", "right"]
    isometric: str


class BlueprintLiveOptions(TypedDict, total=False):
    autoLabel: bool
    autoConnect: bool
    searchTerms: list[str]
    excludedTypes: list[str]
    updatesEnabled: bool
    updateAllOnScan: bool
    updateGroupsOnScan: bool
    updateNodeOnSelect: bool


class BlueprintData(TypedDict, total=False):
    """Top-level blueprint data payload sent to POST/PUT /blueprint."""

    name: str
    grid: Literal["infinite"] | str
    projection: Literal["isometric", "2d"]
    theme: dict[str, Any]
    version: int
    nodes: list[BlueprintNode]
    edges: list[BlueprintEdge]
    groups: list[BlueprintGroup]
    surfaces: list[BlueprintSurface]
    text: list[BlueprintText]
    icons: list[dict[str, Any]]
    connectors: list[dict[str, Any]]
    images: list[dict[str, Any]]
    disabledLayers: list[str]
    shareDocs: bool
    liveOptions: BlueprintLiveOptions
