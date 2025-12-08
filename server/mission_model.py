from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Any
import uuid
import time

class MissionStatus(Enum):
    PENDING = "pending"   # Offered but not accepted
    ACTIVE = "active"     # Accepted and in progress
    COMPLETED = "completed" # Objectives met
    FAILED = "failed"     # Deadline passed or failed condition met
    EXPIRED = "expired"   # Offer expired before acceptance

@dataclass
class Objective:
    """Base class for mission objectives."""
    description: str
    target_id: Optional[str] = None
    target_count: int = 1
    current_count: int = 0
    completed: bool = False
    type: str = "generic"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "description": self.description,
            "target_id": self.target_id,
            "target_count": self.target_count,
            "current_count": self.current_count,
            "completed": self.completed
        }

    @staticmethod
    def from_dict(data: dict) -> "Objective":
        obj_type = data.get("type", "generic")
        
        # Helper to filter dict keys to match dataclass fields
        valid_keys = {"description", "target_id", "target_count", "current_count", "completed", "type"}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        
        if obj_type == "kill":
            return KillObjective(**filtered_data)
        elif obj_type == "obtain":
            return ObtainItemObjective(**filtered_data)
        elif obj_type == "visit":
            return VisitRoomObjective(**filtered_data)
        return Objective(**filtered_data)

@dataclass
class KillObjective(Objective):
    type: str = "kill"

@dataclass
class ObtainItemObjective(Objective):
    type: str = "obtain"

@dataclass
class VisitRoomObjective(Objective):
    type: str = "visit"

@dataclass
class Mission:
    title: str
    description: str
    issuer_id: str  # UUID of NPC or Player who created it
    assignee_id: Optional[str] = None # UUID of Player/NPC who accepted it
    
    # Rewards
    reward_currency: int = 0
    reward_xp: int = 0
    reward_items: List[str] = field(default_factory=list) # List of item UUIDs or template keys
    reward_faction_id: Optional[str] = None
    reward_faction_rep: int = 0

    # Constraints
    deadline: Optional[float] = None # Timestamp
    min_faction_rank: Optional[str] = None
    faction_id: Optional[str] = None # If this is a faction mission

    # State
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: MissionStatus = MissionStatus.PENDING
    objectives: List[Objective] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "uuid": self.uuid,
            "title": self.title,
            "description": self.description,
            "issuer_id": self.issuer_id,
            "assignee_id": self.assignee_id,
            "reward_currency": self.reward_currency,
            "reward_xp": self.reward_xp,
            "reward_items": self.reward_items,
            "reward_faction_id": self.reward_faction_id,
            "reward_faction_rep": self.reward_faction_rep,
            "deadline": self.deadline,
            "min_faction_rank": self.min_faction_rank,
            "faction_id": self.faction_id,
            "status": self.status.value,
            "objectives": [o.to_dict() for o in self.objectives],
            "created_at": self.created_at
        }

    @staticmethod
    def from_dict(data: dict) -> "Mission":
        m = Mission(
            title=data.get("title", "Untitled Mission"),
            description=data.get("description", ""),
            issuer_id=data.get("issuer_id", ""),
            assignee_id=data.get("assignee_id"),
            reward_currency=data.get("reward_currency", 0),
            reward_xp=data.get("reward_xp", 0),
            reward_items=data.get("reward_items", []),
            reward_faction_id=data.get("reward_faction_id"),
            reward_faction_rep=data.get("reward_faction_rep", 0),
            deadline=data.get("deadline"),
            min_faction_rank=data.get("min_faction_rank"),
            faction_id=data.get("faction_id"),
            uuid=data.get("uuid", str(uuid.uuid4())),
            created_at=data.get("created_at", time.time())
        )
        
        status_val = data.get("status", "pending")
        try:
            m.status = MissionStatus(status_val)
        except ValueError:
            m.status = MissionStatus.PENDING
            
        objs = data.get("objectives", [])
        m.objectives = [Objective.from_dict(o) for o in objs]
        
        return m
