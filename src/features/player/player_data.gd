# src/features/player/player_data.gd
class_name PlayerData
extends Resource

@export var id: int
@export var player_name: String
# Every player will start in the "town_square" for now.
@export var location_id: String = "town_square"
