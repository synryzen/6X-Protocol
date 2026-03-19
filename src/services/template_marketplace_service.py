import json
import shutil
from pathlib import Path
from typing import Dict, List, Tuple


class TemplateMarketplaceService:
    def __init__(self):
        self.data_dir = Path.home() / ".local" / "share" / "6x-protocol-studio"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.packs_dir = self.data_dir / "template-packs"
        self.packs_dir.mkdir(parents=True, exist_ok=True)

    def list_packs(self) -> List[Dict]:
        packs = [*self._builtin_packs(), *self._load_external_packs()]
        return sorted(packs, key=lambda pack: str(pack.get("name", "")).lower())

    def list_templates(self) -> List[Dict]:
        templates: List[Dict] = []

        for pack in self.list_packs():
            pack_id = str(pack.get("pack_id", "")).strip() or "unknown-pack"
            pack_name = str(pack.get("name", "")).strip() or "Unnamed Pack"

            for template in pack.get("templates", []):
                if not isinstance(template, dict):
                    continue

                template_id = str(template.get("template_id", "")).strip()
                name = str(template.get("name", "")).strip()
                node_type = str(template.get("node_type", "")).strip()
                if not template_id or not name or not node_type:
                    continue

                templates.append(
                    {
                        "pack_id": pack_id,
                        "pack_name": pack_name,
                        "template_id": template_id,
                        "name": name,
                        "node_type": node_type,
                        "summary": str(template.get("summary", "")).strip(),
                        "detail": str(template.get("detail", "")).strip(),
                        "config": template.get("config", {}),
                    }
                )

        return sorted(templates, key=lambda item: item["name"].lower())

    def install_pack_from_file(self, source_path: str) -> Tuple[bool, str]:
        candidate = Path(source_path).expanduser()
        if not candidate.exists() or not candidate.is_file():
            return False, "Template pack file was not found."

        try:
            with open(candidate, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as error:
            return False, f"Failed to read template pack JSON: {error}"

        if not isinstance(data, dict):
            return False, "Pack JSON must be an object."

        template_items = data.get("templates", [])
        if not isinstance(template_items, list) or not template_items:
            return False, "Template pack must include a non-empty 'templates' list."

        for item in template_items:
            if not isinstance(item, dict):
                return False, "Each template must be an object."
            template_id = str(item.get("template_id", "")).strip()
            name = str(item.get("name", "")).strip()
            node_type = str(item.get("node_type", "")).strip()
            if not template_id or not name or not node_type:
                return False, "Each template must include 'template_id', 'name', and 'node_type'."

        destination = self.packs_dir / candidate.name
        try:
            shutil.copy2(candidate, destination)
        except Exception as error:
            return False, f"Failed to copy template pack file: {error}"

        return True, f"Installed template pack: {candidate.name}"

    def _load_external_packs(self) -> List[Dict]:
        packs: List[Dict] = []

        for file_path in sorted(self.packs_dir.glob("*.json")):
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                if isinstance(data, dict):
                    packs.append(data)
            except Exception:
                continue

        return packs

    def _builtin_packs(self) -> List[Dict]:
        return [
            {
                "pack_id": "starter-local",
                "name": "Starter Local Pack",
                "templates": [
                    {
                        "template_id": "trigger-interval-60",
                        "name": "Interval Trigger (60s)",
                        "node_type": "Trigger",
                        "summary": "Runs workflow every 60 seconds in daemon mode.",
                        "detail": "interval:60",
                        "config": {"interval_seconds": "60"},
                    },
                    {
                        "template_id": "ai-summarizer",
                        "name": "AI Summarizer",
                        "node_type": "AI Node",
                        "summary": "Summarizes incoming context.",
                        "detail": "prompt: Summarize the incoming context with concise bullet points.",
                        "config": {"provider": "inherit"},
                    },
                    {
                        "template_id": "condition-success",
                        "name": "Condition Contains Success",
                        "node_type": "Condition",
                        "summary": "Routes flow when previous output contains success.",
                        "detail": "contains:success",
                        "config": {"expression": "contains:success"},
                    },
                    {
                        "template_id": "action-http-post",
                        "name": "Action HTTP POST",
                        "node_type": "Action",
                        "summary": "Sends payload to external endpoint.",
                        "detail": "integration:http_post\nurl:https://example.com/webhook\npayload:{\"text\":\"hello\"}",
                        "config": {"integration": "http_post"},
                    },
                    {
                        "template_id": "action-file-log",
                        "name": "Action File Append Log",
                        "node_type": "Action",
                        "summary": "Appends output to local log file.",
                        "detail": "integration:file_append\npath:~/6x-protocol/logs/automation.log",
                        "config": {"integration": "file_append"},
                    },
                    {
                        "template_id": "action-bot-handoff",
                        "name": "Action Bot Handoff",
                        "node_type": "Action",
                        "summary": "Passes output through a bot chain.",
                        "detail": "integration:handoff\nbot_chain: Planner > Reviewer",
                        "config": {"integration": "handoff", "bot_chain": "Planner > Reviewer"},
                    },
                ],
            }
        ]
