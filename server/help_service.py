from __future__ import annotations

"""Help Service.

Generates formatted help text for players and admins.
Extracted from server.py to reduce file size.
"""

from typing import Set, Dict, Any

# Fixed column width for aligned output
CMD_COL_MAX = 42


def _fmt_cmd(s: str, width: int = CMD_COL_MAX) -> str:
    """Return s padded/truncated to exactly width using ASCII ellipsis if needed."""
    if len(s) <= width:
        return s.ljust(width)
    if width <= 3:
        return s[:width]
    return s[: width - 3] + "..."


def _fmt_items(items: list[tuple[str, str]], indent: int = 0) -> list[str]:
    """Format a list of (command, description) tuples with alignment."""
    prefix = " " * indent
    return [prefix + _fmt_cmd(a) + "  - " + b for a, b in items]


def print_command_help() -> None:
    """Print a quick reference of available in-game commands to the console."""
    lines: list[str] = []
    lines.append("\n=== Server Command Quick Reference ===")

    # Auth
    lines.append("Auth:")
    lines += _fmt_items([
        ("/auth create <name> | <password> | <description>", "create an account & character"),
        ("/auth login <name> | <password>", "log in to your character"),
        ("/auth list_admins", "list admin users"),
    ], indent=2)
    lines.append("")

    # Player basics
    lines.append("Player commands (after auth):")
    lines += _fmt_items([
        ("look | l", "describe your current room"),
        ("look at <name>", "inspect a Player, NPC, or Object in the room"),
        ("move through <name>", "go via a named door or travel point"),
        ("move up stairs | move down stairs", "use stairs, if present"),
        ("say <message>", "say something; anyone present may respond"),
        ("say to <npc>[ and <npc>...]: <msg>", "address one or multiple NPCs directly"),
        ("tell <Player or NPC> <message>", "speak directly to one person/NPC (room hears it)"),
        ("whisper <Player or NPC> <message>", "private message; NPC always replies; not broadcast"),
        ("roll <dice> [| Private]", "roll dice publicly or privately (e.g., 2d6+1)"),
        ("gesture <verb>", "perform an emote (e.g., 'gesture wave' -> you wave)"),
        ("gesture <verb> to <target>", "targeted emote (e.g., 'gesture bow to Innkeeper')"),
        ("interact with <Object>", "list possible interactions for an object and choose one"),
        ("/trade <Player or NPC>", "pay coins for one of their items"),
        ("/barter <Player or NPC>", "trade one of your items for one of theirs"),
        ("/claim <Object>", "claim an Object as yours"),
        ("/unclaim <Object>", "remove your ownership from an Object"),
        ("/rename <new name>", "change your display name"),
        ("/describe <text>", "update your character description"),
        ("/sheet", "show your character sheet"),
        ("/help", "list available commands"),
    ], indent=2)
    lines.append("")

    # Admin
    lines.append("Admin commands (first created user is admin):")
    lines += _fmt_items([
        ("/auth promote <name>", "elevate a user to admin"),
        ("/auth demote <name>", "revoke a user's admin rights"),
        ("/auth list_admins", "list admin users"),
        ("/kick <playerName>", "disconnect a player"),
        ("/setup", "start world setup (create first room & NPC)"),
        ("/teleport <room name>", "teleport yourself to a room (fuzzy; 'here' allowed)"),
        ("/teleport <player> | <room name>", "teleport another player (fuzzy; 'here' = your room)"),
        ("/bring <player>", "bring a player to your current room"),
        ("/purge", "reset world to factory default (confirmation required)"),
        ("/worldstate", "print the redacted contents of world_state.json"),
        ("/safety <G|PG-13|R|OFF>", "set AI content safety level (admins)"),
        ("/faction factiongen", "[Experimental] AI-generate a small faction"),
    ], indent=2)
    lines.append("")

    # Room management
    lines.append("Room management:")
    lines += _fmt_items([
        ("/room create <id> | <description>", "create a new room"),
        ("/room setdesc <id> | <description>", "update a room's description"),
        ("/room rename <room name> | <new room name>", "rename a room id (updates links)"),
        ("/room adddoor <room name> | <door name> | <target room name>", "add a named door and link target"),
        ("/room removedoor <room name> | <door name>", "remove a named door"),
        ("/room lockdoor <door name> | <name, name, ...>", "lock to players or relationships"),
        ("relationship: <type> with <name>", "...as an alternative lock rule"),
        ("/room setstairs <room name> | <up room name or -> | <down room name or ->", "configure stairs"),
        ("/room linkdoor <room_a> | <door_a> | <room_b> | <door_b>", "link two doors across rooms"),
    ], indent=2)
    lines.append("")

    for line in lines:
        print(line)


def build_help_text(
    sid: str | None,
    players: Dict[str, Any],
    admins: Set[str],
) -> str:
    """Return BBCode-formatted help text tailored to the current user.

    - Unauthenticated: shows a quick start plus auth and basics.
    - Player: shows movement, talking, interactions, and profile commands.
    - Admins: includes admin, room, object, and NPC management commands.
    """
    is_player = bool(sid and sid in players)
    is_admin = bool(sid and sid in admins)

    lines: list[str] = []

    # Header
    lines.append("[b][u]COMMANDS REFERENCE[/u][/b]")
    lines.append("")

    # Quick start for new users
    if not is_player:
        lines.append("[b]Quick Start[/b]")
        lines += _fmt_items([
            ("create", "Interactive account creation (same as /auth create)"),
            ("login", "Interactive login (same as /auth login)"),
            ("list", "Show existing characters you can log into"),
        ])
        lines.append("")

    # Auth section (always visible)
    lines.append("[b]Authentication[/b]")
    lines += _fmt_items([
        ("/auth create <name> | <pass> | <desc>", "Create an account & character"),
        ("/auth login <name> | <pass>", "Log in to your character"),
        ("/auth list_admins", "List admin users"),
    ])
    lines.append("")

    # Player commands
    lines.append("[b]Player Actions[/b]")
    lines += _fmt_items([
        ("look | l", "Describe your current room"),
        ("look at <name>", "Inspect a Player, NPC, or Object in the room"),
        ("move through <name>", "Go via a named door or travel point"),
        ("move up/down stairs", "Use stairs, if present"),
        ("say <message>", "Say something; anyone present may respond"),
        ("say to <npc>: <msg>", "Address an NPC directly"),
        ("tell <target> <message>", "Speak to one person/NPC (room hears it)"),
        ("whisper <target> <message>", "Private message; NPC recalls context"),
        ("roll <dice> [| Private]", "Roll dice publicly or privately (e.g., 2d6+1)"),
        ("interact with <Object>", "List interactions for an object and pick one"),
        ("gesture <verb> [to <target>]", "Perform an emote (e.g., 'wave', 'bow')"),
        ("/trade <target>", "Pay coins for one of their items"),
        ("/barter <target>", "Trade one of your items for one of theirs"),
        ("/claim <Object>", "Claim an object as yours"),
        ("/unclaim <Object>", "Remove your ownership from an object"),
        ("/rename <new name>", "Change your display name"),
        ("/describe <text>", "Update your character description"),
        ("/sheet", "Show your character sheet"),
        ("/help", "Show this help"),
    ])

    # Admin commands
    if is_admin:
        lines.append("")
        lines.append("[b][u]ADMINISTRATION[/u][/b]")
        
        lines.append("")
        lines.append("[b]Core Admin[/b]")
        lines += _fmt_items([
            ("/audit <target>", "View detailed internal state of an entity"),
            ("/kick <playerName>", "Disconnect a player"),
            ("/teleport <target> | <room>", "Teleport self or other (fuzzy matching)"),
            ("/bring <player>", "Bring a player to your current room"),
            ("/purge", "Reset world to factory defaults (confirm)"),
            ("/worldstate", "Print redacted world_state.json"),
            ("/safety <G|PG-13|R|OFF>", "Set AI content safety level"),
            ("/settimedesc <hour> <text>", "Set description for a daily hour (0-23)"),
            ("/faction factiongen", "AI-generate a small faction"),
        ])
        
        lines.append("")
        lines.append("[b]World Building: Rooms[/b]")
        lines += _fmt_items([
            ("/room create <id> | <desc>", "Create a new room"),
            ("/room setdesc <id> | <desc>", "Update a room's description"),
            ("/room rename <old> | <new>", "Change a room's internal ID"),
            ("/room adddoor <door> | <target>", "Add a door and link a target room"),
            ("/room lockdoor <door> | <rules>", "Lock to players or relationships"),
            ("/room setstairs <up_room> | <down_room>", "Configure stairs"),
            ("/room linkdoor/linkstairs ...", "Link doors/stairs between rooms"),
        ])
        
        lines.append("")
        lines.append("[b]World Building: Objects[/b]")
        lines += _fmt_items([
            ("/object createtemplateobject", "Wizard: Create and save Object template"),
            ("/object createobject <params>", "Create Object instance (supports 'here')"),
            ("/object listtemplates", "List saved object template keys"),
            ("/object viewtemplate <key>", "Show a template's JSON"),
            ("/object deletetemplate <key>", "Delete a template"),
        ])
        
        lines.append("")
        lines.append("[b]World Building: NPCs[/b]")
        lines += _fmt_items([
            ("/npc add <room> | <name> | <desc>", "Add an NPC to a room"),
            ("/npc remove <npc name>", "Remove an NPC from your current room"),
            ("/npc setdesc <npc name> | <desc>", "Set an NPC's description"),
            ("/npc setrelation <rules>", "Link two entities (e.g., parent/child)"),
            ("/npc familygen <params>", "AI-generate a related NPC"),
        ])

    # Tips
    lines.append("")
    lines.append("[b]Tips & Tricks[/b]")
    lines.append('• [b]Quotes[/b]: Use quotes for names with spaces: "oak door", "Red Dragon".')
    lines.append("• [b]Separators[/b]: Use | to separate arguments: /auth create Alice | pw | Bio.")
    lines.append("• [b]Shortcuts[/b]: Use 'here' for current room: /object createobject here | ...")
    lines.append("• [b]Matching[/b]: Names are fuzzy-matched: exact > unique prefix > substring.")
    lines.append("• [b]Communication[/b]: /say (room), /tell (target), /whisper (private).")

    return "\n".join(lines)
