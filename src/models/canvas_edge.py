from dataclasses import dataclass, asdict
from typing import Dict


@dataclass
class CanvasEdge:
    id: str
    source_node_id: str
    target_node_id: str
    condition: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict) -> "CanvasEdge":
        return CanvasEdge(
            id=data.get("id", ""),
            source_node_id=data.get("source_node_id", ""),
            target_node_id=data.get("target_node_id", ""),
            condition=str(data.get("condition", "")).strip().lower(),
        )
