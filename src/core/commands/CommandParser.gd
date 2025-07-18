# res://src/core/commands/command_parser.gd
# This autoload singleton is the heart of the MUD's interactivity. It is
# responsible for taking raw text input from a player, parsing it into a
# recognizable command and its arguments, and then dispatching it to the
# appropriate handler function for execution.
extends Node

# We need access to the WorldDB to query and modify game state.
@onready var world_db: WorldDB = get_node("/root/WorldDB")

# A set of all verbs that are treated as movement commands. Using a PackedStringArray
# allows for a fast 'has()' check.
const MOVEMENT_VERBS = ["north", "n", "south", "s", "east", "e", "west", "w", "northeast", "ne", "northwest", "nw", "southeast", "se", "southwest", "sw", "up", "u", "down", "d"]

# The command_map is a dictionary that links command strings (and their aliases)
# to the functions that will handle them. This makes the system highly extensible.
# Adding a new command is as simple as adding a new entry to this map.
var command_map: Dictionary = {
	# Observation
	"look": _handle_look, "l": _handle_look,
	# Interaction
	"get": _handle_get, "g": _handle_get, "take": _handle_get,
	"drop": _handle_drop,
	# Communication
	"say": _handle_say, "'": _handle_say,
	"tell": _handle_tell,
	"shout": _handle_shout,
	# Information
	"who": _handle_who,
	"inventory": _handle_inventory, "i": _handle_inventory, "inv": _handle_inventory,
	"score": _handle_score, "stat": _handle_score,
}


# This is the main entry point for the parser. It takes a player's ID and
# the full text of their command. It now returns a string to be displayed.
func parse_command(player_id: String, input_text: String) -> String:
	var sanitized_input = input_text.strip_edges()
	if sanitized_input.is_empty():
		return ""

	var tokens: Array[String] = sanitized_input.split(" ", false)
	var verb: String = tokens[0].to_lower()
	var args: Array[String] = tokens.slice(1)

	if MOVEMENT_VERBS.has(verb):
		return _handle_move(player_id, [verb])

	if command_map.has(verb):
		var handler_func: Callable = command_map[verb]
		# The 'call' method will return the value from the called function.
		return handler_func.call(player_id, args)
	else:
		# Return a formatted error message for unknown commands.
		return "[color=red]I don't know how to '%s'.[/color]" % verb


# --- COMMAND HANDLER FUNCTIONS ---
# These functions now return BBCode-formatted strings for the UI.
# The logic is still placeholder, but the return type is correct for Phase 3.

func _handle_look(player_id: String, args: Array[String]) -> String:
	return "You look around. Everything is still under construction."

func _handle_get(player_id: String, args: Array[String]) -> String:
	if args.is_empty():
		return "[color=orange]What do you want to get?[/color]"
	return "You try to get the %s." % args[0]

func _handle_drop(player_id: String, args: Array[String]) -> String:
	if args.is_empty():
		return "[color=orange]What do you want to drop?[/color]"
	return "You drop the %s." % args[0]

func _handle_say(player_id: String, args: Array[String]) -> String:
	if args.is_empty():
		return "[color=orange]What do you want to say?[/color]"
	var message = " ".join(args)
	# In a real game, this would be broadcast to others.
	return "You say, '[color=yellow]%s[/color]'" % message

func _handle_tell(player_id: String, args: Array[String]) -> String:
	if args.size() < 2:
		return "[color=orange]Who do you want to tell, and what do you want to say?[/color]"
	var target_player_name = args[0]
	var message = " ".join(args.slice(1))
	return "You tell %s, '[color=cyan]%s[/color]'" % [target_player_name, message]

func _handle_shout(player_id: String, args: Array[String]) -> String:
	if args.is_empty():
		return "[color=orange]What do you want to shout?[/color]"
	var message = " ".join(args)
	return "You shout, '[color=red]%s[/color]'!" % message

func _handle_who(player_id: String, args: Array[String]) -> String:
	return "[color=aqua]You are the only one online.[/color]"

func _handle_inventory(player_id: String, args: Array[String]) -> String:
	return "You are not carrying anything."

func _handle_score(player_id: String, args: Array[String]) -> String:
	return "[color=gold]You are a mighty adventurer, destined for greatness.[/color]"

func _handle_move(player_id: String, args: Array[String]) -> String:
	var direction = args[0]
	# In the future, this will trigger a room change and a new 'look' description.
	return "You walk %s." % direction
