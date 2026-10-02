"""BFS depth barriers keep shortest discovery depth independent of timing."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Resource


@dataclass
class FrontierItem:
    url: str  # private execution URL, never serialized/logged
    resource: Resource


class Frontier:
    def __init__(self) -> None:
        self.levels: dict[int, list[FrontierItem]] = {}

    def push(self, item: FrontierItem) -> None:
        self.levels.setdefault(item.resource.depth, []).append(item)

    def pop_level(self) -> list[FrontierItem]:
        if not self.levels:
            return []
        return sorted(self.levels.pop(min(self.levels)), key=lambda item: item.url)
