# MainMenu.gd
# This script controls the user interface for the main menu screen.
# Its responsibilities are:
# 1. Handling user input from buttons (Host, Join).
# 2. Interfacing with the NetworkManager autoload singleton to initiate
#    hosting or joining a game session.
# 3. Displaying feedback to the user, such as the Session ID when hosting,
#    or error messages if a connection fails.
# 4. Listening for signals from the NetworkManager to know when to transition
#    to the main game scene.

extends Control

# --- Node References ---
# By using @export, we create fields in the Inspector. This allows us to
# drag and drop the actual nodes from the scene tree onto this script's
# properties, creating a direct and safe reference without hardcoding paths.
@export var singleplayer: Button
@export var host_button: Button
@export var join_button: Button
@export var session_id_input: LineEdit
@export var status_label: Label

# The path to the main game scene. We'll switch to this scene
# once a multiplayer session is successfully established.
const GAME_SCENE_PATH = "res://game.tscn"

# Called when the node enters the scene tree for the first time.
func _ready():
	# --- Connect UI Signals ---
	# Connect the 'pressed' signal of our buttons to their handler functions.
	# This is the standard way to handle UI events in Godot.
	singleplayer.pressed.connect(_on_singleplayer_button_pressed)
	host_button.pressed.connect(_on_host_button_pressed)
	join_button.pressed.connect(_on_join_button_pressed)

	# --- Connect NetworkManager Signals ---
	# We need to listen to the signals from our NetworkManager to react to
	# networking events. This decouples the UI from the networking logic.
	NetworkManager.session_hosted.connect(_on_session_hosted)
	NetworkManager.session_joined.connect(_on_session_joined)
	NetworkManager.network_error.connect(_on_network_error)


# --- UI Signal Handlers ---

# This function is called when the "Host New Session" button is pressed.
func _on_host_button_pressed():
	# Visually disable the buttons to prevent the user from clicking them
	# multiple times while we are attempting to host.
	host_button.disabled = true
	join_button.disabled = true
	session_id_input.editable = false
	status_label.text = "Hosting... Please wait."

	# Call the host_session function in our singleton.
	NetworkManager.host_session()


# This function is called when the "Join Session" button is pressed.
func _on_join_button_pressed():
	# Get the session ID from the input field.
	var oid = session_id_input.text

	# Basic validation to ensure the user entered something.
	if oid.is_empty():
		status_label.text = "Error: Session ID cannot be empty."
		return

	# Disable UI elements to prevent multiple clicks.
	host_button.disabled = true
	join_button.disabled = true
	session_id_input.editable = false
	status_label.text = "Joining session..."
	set_process_input(false)

	# Call the join_session function in our singleton.
	NetworkManager.join_session(oid)

# --- Singleplayer Signal Handlers ---

func _on_singleplayer_button_pressed():
	host_button.disabled = true
	join_button.disabled = true
	session_id_input.editable = false
	status_label.text = "starting Singleplayer..."
	NetworkManager.host_session(true)
	set_process_input(false)

# --- NetworkManager Signal Handlers ---

# This function is called when the NetworkManager successfully hosts a session.
func _on_session_hosted(oid: String):
	# Display the session ID to the user so they can share it.
	status_label.text = "Session hosted! Share this ID: " + oid


# This function is called when the NetworkManager successfully joins a session.
func _on_session_joined():
	# The connection is established. It's time to switch to the game scene.
	status_label.text = "Connected! Loading game..."
	get_tree().change_scene_to_file(GAME_SCENE_PATH)


# This function is called when the NetworkManager encounters an error.
func _on_network_error(message: String):
	# Re-enable the UI so the user can try again.
	host_button.disabled = false
	join_button.disabled = false
	session_id_input.editable = true

	# Display the error message.
	status_label.text = "Error: " + message
