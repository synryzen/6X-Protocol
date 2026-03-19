from dataclasses import dataclass, asdict, field
from typing import Dict


@dataclass
class CanvasNode:
    id: str
    name: str
    node_type: str
    detail: str
    summary: str
    x: int
    y: int
    config: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict) -> "CanvasNode":
        raw_config = data.get("config", {})
        if not isinstance(raw_config, dict):
            raw_config = {}

        return CanvasNode(
            id=data.get("id", ""),
            name=data.get("name", ""),
            node_type=data.get("node_type", ""),
            detail=data.get("detail", ""),
            summary=data.get("summary", ""),
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            config={str(k): str(v) for k, v in raw_config.items()},
        )
