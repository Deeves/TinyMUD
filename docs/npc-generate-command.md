# /npc generate Command

## Overview

The `/npc generate` command creates fully-statted NPCs using the Nexus System (GURPS + FATE + SWN). It supports two modes:

1. **Contextual Mode** - Generates an NPC that fits the player's current room and world
2. **Explicit Mode** - Generates an NPC with specified details for a specific room

## Contextual Mode (Recommended)

**Usage:** `/npc generate`

Simply type `/npc generate` while standing in any room. The AI will:
- Analyze the world setting (name, description, conflict)
- Examine the current room's description
- Consider existing NPCs in the room
- Generate a complementary NPC that fits naturally

**Example:**
```
You are in: smithy - A hot, noisy workshop filled with the clang of hammers on anvils.
> /npc generate

[System] Generating contextual NPC for smithy... please wait.
[System] NPC 'Gareth the Smith' generated with full Nexus stats in smithy.
```

**What Gets Generated:**
- **Name** - Contextually appropriate to the setting
- **Description** - 1-3 sentences about who they are
- **FATE Aspects**:
  - High Concept (e.g., "Master of the Forge")
  - Trouble (e.g., "Too Trusting of Strangers")
  - Background (SWN style, e.g., "Craftsman")
  - Focus (SWN style, e.g., "Armorer")
- **GURPS Attributes** (3-18, avg 10):
  - Strength, Dexterity, Intelligence, Health
- **Advantages** (max 40 points total)
- **Disadvantages** (max -40 points total)
- **Quirks** (max 5, worth -1 each)
- **Psychosocial Matrix** (11 axes, -10 to +10 each)

## Explicit Mode

**Usage:** `/npc generate <room name> | <npc name> | <description>`

Specify the room, name, and a brief description. The AI fills in the rest.

**Example:**
```
> /npc generate tavern | Mira the Innkeeper | A cheerful woman who knows everyone's secrets

[System] Generating Nexus profile for 'Mira the Innkeeper'... please wait.
[System] NPC 'Mira the Innkeeper' generated with full Nexus stats in tavern.
```

## Viewing the Generated NPC

Use `/npc sheet <name>` to view the complete character sheet:

```
> /npc sheet Gareth the Smith

Gareth the Smith
A burly blacksmith with soot-stained hands and a friendly demeanor.
High Concept: Master of the Forge
Trouble: Too Trusting of Strangers
Background: Craftsman  Focus: Armorer
ST: 14 DX: 10 IQ: 11 HT: 13
HP: 14/14 Will: 11 Per: 11 FP: 13/13
Matrix:
  Auth/Egal: -3  Cons/Lib: 2
  Ego/Alt: -2  Rat/Rom: 1
```

## Point Allocation Rules

The command automatically enforces Nexus System rules:

1. **Advantages**: Total cost ≤ 40 points
   - Example: Fit (5) + Craftsman (10) + Combat Reflexes (15) = 30 points ✓
   - If AI suggests 55 points, only the first 40 are applied

2. **Disadvantages**: Total cost ≥ -40 points
   - Example: Truthfulness (-5) + Greed (-15) = -20 points ✓

3. **Quirks**: Maximum 5 quirks
   - Each worth -1 point
   - Example: ["Hums while working", "Prefers ale to wine"] ✓

4. **Psychosocial Matrix**: All axes clamped to -10 to +10
   - If AI returns out-of-range values (e.g., 50), they're clamped to valid range

## Psychosocial Matrix Axes

The 11 axes represent personality and worldview:

1. **sexuality_hom_het** - Sexual orientation spectrum
2. **physical_presentation_mas_fem** - Physical gender presentation
3. **social_presentation_mas_fem** - Social gender presentation
4. **auth_egal** - Authoritarian ↔ Egalitarian
5. **cons_lib** - Conservative ↔ Liberal
6. **spirit_mat** - Spiritual ↔ Materialistic
7. **ego_alt** - Egotistical ↔ Altruistic
8. **hed_asc** - Hedonistic ↔ Ascetic
9. **nih_mor** - Nihilistic ↔ Moralistic
10. **rat_rom** - Rational ↔ Romantic
11. **ske_abso** - Skeptical ↔ Absolutist

Each axis ranges from -10 (strongly left) to +10 (strongly right).

## Requirements

- Requires a valid Gemini API key (`GEMINI_API_KEY` or `GOOGLE_API_KEY` environment variable)
- Player must be logged in for contextual mode
- Admin privileges required

## Error Handling

**No API Key:**
```
[Error] AI generation is not available (no API key configured).
```

**Not logged in (contextual mode):**
```
[Error] You must be logged in to use contextual generation.
```

**Invalid room:**
```
[Error] Room 'xyz' not found.
```

## Tips

1. **Contextual mode is smarter** - It considers existing NPCs and avoids duplicates
2. **Use world setup first** - Set world name/description via `/setup` for better context
3. **Review and edit** - Use `/npc setattr`, `/npc setaspect`, `/npc setmatrix` to fine-tune
4. **Check relationships** - Use `/npc setrelation` to link NPCs after generation

## Related Commands

- `/npc add <room> | <name> | <description>` - Create basic NPC without stats
- `/npc setattr <name> | <attribute> | <value>` - Modify GURPS attributes
- `/npc setaspect <name> | <type> | <value>` - Modify FATE aspects
- `/npc setmatrix <name> | <axis> | <value>` - Modify psychosocial matrix
- `/npc sheet <name>` - View complete character sheet
- `/npc familygen <room> | <target npc> | <relationship>` - Generate related NPCs

## Technical Details

The command uses Google's Gemini AI model to generate character profiles based on:
- World metadata (name, description, conflict)
- Room description and atmosphere
- Existing NPCs in the room (to avoid redundancy)
- World safety level setting (G, PG-13, R, OFF)

Generated NPCs are fully integrated into the world's NPC system with:
- Stable UUID for persistence
- Full CharacterSheet data structure
- Automatic placement in the specified room
- Derived stats calculated (HP, Will, Perception, FP)
