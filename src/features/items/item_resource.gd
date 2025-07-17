# res://src/features/items/item_resource.gd
# This script defines the data structure for all interactive items in the game.
# Using a Resource allows us to define a "template" for each type of item,
# which can then be instanced or referenced throughout the world.
# Each .tres file will be a unique item blueprint.
class_name ItemResource
extends Resource

## The unique identifier for this specific item.
## This is used by the WorldDB to track the item's location, whether it's
## in a room or in a player's inventory.
## Example: "rusty_sword_01", "health_potion_001"
@export var id: String = ""

## The short, human-readable name of the item.
## This is how the item will appear in lists (like inventories or room contents).
## Example: "a rusty sword", "a glowing potion"
@export var name: String = "An item"

## The detailed description of the item.
## This text is shown to the player when they 'look' at the item specifically.
@export_multiline var description: String = "A non-descript item."

## An array of keywords that the command parser can use to identify this item.
## This allows players to refer to items in different ways (e.g., "get sword",
## "get rusty sword", "get blade"). All keywords should be lowercase.
## Example: ["sword", "rusty", "blade"]
@export var keywords: Array[String] = []

## A dictionary of properties or flags for this item.
## This provides a flexible way to add boolean states or other data to items
## without changing the core script. It's essential for future expansion.
## Example: {"can_be_taken": true, "is_edible": false, "light_source": true}
@export var properties: Dictionary = {"can_be_taken": true}
