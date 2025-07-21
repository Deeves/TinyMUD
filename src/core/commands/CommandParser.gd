# CommandParser.gd
# This singleton is the heart of the MUD's user interface, translating player
# input into game actions. In our multiplayer architecture, its role is now
# split: it receives commands from clients via RPC and executes them
# authoritatively on the host.

extends Node

# --- RPC Function ---
# This is the new entry point for all player commands. The `@rpc` decorator
# allows it to be called from clients.
# `any_peer`: Allows any peer (client) to call this function on the host.
# `reliable`: Ensures the call is reliable and ordered.
@rpc("any_peer", "reliable")
func parse_command(input_text: String):
	# SECURITY: This is the most critical check. We ensure that only the host
	# (the server) can ever run the game logic. If a client somehow tried to
	# call this on themselves, this check would prevent it.
	if not multiplayer.is_server():
		return

	# The player_id is the unique network ID of the peer who sent this RPC.
	var player_id = multiplayer.get_remote_sender_id()

	# The rest of the parsing logic remains similar to our single-player version.
	var tokens = input_text.strip_edges().split(" ", false)
	if tokens.is_empty():
		return

	var verb = tokens[0].to_lower()
	# TODO: Implement the command_map and handler functions.
	# For now, we will just echo the command back to the player.

	var response = "You typed: " + input_text

	# Instead of returning the result, the host now sends it back to the
	# specific client who issued the command using another RPC.
	Game.rpc_id(player_id, "log_message", response)


# --- Example Command Handler (to be expanded in Phase 5) ---
# func _handle_look(player_id, args):
#     if not multiplayer.is_server(): return
#
#     # 1. Get player's current room from WorldDB.
#     # 2. Get the room's description.
#     # 3. Get lists of players and items in the room.
#     # 4. Format all of this into a single string.
#     var description_string = "You are in a room..."
#
#     # 5. Send the final string back to ONLY the player who typed "look".
#     Game.rpc_id(player_id, "log_message", description_string)
