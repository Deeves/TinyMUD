"""World model for the TinyMUD (very small and in-memory).

Concepts:
- Controlled Character: A character controlled by a User connected via Socket.IO (identified by a session id `sid`).
- Character: a character sheet with a display name, description, and inventory that is controlled by AI.
- Object: an item with a name, description, material type, and interaction tags (e.g., "one-hand", "two-hand").
- Inventory: 8 slots with constraints on what items can be stored where.
- World: serves as the main container for all game entities and logic.
- Room: a place with a description, that holds objects, entrances, exits, and characters.
- User: a persisted account with a character sheet (login name, password, description).
- World: contains all rooms and players and a few helper methods to move/describe.

This is intentionally tiny so beginners can add rooms and NPC names easily.
"""

from dataclasses import dataclass, field
import json
import os
import uuid
from typing import Dict, Set, Optional, List


@dataclass
class Item:
    name: str
    tags: Set[str] = field(default_factory=set)  # e.g., {"one-hand"} or {"two-hand"}

    def to_dict(self) -> dict:
        return {"name": self.name, "tags": sorted(list(self.tags))}

    @staticmethod
    def from_dict(data: dict) -> "Item":
        return Item(name=data.get("name", "Unnamed"), tags=set(data.get("tags", [])))


@dataclass
class Inventory:
    """8 slot inventory with constraints:
    - slot 0: left hand
    - slot 1: right hand
    - slots 2-5: four small items (must have 'one-hand')
    - slots 6-7: two large items (must have 'two-hand')
    """

    slots: List[Optional[Item]] = field(default_factory=lambda: [None] * 8)

    def can_place(self, index: int, item: Item) -> bool:
        if index < 0 or index >= 8:
            return False
        if index in (0, 1):
            # hands can hold either one-hand or two-hand items (conceptually one hand carrying a two-hand object is allowed here for simplicity)
            return True
        if 2 <= index <= 5:
            return 'one-hand' in item.tags and 'two-hand' not in item.tags
        if 6 <= index <= 7:
            return 'two-hand' in item.tags
        return False

    def place(self, index: int, item: Item) -> bool:
        if not self.can_place(index, item):
            return False
        self.slots[index] = item
        return True

    def remove(self, index: int) -> Optional[Item]:
        if index < 0 or index >= 8:
            return None
        it = self.slots[index]
        self.slots[index] = None
        return it

    def describe(self) -> str:
        names = []
        labels = [
            "Left Hand", "Right Hand",
            "Small Slot 1", "Small Slot 2", "Small Slot 3", "Small Slot 4",
            "Large Slot 1", "Large Slot 2",
        ]
        for idx, label in enumerate(labels):
            item = self.slots[idx]
            names.append(f"{label}: {item.name if item else '[empty]'}")
        return "\n".join(names)

    def to_dict(self) -> dict:
        return {
            "slots": [s.to_dict() if s else None for s in self.slots]
        }

    @staticmethod
    def from_dict(data: dict) -> "Inventory":
        inv = Inventory()
        slots = data.get("slots")
        if isinstance(slots, list):
            inv.slots = [Item.from_dict(s) if isinstance(s, dict) else None for s in slots][:8]
            # Ensure exactly 8 slots
            if len(inv.slots) < 8:
                inv.slots.extend([None] * (8 - len(inv.slots)))
        return inv


@dataclass
class CharacterSheet:
    display_name: str
    description: str = "A nondescript adventurer."
    inventory: Inventory = field(default_factory=Inventory)

    def to_dict(self) -> dict:
        return {
            "display_name": self.display_name,
            "description": self.description,
            "inventory": self.inventory.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict) -> "CharacterSheet":
        return CharacterSheet(
            display_name=data.get("display_name", "Unnamed"),
            description=data.get("description", "A nondescript adventurer."),
            inventory=Inventory.from_dict(data.get("inventory", {})),
        )


@dataclass
class Player:
    sid: str
    room_id: str
    sheet: CharacterSheet
    # Stable game-entity id (distinct from volatile websocket sid)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class User:
    """A persisted user account with a character sheet.

    For simplicity, passwords are stored in plaintext as requested.
    The display_name also serves as the login name and must be unique.
    """
    user_id: str
    display_name: str
    password: str
    description: str = "A nondescript adventurer."
    sheet: CharacterSheet = field(default_factory=lambda: CharacterSheet(display_name="Unnamed"))
    is_admin: bool = False

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "password": self.password,
            "description": self.description,
            "sheet": self.sheet.to_dict(),
            "is_admin": self.is_admin,
        }

    @staticmethod
    def from_dict(data: dict) -> "User":
        return User(
            user_id=data.get("user_id", str(uuid.uuid4())),
            display_name=data.get("display_name", "Unnamed"),
            password=data.get("password", ""),
            description=data.get("description", "A nondescript adventurer."),
            sheet=CharacterSheet.from_dict(data.get("sheet", {"display_name": data.get("display_name", "Unnamed")})),
            is_admin=bool(data.get("is_admin", False)),
        )


@dataclass
class Room:
    id: str
    description: str
    players: Set[str] = field(default_factory=set)  # set of player sids
    npcs: Set[str] = field(default_factory=set)     # set of npc names
    # Doors are named connectors within a room that lead to another room id.
    # NOTE: In code and persistence we use stable room ids (machine identifiers).
    # Players type human-readable room names (fuzzy matched) which we resolve to these ids.
    # key: door name shown to players (e.g., "oak door", "north door"). value: target room id
    doors: Dict[str, str] = field(default_factory=dict)
    # Stairs: support up/down links separately (either may be absent)
    stairs_up_to: Optional[str] = None
    stairs_down_to: Optional[str] = None
    # New: stable UUID for the room entity
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    # New: stable UUIDs for door objects, keyed by door name
    door_ids: Dict[str, str] = field(default_factory=dict)
    # New: stable identifiers for stairs objects (if present)
    stairs_up_id: Optional[str] = None
    stairs_down_id: Optional[str] = None
    # New: optional door lock policies per door name
    # Schema: { door_name: { 'allow_ids': [entity_id,...], 'allow_rel': [ {'type': str, 'to': entity_id} ] } }
    door_locks: Dict[str, dict] = field(default_factory=dict)

    def describe(self, world: "World", viewer_sid: str | None = None) -> str:
        """Return a short multi-line description for a player to read.

        Includes the room description, any visible NPC names, and other players present.
        """
        lines = [self.description.strip()]

        # NPCs
        if self.npcs:
            lines.append("NPCs here: " + ", ".join(sorted(self.npcs)))

        # Other players (exclude the viewer)
        others = [p_sid for p_sid in self.players if p_sid != viewer_sid]
        if others:
            names = [world.players[p].sheet.display_name for p in others if p in world.players]
            if names:
                lines.append("Also present: " + ", ".join(sorted(names)))

        # Exits (doors and stairs)
        exit_bits: List[str] = []
        if self.doors:
            # Show door names
            exit_bits.append("doors: " + ", ".join(sorted(self.doors.keys())))
        if self.stairs_up_to:
            exit_bits.append("stairs up")
        if self.stairs_down_to:
            exit_bits.append("stairs down")
        if exit_bits:
            lines.append("Exits: " + "; ".join(exit_bits))

        return "\n".join(lines)

    def to_dict(self) -> dict:
        # Persist core room data; skip live player SIDs
        return {
            "id": self.id,
            "description": self.description,
            "npcs": sorted(list(self.npcs)),
            "doors": self.doors,
            "stairs_up_to": self.stairs_up_to,
            "stairs_down_to": self.stairs_down_to,
            # New fields for stable identifiers
            "uuid": self.uuid,
            "door_ids": self.door_ids,
            "stairs_up_id": self.stairs_up_id,
            "stairs_down_id": self.stairs_down_id,
            # Door locks
            "door_locks": self.door_locks,
        }

    @staticmethod
    def from_dict(data: dict) -> "Room":
        # Load base fields
        room = Room(
            id=data.get("id", "unknown"),
            description=data.get("description", ""),
            players=set(),
            npcs=set(data.get("npcs", [])),
            doors=dict(data.get("doors", {})),
            stairs_up_to=data.get("stairs_up_to"),
            stairs_down_to=data.get("stairs_down_to"),
            uuid=data.get("uuid", str(uuid.uuid4())),
            door_ids=dict(data.get("door_ids", {})),
            stairs_up_id=data.get("stairs_up_id"),
            stairs_down_id=data.get("stairs_down_id"),
            door_locks=dict(data.get("door_locks", {})),
        )
        # Backfill missing door IDs for existing door names
        for dname in list(room.doors.keys()):
            if dname not in room.door_ids:
                room.door_ids[dname] = str(uuid.uuid4())
        # Backfill stairs IDs when targets are set but ids missing
        if room.stairs_up_to and not room.stairs_up_id:
            room.stairs_up_id = str(uuid.uuid4())
        if room.stairs_down_to and not room.stairs_down_id:
            room.stairs_down_id = str(uuid.uuid4())
        return room


class World:
    def __init__(self) -> None:
        self.rooms: Dict[str, Room] = {}
        self.players: Dict[str, Player] = {}
        # Simple NPC sheets by name (if needed later)
        self.npc_sheets: Dict[str, CharacterSheet] = {}
        # Persisted user accounts
        self.users: Dict[str, User] = {}
        # New: Global mapping of NPC display name -> stable UUID
        # Names are globally unique in this simple world; ids provide stability.
        self.npc_ids: Dict[str, str] = {}
        # World metadata configured by the first admin via setup wizard
        self.world_name: Optional[str] = None
        self.world_description: Optional[str] = None
        self.world_conflict: Optional[str] = None
        # Starting room id for new players (set by setup wizard)
        # User-facing commands accept a "room name" which is fuzzy-resolved to this id.
        self.start_room_id: Optional[str] = None
        # Once the first admin finishes setup
        self.setup_complete: bool = False
        # Content safety level for AI replies: 'G' | 'PG-13' | 'R' | 'OFF'
        self.safety_level: str = 'G'
        # Relationship graph (directed): entity_id -> { target_entity_id: relationship_type }
        # entity_id is user.user_id for players and world.get_or_create_npc_id(name) for NPCs
        self.relationships: Dict[str, Dict[str, str]] = {}

    def ensure_default_room(self) -> Optional[Room]:
        """No longer auto-creates a default room; setup wizard defines the first room."""
        return None

    def add_player(self, sid: str, name: str | None = None, room_id: str | None = None, sheet: Optional[CharacterSheet] = None) -> Player:
        """Register a new Player and place them into a room (default: start or __void__).

        Preconditions:
        - sid must be non-empty
        - If room_id is provided, it will be used as-is (may be __void__ if unknown)
        Postconditions:
        - Player exists in self.players and, if room exists, their sid is in room.players
        """
        assert isinstance(sid, str) and sid != "", "sid must be a non-empty string"
        if not room_id:
            # Prefer configured start room if present and exists, else a void
            start_id = self.start_room_id if (self.start_room_id and self.start_room_id in self.rooms) else None
            room_id = start_id or "__void__"
        if sheet is None:
            if not name:
                # Derive a short default name from sid
                suffix = sid[-4:] if len(sid) >= 4 else sid
                name = f"Adventurer-{suffix}"
            # Initialize Character Sheet
            sheet = CharacterSheet(display_name=name)
        player = Player(sid=sid, room_id=room_id, sheet=sheet)
        self.players[sid] = player
        # Place in room
        room = self.rooms.get(room_id)
        if room:
            room.players.add(sid)
        # Postconditions
        assert sid in self.players, "player not registered"
        return player

    def remove_player(self, sid: str) -> None:
        """Remove a Player from the world and from their current room."""
        player = self.players.pop(sid, None)
        if not player:
            return
        room = self.rooms.get(player.room_id)
        if room and sid in room.players:
            room.players.remove(sid)

    def move_player(self, sid: str, new_room_id: str) -> None:
        """Move a Player to another room if it exists.

        Preconditions: sid exists and new_room_id is a known room id.
        """
        player = self.players.get(sid)
        if not player:
            return
        if new_room_id not in self.rooms:
            return
        # Remove from old room
        old_room = self.rooms.get(player.room_id)
        if old_room and sid in old_room.players:
            old_room.players.remove(sid)
        # Add to new room
        player.room_id = new_room_id
        self.rooms[new_room_id].players.add(sid)

    def describe_room_for(self, sid: str) -> str:
        """Return what the player identified by `sid` should see in their room."""
        player = self.players.get(sid)
        if not player:
            return "You drift in the void."
        room = self.rooms.get(player.room_id)
        if not room:
            return "You are nowhere."
        return room.describe(self, viewer_sid=sid)

    # --- Persistence: only rooms and npc_sheets ---
    def to_dict(self) -> dict:
        return {
            "rooms": {rid: room.to_dict() for rid, room in self.rooms.items()},
            "npc_sheets": {name: sheet.to_dict() for name, sheet in self.npc_sheets.items()},
            "users": {uid: user.to_dict() for uid, user in self.users.items()},
            # Persist npc id mapping
            "npc_ids": self.npc_ids,
            # World metadata
            "world_name": self.world_name,
            "world_description": self.world_description,
            "world_conflict": self.world_conflict,
            "start_room_id": self.start_room_id,
            "setup_complete": self.setup_complete,
            "safety_level": self.safety_level,
            # Relationships
            "relationships": self.relationships,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "World":
        w = cls()
        rooms = data.get("rooms", {})
        if isinstance(rooms, dict):
            for rid, rdata in rooms.items():
                if isinstance(rdata, dict):
                    room = Room.from_dict(rdata)
                    # Ensure mapping by its own id
                    w.rooms[room.id] = room
        npc_sheets = data.get("npc_sheets", {})
        if isinstance(npc_sheets, dict):
            for name, sdata in npc_sheets.items():
                if isinstance(sdata, dict):
                    w.npc_sheets[name] = CharacterSheet.from_dict(sdata)
        # Load npc id mapping and backfill for any npcs referenced in rooms
        npc_ids = data.get("npc_ids", {})
        if isinstance(npc_ids, dict):
            w.npc_ids = dict(npc_ids)
        # Backfill for any NPC names in rooms without ids
        try:
            for room in w.rooms.values():
                for npc_name in list(room.npcs):
                    if npc_name not in w.npc_ids:
                        w.npc_ids[npc_name] = str(uuid.uuid4())
        except Exception:
            pass
        users = data.get("users", {})
        if isinstance(users, dict):
            for uid, udata in users.items():
                if isinstance(udata, dict):
                    user = User.from_dict(udata)
                    # Keep key consistent with user_id
                    w.users[user.user_id] = user
        # World metadata
        w.world_name = data.get("world_name")
        w.world_description = data.get("world_description")
        w.world_conflict = data.get("world_conflict")
        w.start_room_id = data.get("start_room_id")
        w.setup_complete = bool(data.get("setup_complete", False))
        # Safety level with default to 'G' if missing
        lvl = (data.get("safety_level") or 'G').upper()
        if lvl not in ('G', 'PG-13', 'R', 'OFF'):
            lvl = 'G'
        w.safety_level = lvl
        # Relationships graph
        rels = data.get("relationships", {})
        if isinstance(rels, dict):
            # Ensure nested dicts are of correct type (string keys)
            w.relationships = {}
            try:
                for src, m in rels.items():
                    if not isinstance(src, str) or not isinstance(m, dict):
                        continue
                    w.relationships[src] = {str(tgt): str(val) for tgt, val in m.items()}
            except Exception:
                # Fallback to raw if any issues
                w.relationships = dict(rels)
        return w

    def save_to_file(self, path: str) -> None:
        try:
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception:
            # Best-effort persistence; avoid crashing the server on save errors
            pass

    @classmethod
    def load_from_file(cls, path: str) -> "World":
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                w = cls.from_dict(data)
                return w
        except Exception:
            # Fall through to a fresh world
            pass
        w = cls()
        return w

    # --- User helpers ---
    def get_user_by_display_name(self, name: str) -> Optional[User]:
        name_lower = name.strip().lower()
        for user in self.users.values():
            if user.display_name.lower() == name_lower:
                return user
        return None

    # --- NPC helpers ---
    def get_or_create_npc_id(self, npc_name: str) -> str:
        """Return a stable UUID for an NPC name, creating one if missing."""
        if npc_name not in self.npc_ids:
            self.npc_ids[npc_name] = str(uuid.uuid4())
        return self.npc_ids[npc_name]

    def create_user(self, display_name: str, password: str, description: str, is_admin: bool = False) -> User:
        assert isinstance(display_name, str) and 2 <= len(display_name) <= 32, "display_name must be 2-32 chars"
        assert isinstance(password, str) and len(password) >= 1, "password required"
        if self.get_user_by_display_name(display_name) is not None:
            raise ValueError("Display name already taken.")
        uid = str(uuid.uuid4())
        # Initialize a sheet mirroring the account's display name and description
        sheet = CharacterSheet(display_name=display_name, description=description)
        user = User(user_id=uid, display_name=display_name, password=password, description=description, sheet=sheet, is_admin=is_admin)
        self.users[uid] = user
        return user
