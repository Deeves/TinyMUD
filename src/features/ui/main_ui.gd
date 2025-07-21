# main_ui.gd
# This script should be attached to the root node of your `main_ui.tscn`.
# It is responsible for managing all the nodes within the UI scene.
# Its responsibilities are:
# 1. Managing its own child nodes (text_log, input_line).
# 2. Emitting a signal (`command_submitted`) when the player enters a command.
# 3. Providing a public function (`append_to_log`) that parent scenes can call
#    to display text in the RichTextLabel.

extends Control

# A signal to notify the parent scene (Game.gd) that a command is ready to be sent.
# This allows us to communicate upwards without a hard dependency.
signal command_submitted(text)

# --- Node References ---
# Use @export to link the nodes from within the main_ui.tscn scene.
@export var text_log: RichTextLabel
@export var input_line: LineEdit

# Called when the node enters the scene tree for the first time.
func _ready():
	# Connect the LineEdit's built-in signal to our local handler.
	input_line.text_submitted.connect(_on_input_line_submitted)

# This function is called when the player presses Enter in the input field.
func _on_input_line_submitted(text: String):
	# Clear the input field for the next command.
	input_line.clear()
	# Emit our custom signal, passing the user's text along. The parent
	# scene (Game.gd) will be listening for this.
	emit_signal("command_submitted", text)

# This is a public function that the parent scene (Game.gd) can call.
# It's the proper way to allow outside scenes to interact with this UI.
func append_to_log(message: String):
	# Append the text from the host to our on-screen log.
	# We add a newline character to ensure each message is on its own line.
	text_log.append_text(message + "\n")
