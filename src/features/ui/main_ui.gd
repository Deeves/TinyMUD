# res://src/features/ui/main_ui.gd
# This script controls the main game user interface. It is responsible for
# capturing user input, sending it to the command parser, and displaying
# the results in the text log.
extends Control

# We'll get direct references to our UI nodes using the %-notation for convenience.
@onready var text_log: RichTextLabel = %TextLog
@onready var input_line: LineEdit = %InputLine

# A placeholder for the player's unique ID. In a single-player context, this
# can be anything. Once networking is implemented, this will be assigned by the host.
const FAKE_PLAYER_ID = "player_1"


# The _ready function is called when the scene is initialized.
# This is the perfect place to set up our signal connection.
func _ready() -> void:
	# Connect the LineEdit's 'text_submitted' signal to our handler function.
	# This means whenever the user presses Enter in the input field,
	# the _on_input_submitted function will be called.
	input_line.text_submitted.connect(_on_input_submitted)

	# Set the initial focus to the input line so the player can start typing immediately.
	input_line.grab_focus()

	# Display a welcome message.
	log_message("[color=aqua]Welcome to the MUD Revival MVP![/color]")
	log_message("Type 'look' to see your surroundings.")


# This function is the signal handler for the input line.
func _on_input_submitted(text: String) -> void:
	# First, echo the player's command to the log so they can see what they typed.
	log_message("[color=gray]> %s[/color]" % text)

	# Pass the command to the parser for processing. The parser will return a
	# string (or null if there's no output).
	var response = CommandParser.parse_command(FAKE_PLAYER_ID, text)

	# If the parser returned a message, log it.
	if response:
		log_message(response)

	# Clear the input line for the next command.
	input_line.clear()
	# Re-focus the input line in case the user clicked elsewhere.
	input_line.grab_focus()


# A helper function to append messages to our RichTextLabel.
func log_message(message: String) -> void:
	# append_text handles BBCode parsing and adds a newline automatically.
	text_log.append_text(message)
