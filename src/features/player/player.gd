# Player.gd
# This script is attached to the root node of our player.tscn scene.
# It represents a single player in the game world.
# Its responsibilities are:
# 1. Holding player-specific data, like their name and network ID.
# 2. Managing the visual representation of the player (e.g., their '@' icon).
# 3. Synchronizing its state across the network via a MultiplayerSynchronizer.

extends Node2D

# This variable will hold the player's unique network ID.
# We will mark it to be synchronized across the network.
var player_id: int

# This variable will hold the player's chosen name.
# We will also synchronize this.
var player_name: String = "Player"


# This function is called by the MultiplayerSpawner on the host right after
# a new player scene is instantiated. We use it to pass initial data
# to the new player instance.
func _spawn(data):
	# The data dictionary is passed from the spawner.
	# We expect it to contain the new player's ID and name.
	self.player_id = data.player_id
	self.player_name = data.player_name

	# We can use the player's ID to name the node in the scene tree,
	# which is very helpful for debugging.
	self.name = "Player_" + str(player_id)
