# Game.gd
# This script manages the main game scene (game.tscn) and acts as a bridge
# between the UI and the core networking logic.
# Its responsibilities are:
# 1. Listening for commands submitted by the UI scene.
# 2. Sending those commands to the host via RPC.
# 3. Receiving log messages from the host via RPC and passing them to the UI.

extends Node2D

# --- Node References ---
# We now only need a reference to the main UI scene instance itself.
@export var main_ui: Control

# Called when the node enters the scene tree for the first time.
#func _ready():
	# Connect to the UI's custom signal. When the UI emits `command_submitted`,
	# our `_on_command_submitted` function will be called.
#	main_ui.command_submitted.connect(_on_command_submitted)


# This function is called when the main_ui scene emits its `command_submitted` signal.
func _on_command_submitted(text: String):
	# The UI has told us a command is ready. We send it to the host (ID=1).
	CommandParser.rpc_id(1, "parse_command", text)


# --- RPC Function ---
# This function is designed to be called BY the host ON this client.
# `call_local`: Ensures this function only runs on the client it's sent to.
@rpc("call_local", "reliable")
func log_message(message: String):
	# The host has sent us a message. We call a function on our UI scene
	# to handle the actual display of the text.
	main_ui.append_to_log(message)
