from dataclasses import dataclass, asdict, field
from typing import Any, Dict


@dataclass
class Workflow:
    id: str
    name: str
    trigger: str
    action: str
    graph: Dict[str, Any] = field(default_factory=lambda: {"version": 1, "nodes": [], "edges": []})

    def to_dict(self) -> Dict:
        data = asdict(self)
        data["graph"] = self.normalized_graph()
        return data

    def normalized_graph(self) -> Dict[str, Any]:
        graph = self.graph if isinstance(self.graph, dict) else {}

        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        version = graph.get("version", 1)
        settings = graph.get("settings", {})

        if not isinstance(nodes, list):
            nodes = []
        if not isinstance(edges, list):
            edges = []
        if not isinstance(settings, dict):
            settings = {}

        return {
            "version": int(version) if isinstance(version, int) else 1,
            "nodes": nodes,
            "edges": edges,
            "settings": settings,
        }

    @staticmethod
    def from_dict(data: Dict) -> "Workflow":
        return Workflow(
            id=data.get("id", ""),
            name=data.get("name", ""),
            trigger=data.get("trigger", ""),
            action=data.get("action", ""),
            graph=data.get("graph", {"version": 1, "nodes": [], "edges": []}),
        )
