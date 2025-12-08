from typing import List, Dict, Any, Optional
import uuid

class Milestone:
    def __init__(self, description: str, target_type: str, target_value: Any, completed: bool = False):
        self.description = description
        self.target_type = target_type # e.g., 'currency', 'item', 'stat', 'relationship'
        self.target_value = target_value
        self.completed = completed

    def to_dict(self) -> Dict:
        return {
            'description': self.description,
            'target_type': self.target_type,
            'target_value': self.target_value,
            'completed': self.completed
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Milestone':
        return cls(
            description=data.get('description', ''),
            target_type=data.get('target_type', ''),
            target_value=data.get('target_value'),
            completed=data.get('completed', False)
        )

class Ambition:
    def __init__(self, name: str, description: str, milestones: List[Milestone]):
        self.id = str(uuid.uuid4())
        self.name = name
        self.description = description
        self.milestones = milestones
        self.current_milestone_idx = 0
        self.is_completed = False

    def get_current_milestone(self) -> Optional[Milestone]:
        if self.is_completed or self.current_milestone_idx >= len(self.milestones):
            return None
        return self.milestones[self.current_milestone_idx]

    def advance_milestone(self):
        if self.current_milestone_idx < len(self.milestones):
            self.milestones[self.current_milestone_idx].completed = True
            self.current_milestone_idx += 1
            if self.current_milestone_idx >= len(self.milestones):
                self.is_completed = True

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'milestones': [m.to_dict() for m in self.milestones],
            'current_milestone_idx': self.current_milestone_idx,
            'is_completed': self.is_completed
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Ambition':
        ambition = cls(
            name=data.get('name', ''),
            description=data.get('description', ''),
            milestones=[Milestone.from_dict(m) for m in data.get('milestones', [])]
        )
        ambition.id = data.get('id', str(uuid.uuid4()))
        ambition.current_milestone_idx = data.get('current_milestone_idx', 0)
        ambition.is_completed = data.get('is_completed', False)
        return ambition
