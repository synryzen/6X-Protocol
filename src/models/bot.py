from dataclasses import dataclass, asdict
from typing import Dict


@dataclass
class Bot:
    id: str
    name: str
    role: str
    provider: str
    model: str
    temperature: str = ""
    max_tokens: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict) -> "Bot":
        return Bot(
            id=data.get("id", ""),
            name=data.get("name", ""),
            role=data.get("role", ""),
            provider=data.get("provider", ""),
            model=data.get("model", ""),
            temperature=str(data.get("temperature", "")).strip(),
            max_tokens=str(data.get("max_tokens", "")).strip(),
        )
