"""Issue #22: blueprint TypedDicts must let service-specific keys through.

pydantic validates MCP tool arguments against these TypedDicts and, by
default, silently drops every key that is not declared. Cloudcraft nodes carry
hundreds of service-specific fields (``instanceType``, ``nodes`` for
containment, ``color`` ...), so the types must opt into ``extra="allow"``.
"""
from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from cloudcraft_mcp import types


@pytest.mark.unit
@pytest.mark.parametrize(
    "typed_dict",
    [
        types.BlueprintNode,
        types.BlueprintEdge,
        types.BlueprintGroup,
        types.BlueprintSurface,
        types.BlueprintText,
        types.BlueprintLiveOptions,
        types.BlueprintData,
    ],
)
def test_undeclared_keys_survive_validation(typed_dict: type) -> None:
    validated = TypeAdapter(typed_dict).validate_python({"serviceSpecific": {"x": 1}})
    assert validated["serviceSpecific"] == {"x": 1}


@pytest.mark.unit
def test_nested_container_fields_survive_validation() -> None:
    node = {
        "type": "subnet",
        "id": "s1",
        "region": "us-east-1",
        "name": "private-1a",
        "shape": "dynamic",
        "padding": 1.5,
        "nodes": ["n1"],
    }
    data = TypeAdapter(types.BlueprintData).validate_python({"nodes": [node]})
    assert data["nodes"][0] == node
