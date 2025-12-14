# Add or Customize NPCs

TinyMUD has a full NPC system with AI-powered dialogue and autonomous behavior.

## Quick Start: In-Game Commands

The easiest way to add NPCs is using admin commands in-game:

```
/npc add <room> | <name> | <description>
```

Example:
```
/npc add tavern | Mira the Bartender | A cheerful woman who knows everyone's secrets.
```

## AI-Generated NPCs

Generate fully-statted NPCs with the Nexus character system:

```
/npc generate                              # Contextual: fits current room
/npc generate <room> | <name> | <desc>     # Explicit: specify details
```

This creates NPCs with:
- FATE aspects (High Concept, Trouble, Background, Focus)
- GURPS attributes (Strength, Dexterity, Intelligence, Health)
- Psychosocial matrix (personality axes like Authority/Egalitarian)
- Full derived stats (HP, Will, Perception, FP)

See `docs/npc-generate-command.md` for the complete guide.

## Editing NPC Attributes

```
/npc setdesc <name> | <new description>
/npc setattr <name> | <attribute> | <value>    # e.g., strength | 14
/npc setaspect <name> | <type> | <value>       # e.g., trouble | "Too Trusting"
/npc setmatrix <name> | <axis> | <value>       # e.g., auth_egal | -3
/npc sheet <name>                               # View full character sheet
```

## NPC Behavior

NPCs have autonomous behavior driven by a GOAP (Goal-Oriented Action Planning) system:

- **Needs:** Hunger, thirst, socialization, sleep (0-100 scale)
- **Actions:** NPCs eat, drink, sleep, and socialize autonomously
- **AI Planning:** When players are present, Gemini AI plans actions; otherwise uses a deterministic offline planner

See `docs/goap-ai.md` for details.

## Manual Setup (Advanced)

For programmatic control, NPCs are stored as `CharacterSheet` objects:

```python
# In server/world.py or a service
sheet = CharacterSheet(
    display_name="The Wizard",
    description="A wise, mysterious figure in flowing robes.",
    strength=10, dexterity=12, intelligence=16, health=11,
    high_concept="Master of the Arcane Arts",
    trouble="Speaks in Riddles"
)
world.npc_sheets["The Wizard"] = sheet
world.rooms["tower"].npcs.add("The Wizard")
```

## No API Key?

Without a Gemini key, NPCs still work:
- Dialogue uses friendly fallback replies
- Behavior uses the deterministic offline planner
- All mechanics function normally
