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
from typing import Dict, Set, Optional, List, Any, Tuple
from safe_utils import safe_call, safe_call_with_default


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
    
    Ownership (optional):
    - owner_id: stable UUID of a player (user.user_id) or NPC (world.npc_ids[name]) who owns this object
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
    # Ownership: player.user_id or npc_id; None means unowned
    owner_id: Optional[str] = None
    # Faction ownership: optional faction_id that owns this object
    faction_id: Optional[str] = None
    # Stable id
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Container support (when 'Container' in object_tags): two small and two large slots
    container_small_slots: List[Optional["Object"]] = field(default_factory=lambda: [None, None])
    container_large_slots: List[Optional["Object"]] = field(default_factory=lambda: [None, None])
    container_opened: bool = False
    container_searched: bool = False

    # --- Combat Modifiers ---
    weapon_damage: Optional[int] = None  # If weapon, base damage
    weapon_type: Optional[str] = None    # e.g., "cutting", "blunt", "piercing"
    armor_defense: Optional[int] = None  # If armor, base defense
    armor_type: Optional[str] = None     # e.g., "light", "medium", "heavy"

    def to_dict(self) -> dict:
        return {
            "uuid": self.uuid,
            "display_name": self.display_name,
            "description": self.description,
            "object_tag": sorted(list(self.object_tags)),
            "material_tag": self.material_tag,
            "value": self.value,
            # Ownership persistence (player.user_id or npc_id)
            "owner_id": getattr(self, 'owner_id', None),
            "faction_id": getattr(self, 'faction_id', None),
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
            # Combat modifiers
            "weapon_damage": self.weapon_damage,
            "weapon_type": self.weapon_type,
            "armor_defense": self.armor_defense,
            "armor_type": self.armor_type,
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
        def _parse_value():
            if isinstance(raw_value, int):
                return raw_value
            elif isinstance(raw_value, str):
                # strip common formatting
                s = raw_value.strip()
                if s.isdigit() or (s.startswith('-') and s[1:].isdigit()):
                    return int(s)
            return None
        ival = safe_call(_parse_value)

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
            # Combat modifiers
            weapon_damage=data.get("weapon_damage"),
            weapon_type=data.get("weapon_type"),
            armor_defense=data.get("armor_defense"),
            armor_type=data.get("armor_type"),
        )
        # Optional nutrition fields with back-compat
        def _set_nutrition_values():
            sv = data.get("satiation_value")
            hv = data.get("hydration_value")
            obj.satiation_value = int(sv) if isinstance(sv, (int, str)) and str(sv).lstrip('-').isdigit() else None  # type: ignore[attr-defined]
            obj.hydration_value = int(hv) if isinstance(hv, (int, str)) and str(hv).lstrip('-').isdigit() else None  # type: ignore[attr-defined]
        safe_call(_set_nutrition_values)
        # Optional ownership field with back-compat (also accept 'ownership')
        def _set_ownership():
            owner = data.get("owner_id")
            if owner is None and "ownership" in data:
                owner = data.get("ownership")
            obj.owner_id = str(owner) if owner is not None and str(owner) else None  # type: ignore[attr-defined]
        safe_call(_set_ownership)
        # Optional faction_id
        obj.faction_id = str(data.get("faction_id")) if data.get("faction_id") else None
        # Load container fields
        def _load_container_fields():
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
        safe_call(_load_container_fields)
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
    currency: int = 0
    # Needs system (0-100 scale; higher is better). Defaults represent a well-fed, hydrated NPC.
    hunger: float = 100.0
    thirst: float = 100.0
    # New social need: drips down over time; refilled by conversation (player or NPC)
    socialization: float = 100.0
    # New: Sleep/rest meter (0-100; higher is better). Drops over time; restored by sleeping in a bed you own.
    sleep: float = 100.0
    # When sleeping, ticks remaining and the bed object uuid (to validate the spot each tick)
    sleeping_ticks_remaining: int = 0
    sleeping_bed_uuid: str | None = None
    
    # Enhanced Needs System (Priority 1: Radiant AI expansion)
    # Additional needs beyond the basic four, driving more complex behaviors
    safety: float = 100.0      # Security/threat avoidance - drops near danger, restored in safe areas
    wealth_desire: float = 50.0  # Drive to accumulate resources/currency - influences trading/hoarding
    social_status: float = 50.0  # Desire for reputation/standing - affects interaction choices
    
    # Personality Traits (0-100 scale, like Oblivion's attributes)
    # These influence how NPCs pursue their needs and interact with the world
    responsibility: int = 50    # Moral compass - low values increase criminal behavior likelihood
    aggression: int = 30       # Combat/conflict tendency - affects fight-or-flight decisions
    confidence: int = 50       # Risk-taking behavior - influences bold vs cautious choices
    curiosity: int = 50        # Exploration drive - affects movement and investigation behaviors
    
    # Memory and Relationship System
    # Simple lists to track recent events and social connections
    memories: list[dict] = field(default_factory=list)  # Recent events/interactions this NPC remembers
    relationships: dict[str, float] = field(default_factory=dict)  # NPC_ID/Player_ID -> relationship score (-100 to +100)
    
    # --- Nexus System Attributes ---
    # Core Attributes (GURPS)
    strength: int = 10
    dexterity: int = 10
    intelligence: int = 10
    health: int = 10
    # --- Combat/Morale System Additions ---
    morale: int = 50            # Fighting spirit (0-100). Low = likely to yield.
    yielded: bool = False       # True once entity yields (NPC stops fighting).
    is_dead: bool = False       # Permadeath flag; players with True cannot act.

    # Secondary Characteristics
    hp: int = 10
    max_hp: int = 10
    will: int = 10
    perception: int = 10
    fp: int = 10
    max_fp: int = 10
    
    # Narrative (FATE)
    high_concept: str = ""
    trouble: str = ""
    destiny_points: int = 3

    # Background (SWN)
    background: str = ""
    focus: str = ""

    # Traits
    advantages: List[Dict[str, Any]] = field(default_factory=list)
    disadvantages: List[Dict[str, Any]] = field(default_factory=list)
    quirks: List[str] = field(default_factory=list)
    narrative_traits: List[str] = field(default_factory=list)

    # Psychosocial Matrix (Sliders -10 to +10)
    # Sexuality & Identity
    sexuality_hom_het: int = 0
    physical_presentation_mas_fem: int = 0
    social_presentation_mas_fem: int = 0
    is_dominant: bool = False
    is_submissive: bool = False
    is_asexual: bool = False

    # Emotional State
    rage_terror: int = 0
    loathing_admiration: int = 0
    grief_ecstasy: int = 0
    amaze_vigil: int = 0

    # Political State
    auth_egal: int = 0
    cons_lib: int = 0

    # Philosophical State
    spirit_mat: int = 0
    ego_alt: int = 0
    hed_asc: int = 0
    nih_mor: int = 0
    rat_rom: int = 0
    ske_abso: int = 0

    # Action economy: how many actions an NPC can take per tick. Players ignore this.
    action_points: int = 0
    # Queue of planned actions produced by AI or offline planner. Each entry is a dict: {"tool": str, "args": dict}
    plan_queue: list[dict] = field(default_factory=list)

    # --- Combat Equipment ---
    equipped_weapon: str | None = None  # UUID of equipped weapon object
    equipped_armor: str | None = None   # UUID of equipped armor object

    def to_dict(self) -> dict:
        # ...existing code...
        d = {
            "display_name": self.display_name,
            "description": self.description,
            "inventory": self.inventory.to_dict(),
            "currency": int(self.currency or 0),
            # Persist needs/planning fields for NPCs and future player use
            "hunger": self.hunger,
            "thirst": self.thirst,
            "socialization": self.socialization,
            "sleep": self.sleep,
            "sleeping_ticks_remaining": int(self.sleeping_ticks_remaining or 0),
            "sleeping_bed_uuid": self.sleeping_bed_uuid,
            # Enhanced needs system
            "safety": self.safety,
            "wealth_desire": self.wealth_desire,
            "social_status": self.social_status,
            # Personality traits
            "responsibility": self.responsibility,
            "aggression": self.aggression,
            "confidence": self.confidence,
            "curiosity": self.curiosity,
            # Memory and relationships
            "memories": list(self.memories or []),
            "relationships": dict(self.relationships or {}),
            # Nexus System
            "strength": self.strength,
            "dexterity": self.dexterity,
            "intelligence": self.intelligence,
            "health": self.health,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "will": self.will,
            "perception": self.perception,
            "fp": self.fp,
            "max_fp": self.max_fp,
            "morale": self.morale,
            "yielded": self.yielded,
            "is_dead": self.is_dead,
            "high_concept": self.high_concept,
            "trouble": self.trouble,
            "destiny_points": self.destiny_points,
            "background": self.background,
            "focus": self.focus,
            "advantages": self.advantages,
            "disadvantages": self.disadvantages,
            "quirks": self.quirks,
            "narrative_traits": self.narrative_traits,
            "sexuality_hom_het": self.sexuality_hom_het,
            "physical_presentation_mas_fem": self.physical_presentation_mas_fem,
            "social_presentation_mas_fem": self.social_presentation_mas_fem,
            "is_dominant": self.is_dominant,
            "is_submissive": self.is_submissive,
            "is_asexual": self.is_asexual,
            "rage_terror": self.rage_terror,
            "loathing_admiration": self.loathing_admiration,
            "grief_ecstasy": self.grief_ecstasy,
            "amaze_vigil": self.amaze_vigil,
            "auth_egal": self.auth_egal,
            "cons_lib": self.cons_lib,
            "spirit_mat": self.spirit_mat,
            "ego_alt": self.ego_alt,
            "hed_asc": self.hed_asc,
            "nih_mor": self.nih_mor,
            "rat_rom": self.rat_rom,
            "ske_abso": self.ske_abso,
            # Action system
            "action_points": self.action_points,
            "plan_queue": list(self.plan_queue or []),
            # Combat equipment
            "equipped_weapon": self.equipped_weapon,
            "equipped_armor": self.equipped_armor,
        }
        return d

    @staticmethod
    def from_dict(data: dict) -> "CharacterSheet":
        # ...existing code...
        def _safe_int(val: Any, default: int) -> int:
            if val is None:
                return default
            if isinstance(val, int):
                return val
            if isinstance(val, str):
                try:
                    return int(val)
                except ValueError:
                    return default
            return default
        
        def _safe_float(val: Any, default: float) -> float:
            if val is None:
                return default
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                try:
                    return float(val)
                except ValueError:
                    return default
            return default
        
        return CharacterSheet(
            display_name=data.get("display_name", "Unnamed"),
            description=data.get("description", "A nondescript adventurer."),
            inventory=Inventory.from_dict(data.get("inventory", {})),
            currency=_safe_int(data.get("currency"), 0),
            # Needs system fields - migrations should have ensured these exist
            hunger=_safe_float(data.get("hunger"), 100.0),
            thirst=_safe_float(data.get("thirst"), 100.0),
            socialization=_safe_float(data.get("socialization"), 100.0),
            sleep=_safe_float(data.get("sleep"), 100.0),
            sleeping_ticks_remaining=_safe_int(data.get("sleeping_ticks_remaining"), 0),
            sleeping_bed_uuid=str(data.get("sleeping_bed_uuid")) if data.get("sleeping_bed_uuid") else None,
            # Enhanced needs system - backfill with sensible defaults
            safety=_safe_float(data.get("safety"), 100.0),
            wealth_desire=_safe_float(data.get("wealth_desire"), 50.0),
            social_status=_safe_float(data.get("social_status"), 50.0),
            # Personality traits - backfill with moderate defaults (Oblivion-style)
            responsibility=_safe_int(data.get("responsibility"), 50),
            aggression=_safe_int(data.get("aggression"), 30),
            confidence=_safe_int(data.get("confidence"), 50),
            curiosity=_safe_int(data.get("curiosity"), 50),
            # Memory and relationships - safe list/dict loading
            memories=list(data.get("memories", [])) if isinstance(data.get("memories"), list) else [],
            relationships=dict(data.get("relationships", {})) if isinstance(data.get("relationships"), dict) else {},
            # Nexus System
            strength=_safe_int(data.get("strength"), 10),
            dexterity=_safe_int(data.get("dexterity"), 10),
            intelligence=_safe_int(data.get("intelligence"), 10),
            health=_safe_int(data.get("health"), 10),
            hp=_safe_int(data.get("hp"), 10),
            max_hp=_safe_int(data.get("max_hp"), 10),
            will=_safe_int(data.get("will"), 10),
            perception=_safe_int(data.get("perception"), 10),
            fp=_safe_int(data.get("fp"), 10),
            max_fp=_safe_int(data.get("max_fp"), 10),
            morale=_safe_int(data.get("morale"), 50),
            yielded=bool(data.get("yielded", False)),
            is_dead=bool(data.get("is_dead", False)),
            high_concept=str(data.get("high_concept", "")),
            trouble=str(data.get("trouble", "")),
            destiny_points=_safe_int(data.get("destiny_points"), 3),
            background=str(data.get("background", "")),
            focus=str(data.get("focus", "")),
            advantages=list(data.get("advantages", [])) if isinstance(data.get("advantages"), list) else [],
            disadvantages=list(data.get("disadvantages", [])) if isinstance(data.get("disadvantages"), list) else [],
            quirks=list(data.get("quirks", [])) if isinstance(data.get("quirks"), list) else [],
            narrative_traits=list(data.get("narrative_traits", [])) if isinstance(data.get("narrative_traits", []), list) else [],
            sexuality_hom_het=_safe_int(data.get("sexuality_hom_het"), 0),
            physical_presentation_mas_fem=_safe_int(data.get("physical_presentation_mas_fem"), 0),
            social_presentation_mas_fem=_safe_int(data.get("social_presentation_mas_fem"), 0),
            is_dominant=bool(data.get("is_dominant", False)),
            is_submissive=bool(data.get("is_submissive", False)),
            is_asexual=bool(data.get("is_asexual", False)),
            rage_terror=_safe_int(data.get("rage_terror"), 0),
            loathing_admiration=_safe_int(data.get("loathing_admiration"), 0),
            grief_ecstasy=_safe_int(data.get("grief_ecstasy"), 0),
            amaze_vigil=_safe_int(data.get("amaze_vigil"), 0),
            auth_egal=_safe_int(data.get("auth_egal"), 0),
            cons_lib=_safe_int(data.get("cons_lib"), 0),
            spirit_mat=_safe_int(data.get("spirit_mat"), 0),
            ego_alt=_safe_int(data.get("ego_alt"), 0),
            hed_asc=_safe_int(data.get("hed_asc"), 0),
            nih_mor=_safe_int(data.get("nih_mor"), 0),
            rat_rom=_safe_int(data.get("rat_rom"), 0),
            ske_abso=_safe_int(data.get("ske_abso"), 0),
            # Action system
            action_points=_safe_int(data.get("action_points"), 0),
            plan_queue=list(data.get("plan_queue", [])),
            # Combat equipment
            equipped_weapon=data.get("equipped_weapon"),
            equipped_armor=data.get("equipped_armor"),
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
    # Player respawn point: if set, login places the player in the room containing this bed object uuid
    home_bed_uuid: str | None = None

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "password": self.password,
            "description": self.description,
            "sheet": self.sheet.to_dict(),
            "is_admin": self.is_admin,
            "home_bed_uuid": self.home_bed_uuid,
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
            home_bed_uuid=str(data.get("home_bed_uuid")) if isinstance(data.get("home_bed_uuid"), str) and data.get("home_bed_uuid") else None,
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
    # Faction ownership: optional faction_id that owns this room
    faction_id: Optional[str] = None
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
            # Faction ownership
            "faction_id": self.faction_id,
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
            faction_id=str(data.get("faction_id")) if data.get("faction_id") else None,
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
        # Note: UUID backfill and travel point object creation has been moved to migrations.
        # Migration003 handles UUID generation, Migration004 handles travel point objects.
        return room


class Faction:
    """A faction represents an organized group of players and NPCs with shared goals.
    
    Factions provide a way to organize characters into meaningful groups with 
    relationships to other factions. Each faction maintains lists of member entities,
    allied factions, and rival factions for dynamic political gameplay.
    """
    
    def __init__(self, 
                 faction_id: str, 
                 name: str, 
                 description: str = "",
                 member_player_ids: Optional[List[str]] = None,
                 member_npc_ids: Optional[List[str]] = None,
                 ally_faction_ids: Optional[List[str]] = None,
                 rival_faction_ids: Optional[List[str]] = None) -> None:
        """Initialize a new faction.
        
        Args:
            faction_id: Unique identifier for this faction (UUID format)
            name: Display name of the faction
            description: Optional description of the faction's purpose/background
            member_player_ids: List of player IDs (session IDs) who are members
            member_npc_ids: List of NPC IDs who are members  
            ally_faction_ids: List of faction IDs that are allies
            rival_faction_ids: List of faction IDs that are rivals
        """
        # Core faction identity
        self.faction_id: str = faction_id
        self.name: str = name
        self.description: str = description
        
        # Member lists - we store entity IDs for persistence stability
        # Player members are identified by their user_id (not session sid)
        # NPC members are identified by their stable NPC UUID from world.npc_ids
        self.member_player_ids: List[str] = member_player_ids or []
        self.member_npc_ids: List[str] = member_npc_ids or []
        
        # Political relationships with other factions
        self.ally_faction_ids: List[str] = ally_faction_ids or []
        self.rival_faction_ids: List[str] = rival_faction_ids or []
        
        # Faction metadata - could be extended later
        self.created_timestamp: Optional[float] = None
        self.leader_player_id: Optional[str] = None  # Optional designated leader
        
    def add_member_player(self, player_id: str) -> bool:
        """Add a player to this faction's membership.
        
        Args:
            player_id: The player's user ID (not session ID)
            
        Returns:
            True if added successfully, False if already a member
        """
        if player_id not in self.member_player_ids:
            self.member_player_ids.append(player_id)
            return True
        return False
        
    def add_member_npc(self, npc_id: str) -> bool:
        """Add an NPC to this faction's membership.
        
        Args:
            npc_id: The NPC's stable UUID from world.npc_ids
            
        Returns:
            True if added successfully, False if already a member
        """
        if npc_id not in self.member_npc_ids:
            self.member_npc_ids.append(npc_id)
            return True
        return False
        
    def remove_member_player(self, player_id: str) -> bool:
        """Remove a player from this faction's membership.
        
        Args:
            player_id: The player's user ID
            
        Returns:
            True if removed successfully, False if not a member
        """
        try:
            self.member_player_ids.remove(player_id)
            return True
        except ValueError:
            return False
            
    def remove_member_npc(self, npc_id: str) -> bool:
        """Remove an NPC from this faction's membership.
        
        Args:
            npc_id: The NPC's stable UUID
            
        Returns:
            True if removed successfully, False if not a member
        """
        try:
            self.member_npc_ids.remove(npc_id)
            return True
        except ValueError:
            return False
    
    def add_ally(self, faction_id: str) -> bool:
        """Add an allied faction relationship.
        
        Args:
            faction_id: The faction ID to mark as ally
            
        Returns:
            True if added successfully, False if already an ally
        """
        if faction_id not in self.ally_faction_ids:
            self.ally_faction_ids.append(faction_id)
            return True
        return False
        
    def add_rival(self, faction_id: str) -> bool:
        """Add a rival faction relationship.
        
        Args:
            faction_id: The faction ID to mark as rival
            
        Returns:
            True if added successfully, False if already a rival
        """
        if faction_id not in self.rival_faction_ids:
            self.rival_faction_ids.append(faction_id)
            return True
        return False
        
    def remove_ally(self, faction_id: str) -> bool:
        """Remove an allied faction relationship.
        
        Args:
            faction_id: The faction ID to remove from allies
            
        Returns:
            True if removed successfully, False if not an ally
        """
        try:
            self.ally_faction_ids.remove(faction_id)
            return True
        except ValueError:
            return False
            
    def remove_rival(self, faction_id: str) -> bool:
        """Remove a rival faction relationship.
        
        Args:
            faction_id: The faction ID to remove from rivals
            
        Returns:
            True if removed successfully, False if not a rival
        """
        try:
            self.rival_faction_ids.remove(faction_id)
            return True
        except ValueError:
            return False
    
    def get_total_members(self) -> int:
        """Get the total number of faction members (players + NPCs).
        
        Returns:
            Total count of all members
        """
        return len(self.member_player_ids) + len(self.member_npc_ids)
        
    def is_player_member(self, player_id: str) -> bool:
        """Check if a player is a member of this faction.
        
        Args:
            player_id: The player's user ID
            
        Returns:
            True if the player is a member
        """
        return player_id in self.member_player_ids
        
    def is_npc_member(self, npc_id: str) -> bool:
        """Check if an NPC is a member of this faction.
        
        Args:
            npc_id: The NPC's stable UUID
            
        Returns:
            True if the NPC is a member
        """
        return npc_id in self.member_npc_ids
        
    def is_ally(self, faction_id: str) -> bool:
        """Check if another faction is an ally.
        
        Args:
            faction_id: The other faction's ID
            
        Returns:
            True if the faction is an ally
        """
        return faction_id in self.ally_faction_ids
        
    def is_rival(self, faction_id: str) -> bool:
        """Check if another faction is a rival.
        
        Args:
            faction_id: The other faction's ID
            
        Returns:
            True if the faction is a rival
        """
        return faction_id in self.rival_faction_ids
    
    def to_dict(self) -> dict:
        """Serialize faction to dictionary for persistence.
        
        Returns:
            Dictionary representation of the faction
        """
        return {
            'faction_id': self.faction_id,
            'name': self.name,
            'description': self.description,
            'member_player_ids': self.member_player_ids,
            'member_npc_ids': self.member_npc_ids,
            'ally_faction_ids': self.ally_faction_ids,
            'rival_faction_ids': self.rival_faction_ids,
            'created_timestamp': self.created_timestamp,
            'leader_player_id': self.leader_player_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Faction":
        """Deserialize faction from dictionary data.
        
        Args:
            data: Dictionary containing faction data
            
        Returns:
            Faction instance restored from the data
        """
        faction = cls(
            faction_id=data.get('faction_id', ''),
            name=data.get('name', ''),
            description=data.get('description', ''),
            member_player_ids=data.get('member_player_ids', []),
            member_npc_ids=data.get('member_npc_ids', []),
            ally_faction_ids=data.get('ally_faction_ids', []),
            rival_faction_ids=data.get('rival_faction_ids', [])
        )
        
        # Load optional metadata
        faction.created_timestamp = data.get('created_timestamp')
        faction.leader_player_id = data.get('leader_player_id')
        
        return faction

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
        # Faction system: organized groups of players and NPCs with political relationships
        # Key is faction_id (UUID), value is Faction instance  
        self.factions: Dict[str, Faction] = {}
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
        # Opt-in for advanced GOAP planning assisted by external models
        self.advanced_goap_enabled: bool = False
        # Relationship graph (directed): entity_id -> { target_entity_id: relationship_type }
        # entity_id is user.user_id for players and world.get_or_create_npc_id(name) for NPCs
        self.relationships: Dict[str, Dict[str, str]] = {}
        # Debug / Creative Mode: when True, all users are admins automatically.
        # Persisted; can be toggled at server startup. Used by account/login flows.
        self.debug_creative_mode = False
        # Schema version for migrations: tracks the data format version
        # New worlds start at latest version; old worlds are migrated on load
        self.world_version: int = 0  # Will be set to latest during save/load  # Will be set to latest during save/load

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

    # --- Persistence: rooms, npc_sheets, and all world data with versioning ---
    def to_dict(self) -> dict:
        # Import here to avoid circular dependency
        from world_migrations import migration_registry
        
        # Always save at the latest schema version
        latest_version = migration_registry.get_latest_version()
        
        return {
            # Schema version must be first for clarity
            "world_version": latest_version,
            "rooms": {rid: room.to_dict() for rid, room in self.rooms.items()},
            "npc_sheets": {name: sheet.to_dict() for name, sheet in self.npc_sheets.items()},
            "object_templates": {key: obj.to_dict() for key, obj in self.object_templates.items()},
            "users": {uid: user.to_dict() for uid, user in self.users.items()},
            # Persist npc id mapping
            "npc_ids": self.npc_ids,
            # Faction system data
            "factions": {fid: faction.to_dict() for fid, faction in self.factions.items()},
            # World metadata
            "world_name": self.world_name,
            "world_description": self.world_description,
            "world_conflict": self.world_conflict,
            "start_room_id": self.start_room_id,
            "setup_complete": self.setup_complete,
            "safety_level": self.safety_level,
            "advanced_goap_enabled": self.advanced_goap_enabled,
            # Relationships
            "relationships": self.relationships,
            # Debug / Creative Mode flag
            "debug_creative_mode": self.debug_creative_mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "World":
        """Load World from dictionary data, applying migrations as needed.
        
        This method now uses the migration system to handle schema evolution
        cleanly, rather than ad-hoc backfill logic scattered throughout.
        """
        # Import here to avoid circular dependency
        from world_migrations import migration_registry
        
        # Apply any needed migrations to bring data up to current schema
        try:
            if migration_registry.needs_migration(data):
                current_version = migration_registry.get_current_version(data)
                latest_version = migration_registry.get_latest_version()
                print(f"Migrating world data from version {current_version} to {latest_version}")
                data = migration_registry.migrate(data)
            else:
                current_version = migration_registry.get_current_version(data)
                print(f"World data is current at version {current_version}")
        except Exception as e:
            # Migration failed - log error but continue with raw data for robustness
            print(f"Migration failed, loading raw data: {e}")
        
        # Create new world instance
        w = cls()
        
        # Set version from migrated data
        w.world_version = data.get("world_version", 0)
        
        # Load rooms (migrations should have cleaned up any issues)
        rooms = data.get("rooms", {})
        if isinstance(rooms, dict):
            for rid, rdata in rooms.items():
                if isinstance(rdata, dict):
                    room = Room.from_dict(rdata)
                    w.rooms[room.id] = room
        
        # Load NPC sheets (migrations should have backfilled needs)
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
        
        # Load NPC ID mapping (migrations should have ensured completeness)
        npc_ids = data.get("npc_ids", {})
        if isinstance(npc_ids, dict):
            w.npc_ids = dict(npc_ids)
        
        # Load factions with safe error handling
        factions = data.get("factions", {})
        if isinstance(factions, dict):
            for fid, fdata in factions.items():
                if isinstance(fdata, dict):
                    try:
                        faction = Faction.from_dict(fdata)
                        w.factions[faction.faction_id] = faction
                    except Exception:
                        # Skip malformed faction entries but log for debugging
                        print(f"Warning: Skipped malformed faction data for {fid}")
        
        # Load users
        users = data.get("users", {})
        if isinstance(users, dict):
            for uid, udata in users.items():
                if isinstance(udata, dict):
                    user = User.from_dict(udata)
                    w.users[user.user_id] = user
        
        # Load world metadata with safe defaults
        w.world_name = data.get("world_name")
        w.world_description = data.get("world_description")
        w.world_conflict = data.get("world_conflict")
        w.start_room_id = data.get("start_room_id")
        w.setup_complete = bool(data.get("setup_complete", False))
        
        # Safety level with validation
        lvl = (data.get("safety_level") or 'G').upper()
        if lvl not in ('G', 'PG-13', 'R', 'OFF'):
            lvl = 'G'
        w.safety_level = lvl
        
        # Advanced GOAP flag
        w.advanced_goap_enabled = bool(data.get("advanced_goap_enabled", False))
        
        # Relationships graph with safe loading
        rels = data.get("relationships", {})
        if isinstance(rels, dict):
            w.relationships = {}
            try:
                for src, m in rels.items():
                    if isinstance(src, str) and isinstance(m, dict):
                        w.relationships[src] = {str(tgt): str(val) for tgt, val in m.items()}
            except Exception:
                w.relationships = {}
        
        # Debug / Creative Mode flag
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
        """Load World from file, applying any necessary schema migrations.
        
        If the file doesn't exist or loading fails, returns a fresh World instance.
        Migration errors are logged but don't prevent loading - the system falls back
        to raw data loading for maximum robustness.
        """
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # from_dict handles migrations internally
                w = cls.from_dict(data)
                return w
        except Exception as e:
            # Log the error but continue with fresh world for robustness
            print(f"Failed to load world from {path}: {e}")
            # Fall through to a fresh world
        
        # Return fresh world at latest schema version
        w = cls()
        # Import here to avoid circular dependency
        from world_migrations import migration_registry
        w.world_version = migration_registry.get_latest_version()
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
        """Return a stable UUID for an NPC name, creating one if missing.
        
        Args:
            npc_name: The display name of the NPC. Must be a non-empty string.
            
        Returns:
            The stable UUID string for this NPC.
            
        Raises:
            TypeError: If npc_name is not a string.
            ValueError: If npc_name is empty or whitespace-only.
        """
        if not isinstance(npc_name, str):
            raise TypeError(f"NPC name must be a string, got {type(npc_name)}")
        
        npc_name = npc_name.strip()
        if not npc_name:
            raise ValueError("NPC name cannot be empty or whitespace-only")
        
        # Initialize npc_ids dict if missing (robustness for corrupt state)
        if not hasattr(self, 'npc_ids') or self.npc_ids is None:
            self.npc_ids = {}
        
        if npc_name not in self.npc_ids:
            new_id = str(uuid.uuid4())
            self.npc_ids[npc_name] = new_id
            
            # Log when creating new NPC IDs for debugging/audit trail
            print(f"Created new NPC ID for '{npc_name}': {new_id}")
            
        return self.npc_ids[npc_name]

    def validate_npc_integrity(self) -> List[str]:
        """Validate consistency between NPC sheets and ID mappings.
        
        Returns:
            List of error messages describing inconsistencies found.
        """
        errors = []
        
        # Ensure both collections exist
        if not hasattr(self, 'npc_sheets') or self.npc_sheets is None:
            self.npc_sheets = {}
        if not hasattr(self, 'npc_ids') or self.npc_ids is None:
            self.npc_ids = {}
        
        # Get all NPC names from various sources
        sheet_names = set(self.npc_sheets.keys())
        id_names = set(self.npc_ids.keys())
        room_npc_names = set()
        
        # Collect NPCs referenced in rooms
        for room_id, room in self.rooms.items():
            if hasattr(room, 'npcs') and room.npcs:
                room_npc_names.update(room.npcs)
        
        # Check for NPCs with sheets but no IDs
        missing_ids = sheet_names - id_names
        for npc_name in missing_ids:
            errors.append(f"NPC '{npc_name}' has sheet but missing from npc_ids mapping")
        
        # Check for NPCs with IDs but no sheets
        missing_sheets = id_names - sheet_names
        for npc_name in missing_sheets:
            errors.append(f"NPC '{npc_name}' has ID mapping but missing character sheet")
        
        # Check for NPCs referenced in rooms but missing sheets
        orphaned_room_npcs = room_npc_names - sheet_names
        for npc_name in orphaned_room_npcs:
            errors.append(f"NPC '{npc_name}' referenced in room but missing character sheet")
        
        # Check for NPCs referenced in rooms but missing IDs
        room_npcs_no_ids = room_npc_names - id_names
        for npc_name in room_npcs_no_ids:
            errors.append(f"NPC '{npc_name}' referenced in room but missing from npc_ids mapping")
        
        return errors

    def repair_npc_integrity(self) -> Tuple[int, List[str]]:
        """Repair NPC integrity issues by creating missing sheets and IDs.
        
        This method attempts to fix common NPC integrity problems:
        - Creates missing character sheets for NPCs with IDs
        - Creates missing ID mappings for NPCs with sheets
        - Creates both sheets and IDs for NPCs only referenced in rooms
        
        Returns:
            Tuple of (repairs_made, repair_messages)
        """
        repairs = 0
        messages = []
        
        # Ensure collections exist
        if not hasattr(self, 'npc_sheets') or self.npc_sheets is None:
            self.npc_sheets = {}
        if not hasattr(self, 'npc_ids') or self.npc_ids is None:
            self.npc_ids = {}
        
        # Get all NPC names from various sources
        sheet_names = set(self.npc_sheets.keys())
        id_names = set(self.npc_ids.keys())
        room_npc_names = set()
        
        for room_id, room in self.rooms.items():
            if hasattr(room, 'npcs') and room.npcs:
                room_npc_names.update(room.npcs)
        
        all_npc_names = sheet_names | id_names | room_npc_names
        
        # Repair missing character sheets
        for npc_name in all_npc_names:
            if npc_name not in self.npc_sheets:
                self.npc_sheets[npc_name] = CharacterSheet(
                    display_name=npc_name,
                    description=f"An NPC named {npc_name}."
                )
                repairs += 1
                messages.append(f"Created missing character sheet for NPC '{npc_name}'")
        
        # Repair missing ID mappings
        for npc_name in all_npc_names:
            if npc_name not in self.npc_ids:
                self.npc_ids[npc_name] = str(uuid.uuid4())
                repairs += 1
                messages.append(f"Created missing ID mapping for NPC '{npc_name}'")
        
        return repairs, messages

    def create_user(self, display_name: str, password: str, description: str,
                    is_admin: bool = False) -> User:
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

    # --- Faction helpers ---
    def create_faction(self, name: str, description: str = "", leader_player_id: Optional[str] = None) -> Faction:
        """Create a new faction with a unique ID.
        
        Args:
            name: Display name for the faction
            description: Optional description of the faction
            leader_player_id: Optional player ID to designate as leader
            
        Returns:
            The newly created Faction instance
            
        Raises:
            ValueError: If a faction with the same name already exists
        """
        # Check for duplicate names (case-insensitive)
        name_lower = name.strip().lower()
        for faction in self.factions.values():
            if faction.name.lower() == name_lower:
                raise ValueError(f"Faction name '{name}' already exists")
        
        # Create faction with unique ID
        import uuid
        faction_id = str(uuid.uuid4())
        faction = Faction(
            faction_id=faction_id,
            name=name.strip(),
            description=description
        )
        
        # Set creation timestamp
        import time
        faction.created_timestamp = time.time()
        
        # Set leader if provided
        if leader_player_id:
            faction.leader_player_id = leader_player_id
        
        # Store in world
        self.factions[faction_id] = faction
        return faction
    
    def get_faction_by_name(self, name: str) -> Optional[Faction]:
        """Find a faction by its display name (case-insensitive).
        
        Args:
            name: The faction name to search for
            
        Returns:
            The Faction instance if found, None otherwise
        """
        name_lower = name.strip().lower()
        for faction in self.factions.values():
            if faction.name.lower() == name_lower:
                return faction
        return None
    
    def get_player_factions(self, player_id: str) -> List[Faction]:
        """Get all factions that a player is a member of.
        
        Args:
            player_id: The player's user ID
            
        Returns:
            List of Faction instances the player belongs to
        """
        return [faction for faction in self.factions.values() 
                if faction.is_player_member(player_id)]
    
    def get_npc_factions(self, npc_id: str) -> List[Faction]:
        """Get all factions that an NPC is a member of.
        
        Args:
            npc_id: The NPC's stable UUID
            
        Returns:
            List of Faction instances the NPC belongs to
        """
        return [faction for faction in self.factions.values() 
                if faction.is_npc_member(npc_id)]
    
    def remove_faction(self, faction_id: str) -> bool:
        """Remove a faction from the world.
        
        This also removes any references to this faction from other factions'
        ally and rival lists to maintain referential integrity.
        
        Args:
            faction_id: The faction ID to remove
            
        Returns:
            True if the faction was removed, False if it didn't exist
        """
        if faction_id not in self.factions:
            return False
        
        # Remove the faction
        del self.factions[faction_id]
        
        # Clean up references from other factions
        for other_faction in self.factions.values():
            other_faction.remove_ally(faction_id)
            other_faction.remove_rival(faction_id)
        
        return True
    
    def validate_faction_integrity(self) -> List[str]:
        """Validate faction system integrity and return error messages.
        
        This checks for:
        - Invalid player/NPC references
        - Invalid ally/rival faction references  
        - Circular relationships
        
        Returns:
            List of error message strings
        """
        errors = []
        
        for faction_id, faction in self.factions.items():
            # Validate player members exist
            for player_id in faction.member_player_ids:
                if player_id not in self.users:
                    errors.append(f"Faction '{faction.name}' references non-existent player: {player_id}")
            
            # Validate NPC members exist  
            for npc_id in faction.member_npc_ids:
                # Check if NPC ID exists in our mapping
                npc_exists = any(mapped_id == npc_id for mapped_id in self.npc_ids.values())
                if not npc_exists:
                    errors.append(f"Faction '{faction.name}' references non-existent NPC: {npc_id}")
            
            # Validate ally factions exist
            for ally_id in faction.ally_faction_ids:
                if ally_id not in self.factions:
                    errors.append(f"Faction '{faction.name}' has non-existent ally: {ally_id}")
                elif ally_id == faction_id:
                    errors.append(f"Faction '{faction.name}' lists itself as an ally")
            
            # Validate rival factions exist
            for rival_id in faction.rival_faction_ids:
                if rival_id not in self.factions:
                    errors.append(f"Faction '{faction.name}' has non-existent rival: {rival_id}")
                elif rival_id == faction_id:
                    errors.append(f"Faction '{faction.name}' lists itself as a rival")
            
            # Check for conflicting ally/rival relationships
            for ally_id in faction.ally_faction_ids:
                if ally_id in faction.rival_faction_ids:
                    errors.append(f"Faction '{faction.name}' lists {ally_id} as both ally and rival")
            
            # Validate leader exists and is a member
            if faction.leader_player_id:
                if faction.leader_player_id not in self.users:
                    errors.append(f"Faction '{faction.name}' has non-existent leader: {faction.leader_player_id}")
                elif not faction.is_player_member(faction.leader_player_id):
                    errors.append(f"Faction '{faction.name}' leader is not a member: {faction.leader_player_id}")
        
        return errors

    def validate(self) -> List[str]:
        """Validate world state and return a list of error messages.
        
        This method performs comprehensive validation of world integrity including:
        - UUID uniqueness and format validation
        - Referential integrity (room links, player locations, NPC references)
        - Object consistency (travel points, inventory constraints)
        - User/account consistency
        - Faction system integrity
        
        Returns:
            List of error message strings. Empty list indicates no validation errors.
        """
        errors = []
        
        # Helper to validate UUID format
        def _is_valid_uuid(uid: str) -> bool:
            if not isinstance(uid, str):
                return False
            try:
                import uuid
                uuid.UUID(uid)
                return True
            except ValueError:
                return False
        
        # Track all UUIDs to check uniqueness
        all_uuids = set()
        
        def _check_uuid_unique(uid: str, context: str) -> None:
            if not _is_valid_uuid(uid):
                errors.append(f"Invalid UUID format in {context}: {uid}")
                return
            if uid in all_uuids:
                errors.append(f"Duplicate UUID in {context}: {uid}")
            else:
                all_uuids.add(uid)
        
        # 1. Validate room structure and collect room UUIDs
        room_ids = set()
        for room_id, room in self.rooms.items():
            room_ids.add(room_id)
            
            # Check room UUID
            if hasattr(room, 'uuid'):
                _check_uuid_unique(room.uuid, f"room '{room_id}' uuid")
            
            # Validate door targets exist
            for door_name, target_room_id in (room.doors or {}).items():
                if target_room_id not in self.rooms:
                    errors.append(f"Room '{room_id}' door '{door_name}' points to non-existent room: {target_room_id}")
            
            # Validate stairs targets exist
            if room.stairs_up_to and room.stairs_up_to not in self.rooms:
                errors.append(f"Room '{room_id}' stairs_up_to points to non-existent room: {room.stairs_up_to}")
            if room.stairs_down_to and room.stairs_down_to not in self.rooms:
                errors.append(f"Room '{room_id}' stairs_down_to points to non-existent room: {room.stairs_down_to}")
            
            # Validate door IDs (only check if they don't correspond to objects)
            for door_name in (room.doors or {}).keys():
                door_id = (room.door_ids or {}).get(door_name)
                if door_id:
                    # Only check door ID uniqueness if there's no corresponding object
                    # (if there is an object, it will be checked in the objects section)
                    if door_id not in (room.objects or {}):
                        _check_uuid_unique(door_id, f"room '{room_id}' door '{door_name}' id")
            
            # Validate stairs IDs
            if hasattr(room, 'stairs_up_id') and room.stairs_up_id:
                _check_uuid_unique(room.stairs_up_id, f"room '{room_id}' stairs_up_id")
            if hasattr(room, 'stairs_down_id') and room.stairs_down_id:
                _check_uuid_unique(room.stairs_down_id, f"room '{room_id}' stairs_down_id")
            
            # Validate room objects
            for obj_uuid, obj in (room.objects or {}).items():
                _check_uuid_unique(obj_uuid, f"room '{room_id}' object uuid")
                if obj.uuid != obj_uuid:
                    errors.append(f"Room '{room_id}' object key mismatch: key={obj_uuid}, obj.uuid={obj.uuid}")
                
                # Check travel point links
                if hasattr(obj, 'object_tags') and isinstance(obj.object_tags, set):
                    if 'Travel Point' in obj.object_tags:
                        if hasattr(obj, 'link_target_room_id') and obj.link_target_room_id:
                            if obj.link_target_room_id not in self.rooms:
                                errors.append(f"Room '{room_id}' travel point '{obj.display_name}' links to non-existent room: {obj.link_target_room_id}")
        
        # 2. Validate player structure
        for sid, player in self.players.items():
            if hasattr(player, 'id'):
                _check_uuid_unique(player.id, f"player '{sid}' id")
            
            # Check player room exists
            if player.room_id not in room_ids and player.room_id != "__void__":
                errors.append(f"Player '{sid}' in non-existent room: {player.room_id}")
            
            # Check player is registered in their room
            if player.room_id in self.rooms:
                room = self.rooms[player.room_id]
                if sid not in room.players:
                    errors.append(f"Player '{sid}' not registered in room '{player.room_id}' players set")
            
            # Validate player inventory
            if hasattr(player, 'sheet') and hasattr(player.sheet, 'inventory'):
                inv = player.sheet.inventory
                for slot_idx, obj in enumerate(inv.slots or []):
                    if obj is not None:
                        _check_uuid_unique(obj.uuid, f"player '{sid}' inventory slot {slot_idx}")
                        
                        # Check inventory constraints
                        if not inv.can_place(slot_idx, obj):
                            errors.append(f"Player '{sid}' inventory slot {slot_idx} violates constraints for object '{obj.display_name}'")
        
        # 3. Validate NPC structure
        npc_names = set()
        for npc_name, sheet in self.npc_sheets.items():
            npc_names.add(npc_name)
            
            # Validate NPC inventory
            if hasattr(sheet, 'inventory'):
                inv = sheet.inventory
                for slot_idx, obj in enumerate(inv.slots or []):
                    if obj is not None:
                        _check_uuid_unique(obj.uuid, f"NPC '{npc_name}' inventory slot {slot_idx}")
                        
                        # Check inventory constraints
                        if not inv.can_place(slot_idx, obj):
                            errors.append(f"NPC '{npc_name}' inventory slot {slot_idx} violates constraints for object '{obj.display_name}'")
        
        # Check NPCs referenced in rooms have sheets
        for room_id, room in self.rooms.items():
            for npc_name in (room.npcs or set()):
                if npc_name not in self.npc_sheets:
                    errors.append(f"Room '{room_id}' references NPC '{npc_name}' but no sheet exists")
        
        # 4. Validate NPC ID mapping
        for npc_name, npc_id in (self.npc_ids or {}).items():
            _check_uuid_unique(npc_id, f"NPC '{npc_name}' id")
        
        # Check all NPCs have ID mappings
        for npc_name in npc_names:
            if npc_name not in (self.npc_ids or {}):
                errors.append(f"NPC '{npc_name}' missing from npc_ids mapping")
        
        # 5. Validate user accounts
        user_display_names = set()
        for user_id, user in self.users.items():
            _check_uuid_unique(user_id, f"user account user_id")
            if user.user_id != user_id:
                errors.append(f"User account key mismatch: key={user_id}, user.user_id={user.user_id}")
            
            # Check display name uniqueness
            name_lower = user.display_name.lower()
            if name_lower in user_display_names:
                errors.append(f"Duplicate user display name: {user.display_name}")
            else:
                user_display_names.add(name_lower)
            
            # Validate user's character sheet inventory
            if hasattr(user, 'sheet') and hasattr(user.sheet, 'inventory'):
                inv = user.sheet.inventory
                for slot_idx, obj in enumerate(inv.slots or []):
                    if obj is not None:
                        _check_uuid_unique(obj.uuid, f"user '{user.display_name}' inventory slot {slot_idx}")
                        
                        # Check inventory constraints
                        if not inv.can_place(slot_idx, obj):
                            errors.append(f"User '{user.display_name}' inventory slot {slot_idx} violates constraints for object '{obj.display_name}'")
        
        # 6. Validate object templates
        for template_key, obj in (self.object_templates or {}).items():
            _check_uuid_unique(obj.uuid, f"object template '{template_key}'")
        
        # 7. Validate world configuration
        if self.start_room_id and self.start_room_id not in room_ids:
            errors.append(f"World start_room_id points to non-existent room: {self.start_room_id}")
        
        # 8. Validate relationships graph
        for entity_id, relationships in (self.relationships or {}).items():
            if not _is_valid_uuid(entity_id):
                errors.append(f"Invalid entity_id in relationships: {entity_id}")
            for target_id, relationship_type in relationships.items():
                if not _is_valid_uuid(target_id):
                    errors.append(f"Invalid target entity_id in relationships[{entity_id}]: {target_id}")
        
        # 9. Validate reciprocal door linkage
        # Check that doors have appropriate reciprocal connections
        for room_id, room in self.rooms.items():
            for door_name, target_room_id in (room.doors or {}).items():
                if target_room_id in self.rooms:
                    target_room = self.rooms[target_room_id]
                    # Check if target room has any door back to this room
                    has_reciprocal = any(
                        target_target == room_id
                        for target_target in (target_room.doors or {}).values()
                    )
                    if not has_reciprocal:
                        msg = (f"Room '{room_id}' door '{door_name}' -> '{target_room_id}' "
                               f"lacks reciprocal door")
                        errors.append(msg)
                
                # Validate door object exists and is consistent
                door_id = (room.door_ids or {}).get(door_name)
                if door_id:
                    if door_id not in (room.objects or {}):
                        msg = (f"Room '{room_id}' door '{door_name}' has door_id {door_id} "
                               f"but no matching object")
                        errors.append(msg)
                    else:
                        door_obj = room.objects[door_id]
                        # Check travel point tags
                        if not (hasattr(door_obj, 'object_tags') and
                                isinstance(door_obj.object_tags, set) and
                                'Travel Point' in door_obj.object_tags):
                            msg = (f"Room '{room_id}' door object '{door_name}' "
                                   f"missing 'Travel Point' tag")
                            errors.append(msg)
                        # Check link target matches door destination
                        if (hasattr(door_obj, 'link_target_room_id') and
                                door_obj.link_target_room_id != target_room_id):
                            msg = (f"Room '{room_id}' door object '{door_name}' "
                                   f"link_target_room_id mismatch: "
                                   f"object={door_obj.link_target_room_id}, door={target_room_id}")
                            errors.append(msg)
                else:
                    errors.append(f"Room '{room_id}' door '{door_name}' missing door_id")
        
        # 10. Validate reciprocal stairs linkage
        for room_id, room in self.rooms.items():
            # Check stairs up reciprocity
            if room.stairs_up_to and room.stairs_up_to in self.rooms:
                target_room = self.rooms[room.stairs_up_to]
                if target_room.stairs_down_to != room_id:
                    msg = (f"Room '{room_id}' stairs_up_to '{room.stairs_up_to}' "
                           f"lacks reciprocal stairs_down_to")
                    errors.append(msg)
                
                # Validate stairs up object exists and is consistent
                if hasattr(room, 'stairs_up_id') and room.stairs_up_id:
                    if room.stairs_up_id not in (room.objects or {}):
                        msg = (f"Room '{room_id}' stairs_up_id {room.stairs_up_id} "
                               f"but no matching object")
                        errors.append(msg)
                    else:
                        stairs_obj = room.objects[room.stairs_up_id]
                        if not (hasattr(stairs_obj, 'object_tags') and
                                isinstance(stairs_obj.object_tags, set) and
                                'Travel Point' in stairs_obj.object_tags):
                            msg = f"Room '{room_id}' stairs up object missing 'Travel Point' tag"
                            errors.append(msg)
                        if (hasattr(stairs_obj, 'link_target_room_id') and
                                stairs_obj.link_target_room_id != room.stairs_up_to):
                            msg = f"Room '{room_id}' stairs up object link_target_room_id mismatch"
                            errors.append(msg)
                else:
                    errors.append(f"Room '{room_id}' has stairs_up_to but missing stairs_up_id")
            
            # Check stairs down reciprocity
            if room.stairs_down_to and room.stairs_down_to in self.rooms:
                target_room = self.rooms[room.stairs_down_to]
                if target_room.stairs_up_to != room_id:
                    msg = (f"Room '{room_id}' stairs_down_to '{room.stairs_down_to}' "
                           f"lacks reciprocal stairs_up_to")
                    errors.append(msg)
                
                # Validate stairs down object exists and is consistent
                if hasattr(room, 'stairs_down_id') and room.stairs_down_id:
                    if room.stairs_down_id not in (room.objects or {}):
                        msg = (f"Room '{room_id}' stairs_down_id {room.stairs_down_id} "
                               f"but no matching object")
                        errors.append(msg)
                    else:
                        stairs_obj = room.objects[room.stairs_down_id]
                        if not (hasattr(stairs_obj, 'object_tags') and
                                isinstance(stairs_obj.object_tags, set) and
                                'Travel Point' in stairs_obj.object_tags):
                            msg = f"Room '{room_id}' stairs down object missing 'Travel Point' tag"
                            errors.append(msg)
                        if (hasattr(stairs_obj, 'link_target_room_id') and
                                stairs_obj.link_target_room_id != room.stairs_down_to):
                            msg = f"Room '{room_id}' stairs down obj link_target_room_id mismatch"
                            errors.append(msg)
                else:
                    msg = f"Room '{room_id}' has stairs_down_to but missing stairs_down_id"
                    errors.append(msg)
        
        # 11. Validate object tag consistency for all travel points
        for room_id, room in self.rooms.items():
            for obj_uuid, obj in (room.objects or {}).items():
                if hasattr(obj, 'object_tags') and isinstance(obj.object_tags, set):
                    if 'Travel Point' in obj.object_tags:
                        # Travel points must have Immovable tag
                        if 'Immovable' not in obj.object_tags:
                            msg = (f"Room '{room_id}' travel point '{obj.display_name}' "
                                   f"missing 'Immovable' tag")
                            errors.append(msg)
                        
                        # Travel points should have a link target (unless they're special cases)
                        if not hasattr(obj, 'link_target_room_id') or not obj.link_target_room_id:
                            msg = (f"Room '{room_id}' travel point '{obj.display_name}' "
                                   f"missing link_target_room_id")
                            errors.append(msg)
        
        # 12. Validate NPC integrity (sheets ↔ IDs consistency)
        npc_integrity_errors = self.validate_npc_integrity()
        errors.extend(npc_integrity_errors)
        
        # 13. Validate faction system integrity
        faction_integrity_errors = self.validate_faction_integrity()
        errors.extend(faction_integrity_errors)
        
        # Also validate faction UUIDs are unique
        for faction_id, faction in self.factions.items():
            _check_uuid_unique(faction_id, f"faction '{faction.name}' id")
            if faction.faction_id != faction_id:
                errors.append(f"Faction key mismatch: key={faction_id}, faction.faction_id={faction.faction_id}")
        
        return errors
