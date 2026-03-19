import json
from pathlib import Path
from typing import Dict, List, Optional

from src.models.workflow import Workflow


class WorkflowStore:
    def __init__(self):
        self.data_dir = Path.home() / ".local" / "share" / "6x-protocol-studio"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.data_dir / "workflows.json"

    def load_workflows(self) -> List[Workflow]:
        if not self.file_path.exists():
            return []

        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return [Workflow.from_dict(item) for item in data]
        except Exception:
            return []

    def save_workflows(self, workflows: List[Workflow]) -> None:
        data = [workflow.to_dict() for workflow in workflows]
        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)

    def get_workflow_by_id(self, workflow_id: str) -> Optional[Workflow]:
        workflows = self.load_workflows()
        for workflow in workflows:
            if workflow.id == workflow_id:
                return workflow
        return None

    def update_workflow(self, workflow_id: str, updates: Dict) -> bool:
        workflows = self.load_workflows()
        updated = False

        for index, workflow in enumerate(workflows):
            if workflow.id != workflow_id:
                continue

            workflow_data = workflow.to_dict()
            workflow_data.update(updates)
            workflows[index] = Workflow.from_dict(workflow_data)
            updated = True
            break

        if updated:
            self.save_workflows(workflows)

        return updated

    def update_workflow_graph(self, workflow_id: str, graph: Dict) -> bool:
        return self.update_workflow(workflow_id, {"graph": graph})
