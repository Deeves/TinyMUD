# Game.gd
# This script manages the main game UI (game.tscn).
# Its responsibilities are:
# 1. Capturing player input from the LineEdit.
# 2. Sending the typed command to the host for processing via an RPC.
# 3. Providing an RPC-callable function (`log_message`) for the host to send
#    text back to this client.
# 4. Displaying received messages in the RichTextLabel.

extends Node2D

# --- Node References ---
# Use @export to link these nodes from the editor's Inspector.
@export var text_log: RichTextLabel
@export var input_line: LineEdit

# Called when the node enters the scene tree for the first time.
func _ready():
	# Connect the LineEdit's signal to our handler function.
	input_line.text_submitted.connect(_on_input_submitted)

	# Make this script globally accessible via the "Game" autoload name.
	# This allows the CommandParser to easily call RPCs on it.
	# Note: You must add "Game" as an autoload in Project Settings,
	# pointing to this script file.


# This function is called when the player presses Enter in the input field.
func _on_input_submitted(text: String):
	# The input field should be cleared immediately for the next command.
	input_line.clear()

	# Instead of processing the command locally, we send it to the host (ID=1).
	# We call the `parse_command` function that we defined in CommandParser.gd.
	# The multiplayer API handles sending this over the network.
	CommandParser.rpc_id(1, "parse_command", text)


# --- RPC Function ---
# This function is designed to be called BY the host ON this client.
# `call_local`: Ensures this function only runs on the client it's sent to.
@rpc("call_local", "reliable")
func log_message(message: String):
	# Append the text from the host to our on-screen log.
	# We add a newline character to ensure each message is on its own line.
	text_log.append_text(message + "\n")
