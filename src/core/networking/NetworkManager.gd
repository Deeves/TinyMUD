# res://src/core/networking/NetworkManager.gd
# This script serves as the network manager for the MUD game.
# It handles all network-related functionality including connections,
# data transmission, and synchronization between clients and server.
extends Node

func _ready() -> void:
	print("NetworkManager initialized")

# Add your networking code here
# For example:
# func start_server(port: int) -> void:
#     pass
#
# func connect_to_server(address: String, port: int) -> void:
#     pass
