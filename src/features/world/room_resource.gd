# res://src/features/world/room_resource.gd
# This script defines the data structure for a single room or location in the game world.
# By using a custom Resource, we can create, save, and manage room data
# independently from scene files, which is a core part of our data-driven design.
# Each .tres file created from this resource will represent one unique room.
class_name RoomResource
extends Resource

## A unique identifier for the room.
## This is crucial for the WorldDB to look up specific rooms and for other
## resources (like exits) to reference this room.
## Example: "town_square", "dark_forest_1"
@export var id: String = ""

## The short, human-readable name of the room.
## This is what players will see as the primary title for a location.
## Example: "The Town Square", "A Dark Forest Path"
@export var name: String = "A Room"

## The main descriptive text for the room.
## This is the text that will be shown to the player when they use the 'look'
## command. It should be evocative and provide details about the surroundings.
@export_multiline var description: String = "An empty room."

## A dictionary that defines the exits from this room.
## The keys are the directions (e.g., "north", "south", "up", "dungeon").
## The values are the 'id' strings of the connecting RoomResource.
## The command parser will use these keys to handle movement commands.
## Example: {"north": "north_gate", "west": "general_store"}
@export var exits: Dictionary = {}

## An array holding the unique 'id' strings of all ItemResources currently
## located in this room. This list is dynamic; items will be added or removed
## as players drop or get them.
@export var item_ids: Array[String] = []

## An array holding the unique 'id' strings of all PlayerResources (players)
## currently in this room. This list is highly dynamic and will be updated
## every time a player enters or leaves the room.
@export var player_ids: Array[String] = []
