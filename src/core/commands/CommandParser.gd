# res://src/core/commands/command_parser.gd
# REFACTOR: This version contains the live game logic for the MVP.
# It now waits for the WorldDB to be ready before processing commands.
extends Node

# Get a reference to the WorldDB singleton by its global name.
# This is more robust than get_node() and avoids load-order issues.
@onready var world_db = get_node("/root/WorldDb")  # Note: lowercase 'b' to match project.godot

# This flag prevents the parser from running until the database is ready.
var is_ready = false

const MOVEMENT_VERBS = ["north", "n", "south", "s", "east", "e", "west", "w", "northeast", "ne", "northwest", "nw", "southeast", "se", "southwest", "sw", "up", "u", "down", "d"]

var command_map: Dictionary = {
	"look": _handle_look, "l": _handle_look,
	"get": _handle_get, "g": _handle_get, "take": _handle_get,
	"drop": _handle_drop,
	"inventory": _handle_inventory, "i": _handle_inventory, "inv": _handle_inventory,
	# Other commands will be added here.
}

func _ready():
	# Wait for the WorldDB to finish loading before allowing commands.
	await world_db.database_ready
	is_ready = true
	print("CommandParser is ready.")


func parse_command(player_id: String, input_text: String) -> String:
	# If the database isn't ready, don't process any commands.
	if not is_ready:
		return "[color=orange]World database is still loading...[/color]"

	var sanitized_input = input_text.strip_edges()
	if sanitized_input.is_empty(): return ""

	var tokens: Array[String] = sanitized_input.split(" ", false)
	var verb: String = tokens[0].to_lower()
	var args: Array[String] = tokens.slice(1)

	if MOVEMENT_VERBS.has(verb):
		return _handle_move(player_id, verb)

	if command_map.has(verb):
		var handler_func: Callable = command_map[verb]
		return handler_func.call(player_id, args)
	else:
		return "[color=red]I don't know how to '%s'.[/color]" % verb

# --- Live Command Handler Functions ---

func _handle_look(player_id: String, args: Array[String]) -> String:
	var player: PlayerResource = world_db.players.get(player_id)
	if not player: return "[color=red]Error: Player not found.[/color]"

	var room: RoomResource = world_db.rooms.get(player.location_id)
	if not room: return "[color=red]Error: Room not found.[/color]"

	# Build the room description string.
	var result = ""
	result += "[b][color=white]%s[/color][/b]\n" % room.name
	result += "  %s\n" % room.description

	# List items in the room.
	if not room.item_ids.is_empty():
		result += "[color=lime]You also see:[/color]\n"
		for item_id in room.item_ids:
			var item_res: ItemResource = world_db.items.get(item_id)
			if item_res:
				result += "  - %s\n" % item_res.name

	# List exits.
	if not room.exits.is_empty():
		var exit_list = ", ".join(room.exits.keys())
		result += "[color=cyan]Exits: %s[/color]" % exit_list

	return result

func _handle_move(player_id: String, direction: String) -> String:
	var player: PlayerResource = world_db.players.get(player_id)
	var room: RoomResource = world_db.rooms.get(player.location_id)

	# Check if the exit exists.
	if not direction in room.exits:
		return "[color=red]You can't go that way.[/color]"

	# Get the destination room ID.
	var destination_id = room.exits[direction]
	if not world_db.rooms.has(destination_id):
		return "[color=red]Error: That exit leads nowhere.[/color]"

	# Update the player's location.
	player.location_id = destination_id

	# Return the description of the new room.
	return _handle_look(player_id, [])

func _handle_inventory(player_id: String, args: Array[String]) -> String:
	var player: PlayerResource = world_db.players.get(player_id)
	if player.inventory_ids.is_empty():
		return "You are not carrying anything."

	var result = "You are carrying:\n"
	for item_id in player.inventory_ids:
		var item_res: ItemResource = world_db.items.get(item_id)
		if item_res:
			result += "  - %s\n" % item_res.name
	return result

func _handle_get(player_id: String, args: Array[String]) -> String:
	if args.is_empty(): return "[color=orange]What do you want to get?[/color]"

	var player: PlayerResource = world_db.players.get(player_id)
	var room: RoomResource = world_db.rooms.get(player.location_id)
	var target_keyword = args[0].to_lower()

	# Find the item in the room.
	for item_id in room.item_ids:
		var item_res: ItemResource = world_db.items.get(item_id)
		if item_res and target_keyword in item_res.keywords:
			# Move item from room to player.
			room.item_ids.erase(item_id)
			player.inventory_ids.append(item_id)
			return "You take the %s." % item_res.name

	return "You don't see that here."

func _handle_drop(player_id: String, args: Array[String]) -> String:
	if args.is_empty(): return "[color=orange]What do you want to drop?[/color]"

	var player: PlayerResource = world_db.players.get(player_id)
	var room: RoomResource = world_db.rooms.get(player.location_id)
	var target_keyword = args[0].to_lower()

	# Find the item in the player's inventory.
	for item_id in player.inventory_ids:
		var item_res: ItemResource = world_db.items.get(item_id)
		if item_res and target_keyword in item_res.keywords:
			# Move item from player to room.
			player.inventory_ids.erase(item_id)
			room.item_ids.append(item_id)
			return "You drop the %s." % item_res.name

	return "You don't have that."
