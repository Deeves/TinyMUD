from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class FactionRole:
    """A functional role within a faction (e.g., 'Miner', 'Guard').
    
    Roles are distinct from Ranks. A Rank (Captain) denotes status/command.
    A Role (Guard) denotes the job/duty the member performs daily.
    """
    id: str  # Unique identifier (e.g., 'mining_corp_miner')
    name: str # Display name (e.g., "Miner")
    description: str
    
    # Contract Configuration
    # type: e.g., 'resource_contribution', 'patrol', 'crafting', 'combat'
    contract_type: str = "generic"
    
    # config: parameters for generating the daily mission
    # e.g., {'resource_tag': 'ore', 'amount': 5, 'reward_rep': 10}
    contract_config: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "contract_type": self.contract_type,
            "contract_config": self.contract_config
        }

    @staticmethod
    def from_dict(data: dict) -> "FactionRole":
        return FactionRole(
            id=data.get("id", ""),
            name=data.get("name", "Unnamed Role"),
            description=data.get("description", ""),
            contract_type=data.get("contract_type", "generic"),
            contract_config=data.get("contract_config", {})
        )
