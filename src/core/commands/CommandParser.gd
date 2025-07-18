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
# the full text of their command. It then tokenizes the input and attempts
# to execute the command.
func parse_command(player_id: String, input_text: String) -> void:
	# Sanitize the input by removing leading/trailing whitespace.
	var sanitized_input = input_text.strip_edges()
	if sanitized_input.is_empty():
		return # Ignore empty commands.

	# Tokenize the input string into an array of words.
	var tokens: Array[String] = sanitized_input.split(" ", false)
	var verb: String = tokens[0].to_lower()
	var args: Array[String] = tokens.slice(1)

	# Check if the verb is a movement command first.
	if MOVEMENT_VERBS.has(verb):
		_handle_move(player_id, [verb])
		return

	# Check if the verb exists in our main command map.
	if command_map.has(verb):
		var handler_func: Callable = command_map[verb]
		handler_func.call(player_id, args)
	else:
		# If the command is not found, we'll eventually send an error to the player.
		# This is the ONLY place where 'verb' can be safely used for this message.
		print("Player '%s' issued unknown command: '%s'" % [player_id, verb])


# --- COMMAND HANDLER FUNCTIONS ---
# For now, these are placeholders that print to the console. This allows us
# to test the core logic without a UI. In Phase 3, these will be updated
# to return formatted strings for the RichTextLabel.

func _handle_look(player_id: String, args: Array[String]) -> void:
	print("Player '%s' is looking. Args: %s" % [player_id, args])

func _handle_get(player_id: String, args: Array[String]) -> void:
	if args.is_empty():
		print("Player '%s' needs to specify what to get." % player_id)
		return
	print("Player '%s' is getting. Args: %s" % [player_id, args])

func _handle_drop(player_id: String, args: Array[String]) -> void:
	if args.is_empty():
		print("Player '%s' needs to specify what to drop." % player_id)
		return
	print("Player '%s' is dropping. Args: %s" % [player_id, args])

func _handle_say(player_id: String, args: Array[String]) -> void:
	if args.is_empty():
		print("Player '%s' needs to specify what to say." % player_id)
		return
	var message = " ".join(args)
	print("Player '%s' says: '%s'" % [player_id, message])

func _handle_tell(player_id: String, args: Array[String]) -> void:
	if args.size() < 2:
		print("Player '%s' tried to tell, but format is wrong. (tell <player> <message>)" % player_id)
		return
	var target_player_name = args[0]
	var message = " ".join(args.slice(1))
	print("Player '%s' tells '%s': '%s'" % [player_id, target_player_name, message])

func _handle_shout(player_id: String, args: Array[String]) -> void:
	if args.is_empty():
		print("Player '%s' needs to specify what to shout." % player_id)
		return
	var message = " ".join(args)
	print("Player '%s' shouts: '%s'" % [player_id, message])

func _handle_who(player_id: String, args: Array[String]) -> void:
	print("Player '%s' requests player list. Args: %s" % [player_id, args])

func _handle_inventory(player_id: String, args: Array[String]) -> void:
	print("Player '%s' requests inventory. Args: %s" % [player_id, args])

func _handle_score(player_id: String, args: Array[String]) -> void:
	print("Player '%s' requests score. Args: %s" % [player_id, args])

func _handle_move(player_id: String, args: Array[String]) -> void:
	var direction = args[0]
	print("Player '%s' is moving %s." % [player_id, direction])
