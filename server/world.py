"""World model for the TinyMUD (very small and in-memory).

Concepts:
- Controlled Character: A character controlled by a User connected via Socket.IO (identified by a session id `sid`).
- Character: a character sheet with a display name, description, and inventory that is controlled by AI.
- Object: an item with a name, description, material type, and interaction tags (e.g., "small", "large").
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
class Object:
    """Generic game object.

    Schema (all optional fields may be None):
    - uuid: stable identifier
    - display_name: human-friendly name (e.g., "Sword")
    - description: flavor text
    - object_tags: tags such as "weapon", "cutting damage", "small", "Immovable", "Travel Point"
    - material_tag: e.g., "bronze"
    - value: integer numeric value (optional)
    - loot_location_hint: an Object indicating where it can usually be found
    - durability: remaining durability (integer)
    - quality: e.g., "average"
    - crafting_recipe: a list of Objects that represent inputs/stations (freeform objects ok)
    - deconstruct_recipe: a list of Objects for salvage output

    Travel/Linking (optional helpers for movement objects like doors/stairs):
    - link_target_room_id: if this object acts as a travel point to a room
    - link_to_object_uuid: if this object links to another Object (future use)
    """

    display_name: str
    description: str = ""
    object_tags: Set[str] = field(default_factory=lambda: {"small"})
    material_tag: Optional[str] = None
    value: Optional[int] = None
    # Nutrition for needs system (optional; back-compat defaults to None)
    satiation_value: Optional[int] = None
    hydration_value: Optional[int] = None
    loot_location_hint: Optional["Object"] = None
    durability: Optional[int] = None
    quality: Optional[str] = None
    crafting_recipe: List["Object"] = field(default_factory=list)
    deconstruct_recipe: List["Object"] = field(default_factory=list)
    # Travel helpers
    link_target_room_id: Optional[str] = None
    link_to_object_uuid: Optional[str] = None
    # Stable id
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Container support (when 'Container' in object_tags): two small and two large slots
    container_small_slots: List[Optional["Object"]] = field(default_factory=lambda: [None, None])
    container_large_slots: List[Optional["Object"]] = field(default_factory=lambda: [None, None])
    container_opened: bool = False
    container_searched: bool = False

    def to_dict(self) -> dict:
        return {
            "uuid": self.uuid,
            "display_name": self.display_name,
            "description": self.description,
            "object_tag": sorted(list(self.object_tags)),
            "material_tag": self.material_tag,
            "value": self.value,
            # Nutrition properties for needs system (optional)
            "satiation_value": getattr(self, 'satiation_value', None),
            "hydration_value": getattr(self, 'hydration_value', None),
            "loot_location_hint": (self.loot_location_hint.to_dict() if self.loot_location_hint else None),
            "durability": self.durability,
            "quality": self.quality,
            "crafting_recipe": [o.to_dict() for o in (self.crafting_recipe or [])],
            "deconstruct_recipe": [o.to_dict() for o in (self.deconstruct_recipe or [])],
            # Travel helpers (optional)
            "link_target_room_id": self.link_target_room_id,
            "link_to_object_uuid": self.link_to_object_uuid,
            # Container persistence
            "container_small_slots": [o.to_dict() if o else None for o in (self.container_small_slots or [None, None])],
            "container_large_slots": [o.to_dict() if o else None for o in (self.container_large_slots or [None, None])],
            "container_opened": self.container_opened,
            "container_searched": self.container_searched,
        }

    @staticmethod
    def from_dict(data: dict) -> "Object":
        """Load from either the new Object schema or legacy Item schema.

        Legacy Item shape: {"name": str, "tags": [str]}
        New Object shape:  {"display_name": str, "object_tag": [str], ...}
        Also accepts a few common misspellings from the request (e.g., 'druability', 'deconstruct_recpie').
        """
        if not isinstance(data, dict):
            # Fall back to a minimal unnamed object
            return Object(display_name=str(data))

        # Small helpers to coerce inputs into Objects
        def _to_object(maybe) -> "Object":
            if isinstance(maybe, dict):
                return Object.from_dict(maybe)
            # Fallback: string or other -> simple object named after it
            return Object(display_name=str(maybe) if maybe is not None else "Unnamed")

        def _to_object_list(maybe_list) -> List["Object"]:
            if maybe_list is None:
                return []
            if isinstance(maybe_list, (str, int)):
                # Back-compat: single scalar -> single object
                return [_to_object(maybe_list)]
            if isinstance(maybe_list, list):
                out: List[Object] = []
                for el in maybe_list:
                    if isinstance(el, dict) or isinstance(el, (str, int)):
                        out.append(_to_object(el))
                return out
            # Unknown type -> empty list
            return []

        # Extract common name fields
        display_name = data.get("display_name") or data.get("name") or "Unnamed"
        # Tags under various keys
        tags = set()
        if isinstance(data.get("object_tag"), list):
            tags = set(map(str, data.get("object_tag", [])))
        elif isinstance(data.get("tags"), list):  # legacy
            tags = set(map(str, data.get("tags", [])))
        # Provide a default when missing
        if not tags:
            tags = {"small"}

        # Optional fields with typo back-compat
        durability = data.get("durability")
        if durability is None and "druability" in data:
            durability = data.get("druability")
        deconstruct_recipe = data.get("deconstruct_recipe")
        if deconstruct_recipe is None and "deconstruct_recpie" in data:
            deconstruct_recipe = data.get("deconstruct_recpie")

        # Parse value: accept int or numeric string; otherwise None
        raw_value = data.get("value")
        ival: Optional[int] = None
        try:
            if isinstance(raw_value, int):
                ival = raw_value
            elif isinstance(raw_value, str):
                # strip common formatting
                s = raw_value.strip()
                if s.isdigit() or (s.startswith('-') and s[1:].isdigit()):
                    ival = int(s)
        except Exception:
            ival = None

        # Loot location hint can be an embedded object or a string
        llh_raw = data.get("loot_location_hint")
        llh_obj = None
        if llh_raw is not None:
            llh_obj = _to_object(llh_raw)

        # Crafting/deconstruct recipes as lists of Objects (accept legacy string)
        craft_list = _to_object_list(data.get("crafting_recipe"))
        decon_list = _to_object_list(data.get("deconstruct_recipe"))
        # Back-compat for misspelled key
        if not decon_list and "deconstruct_recpie" in data:
            decon_list = _to_object_list(data.get("deconstruct_recpie"))

        # Build object
        obj = Object(
            display_name=display_name,
            description=str(data.get("description") or ""),
            object_tags=tags,
            material_tag=(str(data.get("material_tag")) if data.get("material_tag") is not None else None),
            value=ival,
            loot_location_hint=llh_obj,
            durability=(int(durability) if isinstance(durability, (int, str)) and str(durability).isdigit() else None),
            quality=(str(data.get("quality")) if data.get("quality") is not None else None),
            crafting_recipe=craft_list,
            deconstruct_recipe=decon_list,
            link_target_room_id=(str(data.get("link_target_room_id")) if data.get("link_target_room_id") is not None else None),
            link_to_object_uuid=(str(data.get("link_to_object_uuid")) if data.get("link_to_object_uuid") is not None else None),
            uuid=str(data.get("uuid") or uuid.uuid4()),
        )
        # Optional nutrition fields with back-compat
        try:
            sv = data.get("satiation_value")
            hv = data.get("hydration_value")
            obj.satiation_value = int(sv) if isinstance(sv, (int, str)) and str(sv).lstrip('-').isdigit() else None  # type: ignore[attr-defined]
            obj.hydration_value = int(hv) if isinstance(hv, (int, str)) and str(hv).lstrip('-').isdigit() else None  # type: ignore[attr-defined]
        except Exception:
            pass
        # Load container fields
        try:
            small_raw = data.get("container_small_slots")
            large_raw = data.get("container_large_slots")
            if isinstance(small_raw, list):
                obj.container_small_slots = [Object.from_dict(el) if isinstance(el, dict) else None for el in small_raw][:2]
                if len(obj.container_small_slots) < 2:
                    obj.container_small_slots.extend([None] * (2 - len(obj.container_small_slots)))
            if isinstance(large_raw, list):
                obj.container_large_slots = [Object.from_dict(el) if isinstance(el, dict) else None for el in large_raw][:2]
                if len(obj.container_large_slots) < 2:
                    obj.container_large_slots.extend([None] * (2 - len(obj.container_large_slots)))
            obj.container_opened = bool(data.get("container_opened", False))
            obj.container_searched = bool(data.get("container_searched", False))
        except Exception:
            # Leave defaults on error
            pass
        return obj


@dataclass
class Inventory:
    """8 slot inventory with constraints:
    - slot 0: left hand
    - slot 1: right hand
    - slots 2-5: four small items (must have 'small')
    - slots 6-7: two large items (must have 'large')
    """

    slots: List[Optional[Object]] = field(default_factory=lambda: [None] * 8)

    def can_place(self, index: int, obj: Object) -> bool:
        if index < 0 or index >= 8:
            return False
        # Immovable objects (e.g., Doors, Stairs, fixed fixtures) cannot be placed anywhere
        tags = obj.object_tags or set()
        if 'Immovable' in tags or 'Travel Point' in tags:
            return False
        if index in (0, 1):
            # hands can hold either small or large items (conceptually one hand carrying a large object is allowed here for simplicity)
            return True
        if 2 <= index <= 5:
            # Allow only 'small'; disallow if also marked as 'large'
            is_small = ('small' in tags)
            is_large = ('large' in tags)
            return is_small and not is_large
        if 6 <= index <= 7:
            # Allow only 'large'
            return ('large' in tags)
        return False

    def place(self, index: int, obj: Object) -> bool:
        if not self.can_place(index, obj):
            return False
        self.slots[index] = obj
        return True

    def remove(self, index: int) -> Optional[Object]:
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
            obj = self.slots[idx]
            names.append(f"{label}: {obj.display_name if obj else '[empty]'}")
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
            inv.slots = [Object.from_dict(s) if isinstance(s, dict) else None for s in slots][:8]
            # Ensure exactly 8 slots
            if len(inv.slots) < 8:
                inv.slots.extend([None] * (8 - len(inv.slots)))
        return inv


@dataclass
class CharacterSheet:
    display_name: str
    description: str = "A nondescript adventurer."
    inventory: Inventory = field(default_factory=Inventory)
    # Needs system (0-100 scale; higher is better). Defaults represent a well-fed, hydrated NPC.
    hunger: float = 100.0
    thirst: float = 100.0
    # Action economy: how many actions an NPC can take per tick. Players ignore this.
    action_points: int = 0
    # Queue of planned actions produced by AI or offline planner. Each entry is a dict: {"tool": str, "args": dict}
    plan_queue: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "display_name": self.display_name,
            "description": self.description,
            "inventory": self.inventory.to_dict(),
            # Persist needs/planning fields for NPCs and future player use
            "hunger": self.hunger,
            "thirst": self.thirst,
            "action_points": self.action_points,
            "plan_queue": list(self.plan_queue or []),
        }

    @staticmethod
    def from_dict(data: dict) -> "CharacterSheet":
        # Backfill defaults for worlds saved before needs existed
        hunger = data.get("hunger")
        thirst = data.get("thirst")
        ap = data.get("action_points")
        pq = data.get("plan_queue")
        return CharacterSheet(
            display_name=data.get("display_name", "Unnamed"),
            description=data.get("description", "A nondescript adventurer."),
            inventory=Inventory.from_dict(data.get("inventory", {})),
            hunger=float(hunger) if isinstance(hunger, (int, float, str)) and str(hunger).replace('.', '', 1).lstrip('-').isdigit() else 100.0,
            thirst=float(thirst) if isinstance(thirst, (int, float, str)) and str(thirst).replace('.', '', 1).lstrip('-').isdigit() else 100.0,
            action_points=int(ap) if isinstance(ap, (int, str)) and str(ap).lstrip('-').isdigit() else 0,
            plan_queue=list(pq) if isinstance(pq, list) else [],
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
    # Objects physically present in the room (includes doors/stairs as Objects)
    objects: Dict[str, Object] = field(default_factory=dict)  # key: object uuid -> Object

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

        # Travel Points category (doors and stairs) plus other visible objects
        try:
            travel_color = "#FFA500"
            tp_names: List[str] = []
            other_objects: List[str] = []
            # Prefer object list for richer tagging
            vals = list((self.objects or {}).values()) if isinstance(self.objects, dict) else []
            if vals:
                for o in vals:
                    try:
                        name = getattr(o, 'display_name', None)
                        if not name:
                            continue
                        tags = set(getattr(o, 'object_tags', []) or [])
                        if 'Travel Point' in tags:
                            tp_names.append(f"[color={travel_color}]{name}[/color]")
                        else:
                            other_objects.append(str(name))
                    except Exception:
                        continue
            else:
                # Fallback to basic exits as travel points
                for d in sorted((self.doors or {}).keys()):
                    tp_names.append(f"[color={travel_color}]{d}[/color]")
                if self.stairs_up_to:
                    tp_names.append(f"[color={travel_color}]stairs up[/color]")
                if self.stairs_down_to:
                    tp_names.append(f"[color={travel_color}]stairs down[/color]")
            # Unique + stable order
            def _uniq(lst: List[str]) -> List[str]:
                seen = {}
                out: List[str] = []
                for x in lst:
                    if x not in seen:
                        seen[x] = True
                        out.append(x)
                return out
            tp_names = _uniq(sorted(tp_names, key=lambda s: s.lower()))
            other_objects = _uniq(sorted(other_objects, key=lambda s: s.lower()))
            if tp_names:
                lines.append("Travel Points: " + ", ".join(tp_names))
            if other_objects:
                lines.append("Objects: " + ", ".join(other_objects))
        except Exception:
            # Fallback to prior exits formatting on any error
            exit_bits: List[str] = []
            if self.doors:
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
            # Objects in the room
            "objects": {oid: obj.to_dict() for oid, obj in self.objects.items()},
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
            objects={},
        )
        # Load objects if present
        try:
            objs_raw = data.get("objects", {})
            if isinstance(objs_raw, dict):
                for oid, odata in objs_raw.items():
                    if isinstance(odata, dict):
                        obj = Object.from_dict(odata)
                        # Ensure key matches object uuid
                        room.objects[obj.uuid] = obj
            elif isinstance(objs_raw, list):
                for odata in objs_raw:
                    if isinstance(odata, dict):
                        obj = Object.from_dict(odata)
                        room.objects[obj.uuid] = obj
        except Exception:
            pass
        # Backfill missing door IDs for existing door names
        for dname in list(room.doors.keys()):
            if dname not in room.door_ids:
                room.door_ids[dname] = str(uuid.uuid4())
        # Backfill stairs IDs when targets are set but ids missing
        if room.stairs_up_to and not room.stairs_up_id:
            room.stairs_up_id = str(uuid.uuid4())
        if room.stairs_down_to and not room.stairs_down_id:
            room.stairs_down_id = str(uuid.uuid4())
        # Ensure door objects exist for every named door
        try:
            for dname, target_room in (room.doors or {}).items():
                oid = room.door_ids.get(dname) or str(uuid.uuid4())
                room.door_ids[dname] = oid
                if oid not in room.objects:
                    desc = f"A doorway named '{dname}'."
                    obj = Object(
                        display_name=dname,
                        description=desc,
                        object_tags={"Immovable", "Travel Point"},
                        link_target_room_id=target_room,
                    )
                    # Force object's uuid to match oid for stable linking
                    obj.uuid = oid
                    room.objects[oid] = obj
                else:
                    # Ensure tags include immovable + travel point and link target is set
                    o = room.objects[oid]
                    o.object_tags.update({"Immovable", "Travel Point"})
                    if not getattr(o, 'link_target_room_id', None):
                        o.link_target_room_id = target_room
        except Exception:
            pass
        # Ensure stairs objects exist (up/down) when linked
        try:
            if room.stairs_up_to and room.stairs_up_id:
                oid = room.stairs_up_id
                if oid not in room.objects:
                    obj = Object(
                        display_name="stairs up",
                        description="A staircase leading up.",
                        object_tags={"Immovable", "Travel Point"},
                        link_target_room_id=room.stairs_up_to,
                    )
                    obj.uuid = oid
                    room.objects[oid] = obj
                else:
                    o = room.objects[oid]
                    o.object_tags.update({"Immovable", "Travel Point"})
                    if not getattr(o, 'link_target_room_id', None):
                        o.link_target_room_id = room.stairs_up_to
            if room.stairs_down_to and room.stairs_down_id:
                oid = room.stairs_down_id
                if oid not in room.objects:
                    obj = Object(
                        display_name="stairs down",
                        description="A staircase leading down.",
                        object_tags={"Immovable", "Travel Point"},
                        link_target_room_id=room.stairs_down_to,
                    )
                    obj.uuid = oid
                    room.objects[oid] = obj
                else:
                    o = room.objects[oid]
                    o.object_tags.update({"Immovable", "Travel Point"})
                    if not getattr(o, 'link_target_room_id', None):
                        o.link_target_room_id = room.stairs_down_to
        except Exception:
            pass
        return room


class World:
    def __init__(self) -> None:
        self.rooms: Dict[str, Room] = {}
        self.players: Dict[str, Player] = {}
        # Simple NPC sheets by name (if needed later)
        self.npc_sheets: Dict[str, CharacterSheet] = {}
        # Admin-created object templates: key -> Object
        self.object_templates: Dict[str, Object] = {}
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
        # Debug / Creative Mode: when True, all users are admins automatically.
        # Persisted; can be toggled at server startup. Used by account/login flows.
        self.debug_creative_mode = False

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
            "object_templates": {key: obj.to_dict() for key, obj in self.object_templates.items()},
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
            # Debug / Creative Mode flag
            "debug_creative_mode": self.debug_creative_mode,
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
        # Load object templates
        obj_t = data.get("object_templates", {})
        if isinstance(obj_t, dict):
            for key, odata in obj_t.items():
                if isinstance(odata, dict):
                    try:
                        w.object_templates[str(key)] = Object.from_dict(odata)
                    except Exception:
                        # Skip malformed entries
                        pass
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
        # Debug / Creative Mode flag (default False for back-compat)
        w.debug_creative_mode = bool(data.get("debug_creative_mode", False))
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
