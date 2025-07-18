# res://src/features/ui/main_ui.gd
# This script controls the main game user interface. It is responsible for
# capturing user input, sending it to the command parser, and displaying
# the results in the text log and map view.
#
# REFACTOR: This script is now "stateless." It does not track the player's
# location itself. Instead, it relies on WorldDB as the single source of truth
# and uses the CommandParser to fetch the current state.
extends Control

@onready var text_log: RichTextLabel = %TextLog
@onready var input_line: LineEdit = %InputLine
@onready var map_view: Control = %MapView

@onready var world_db: WorldDB = get_node("/root/WorldDB")

# This flag prevents the parser from running until the database is ready.
var is_ready = false

# The ID for our player in this single-player session.
const PLAYER_ID = "player_1"

func _ready():
	# Wait for the WorldDB to finish loading before allowing commands.
	await world_db.database_ready
	is_ready = true
	print("CommandParser is ready.")

	input_line.text_submitted.connect(_on_input_submitted)
	input_line.grab_focus()

	log_message("[color=aqua]Welcome to the MUD Revival MVP![/color]")

	# Perform an initial "look" to show the player where they are.
	_update_view()


func _on_input_submitted(text: String) -> void:
	if text.is_empty():
		return

	log_message("\n[color=gray]> %s[/color]" % text)

	# The parser now handles all logic and returns the result.
	var response = CommandParser.parse_command(PLAYER_ID, text)

	if response:
		log_message(response)

	# After every command, refresh the view to show any changes.
	_update_view()

	input_line.clear()
	input_line.grab_focus()


func log_message(message: String) -> void:
	text_log.append_text(message)
	text_log.scroll_to_end()


# This function now gets all its information from the WorldDB.
func _update_view() -> void:
	# Get the player's current data from the database.
	var player: PlayerResource = world_db.players.get(PLAYER_ID)
	if not player: return

	# Get the player's current room data.
	var room: RoomResource = world_db.rooms.get(player.location_id)
	if not room:
		log_message("[color=red]ERROR: Current room '%s' not found![/color]" % player.location_id)
		return

	# Tell the map view to draw the room and the player.
	# For now, we'll just put the player in the center of the map view.
	# A more advanced system could define specific coordinates in the RoomResource.
	var map_center = map_view.tile_map.get_used_rect().get_center()
	map_view.draw_room(room)
	map_view.update_player_position(map_center)
