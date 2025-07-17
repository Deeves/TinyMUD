# res://src/features/player/player_resource.gd
# This script defines the data structure for a player's character state.
# It holds all the essential information about a player that needs to be tracked
# across the game world and saved. Note that this is purely data; the player's
# in-game representation (the node) will be a separate scene.
class_name PlayerResource
extends Resource

## The unique network ID assigned to the player by Godot's MultiplayerAPI
## when they connect to the session host. This is the definitive identifier
## for a player during a game session. It's typically an integer.
@export var id: int = -1

## The player's chosen character name.
## This is the public-facing name that other players will see in the game.
## Example: "Gandalf", "PlayerOne"
@export var name: String = "Adventurer"

## The 'id' of the RoomResource where the player is currently located.
## This is a critical piece of state that will be updated every time the
## player successfully moves from one room to another.
@export var location_id: String = ""

## An array holding the unique 'id' strings of all ItemResources that the
## player is currently carrying in their inventory.
@export var inventory_ids: Array[String] = []

## A dictionary to hold basic character stats.
## For the MVP, this might just be a placeholder, but it establishes the
## pattern for future expansion with stats like health, mana, strength, etc.
## Example: {"health": 100, "max_health": 100}
@export var stats: Dictionary = {}
