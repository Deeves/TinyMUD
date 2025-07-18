# res://src/features/ui/map_view.gd
# This script controls the graphical map view. Its primary responsibility
# is to take a RoomResource and render its 'layout' property onto a TileMap.
extends Control

# A reference to the TileMap node within the SubViewport.
@onready var tile_map: TileMap = %TileMap

# These constants define which tile coordinates in our TileSet correspond to
# which character. This mapping is essential for the draw_room function.
# You will need to adjust these Vector2i values to match your specific
# ascii_tileset.tres resource after you create it.
const TILE_FLOOR = Vector2i(14, 2)  # Placeholder: The tile for '.'
const TILE_WALL = Vector2i(3, 2)   # Placeholder: The tile for '#'
const TILE_PLAYER = Vector2i(0, 4) # Placeholder: The tile for '@'


# This is the main public function for this scene. It takes a RoomResource,
# clears the old map, and draws the new one based on the room's layout.
func draw_room(room_data: RoomResource) -> void:
	# It's crucial to clear the existing tiles before drawing a new room.
	tile_map.clear()

	# Get the layout from the provided room resource.
	var layout: PackedStringArray = room_data.layout
	if layout.is_empty():
		return # Don't try to draw an empty layout.

	# Iterate over the layout array. 'y' represents the row index.
	for y in range(layout.size()):
		# 'line' is the string for the current row, e.g., "#######"
		var line: String = layout[y]
		# Iterate over the characters in the line. 'x' is the column index.
		for x in range(line.length()):
			var char = line[x]
			var tile_coord = Vector2i(x, y)

			# Use a match statement to determine which tile to place.
			match char:
				'#':
					# Layer 0 is for the terrain (walls, floors).
					# TILE_WALL is the coordinate of the wall tile in our atlas.
					tile_map.set_cell(0, tile_coord, 0, TILE_WALL)
				'.':
					tile_map.set_cell(0, tile_coord, 0, TILE_FLOOR)
				# We can add more cases here for other characters like doors, water, etc.

# This function will be called to place the player's '@' icon on the map.
# It's separate from draw_room because the player's position can change
# without the room itself changing.
func update_player_position(position: Vector2i) -> void:
	# Layer 1 is for entities (players, items, NPCs).
	# This ensures the player icon draws on top of the floor tile.
	tile_map.set_cell(1, position, 0, TILE_PLAYER)
