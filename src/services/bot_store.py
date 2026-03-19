import json
from pathlib import Path
from typing import List, Optional

from src.models.bot import Bot


class BotStore:
    def __init__(self):
        self.data_dir = Path.home() / ".local" / "share" / "6x-protocol-studio"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.data_dir / "bots.json"

    def load_bots(self) -> List[Bot]:
        if not self.file_path.exists():
            return []

        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return [Bot.from_dict(item) for item in data]
        except Exception:
            return []

    def save_bots(self, bots: List[Bot]) -> None:
        data = [bot.to_dict() for bot in bots]
        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)

    def get_bot_by_id(self, bot_id: str) -> Optional[Bot]:
        bots = self.load_bots()
        for bot in bots:
            if bot.id == bot_id:
                return bot
        return None

    def get_bot_by_name(self, name: str) -> Optional[Bot]:
        target = name.strip().lower()
        if not target:
            return None

        bots = self.load_bots()
        for bot in bots:
            if bot.name.strip().lower() == target:
                return bot
        return None
