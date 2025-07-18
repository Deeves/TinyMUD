# res://src/core/world/world_db.gd
# This autoload singleton acts as the central, in-memory database for the
# entire game world. It holds dictionaries of all loaded rooms, items, and
# active players. All other systems (CommandParser, NetworkManager, etc.)
# will interact with this singleton to query and modify the game state.
# This centralized approach is essential for maintaining a single,
# authoritative source of truth on the session host.
class_name WorldDB
extends Node

# This signal is emitted after all resources have been loaded into the
# dictionaries. Other nodes can wait for this signal to safely access the data.
signal database_ready

# Master dictionary for all RoomResources, keyed by their unique 'id'.
var rooms: Dictionary = {}

# Master dictionary for all ItemResources, keyed by their unique 'id'.
var items: Dictionary = {}

# Master dictionary for all active PlayerResources, keyed by their unique 'id'.
var players: Dictionary = {}

# The file paths where the resource definitions are stored.
# By centralizing these paths, we make it easy to manage our project structure.
const ROOM_DEFINITIONS_PATH = "res://src/features/world/definitions/"
const ITEM_DEFINITIONS_PATH = "res://src/features/items/definitions/"


# _ready() is called when the node (and the game) starts.
# We use it to kick off the process of loading all our world data.
func _ready() -> void:
	print("WorldDB: Initializing and loading resources...")
	_load_resources_from_path(ROOM_DEFINITIONS_PATH, rooms)
	_load_resources_from_path(ITEM_DEFINITIONS_PATH, items)
	print("WorldDB: %d rooms and %d items loaded." % [rooms.size(), items.size()])

	# After all loading is complete, emit the signal.
	emit_signal("database_ready")


# A generic helper function to load all .tres resource files from a given path.
# It iterates through a directory, loads each resource, and stores it in the
# provided dictionary, using the resource's 'id' property as the key.
# This makes our data loading system scalable and easy to manage.
func _load_resources_from_path(path: String, dictionary: Dictionary) -> void:
	# Use DirAccess to open the specified directory.
	var dir = DirAccess.open(path)
	if dir:
		# Start iterating through the directory contents.
		dir.list_dir_begin()
		var file_name = dir.get_next()
		while file_name != "":
			# We only care about .tres files, and we must ignore import metadata files.
			if not dir.current_is_dir() and file_name.ends_with(".tres"):
				# Load the resource from the disk.
				var resource = load(path.path_join(file_name))
				# Check if the resource and its ID are valid before adding it.
				if resource and resource.get("id") != null and resource.id != "":
					dictionary[resource.id] = resource
				else:
					# This is a critical error. A resource file is invalid.
					push_error("Failed to load resource or resource has invalid ID: %s" % path.path_join(file_name))

			# Move to the next file in the directory.
			file_name = dir.get_next()
	else:
		# This error indicates a problem with the project's directory structure.
		push_error("Could not open resource directory: %s" % path)
