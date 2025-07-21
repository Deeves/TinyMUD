# NetworkManager.gd
# This autoload singleton is the central hub for all networking operations in TinyMUD.
# Its primary responsibilities are:
# 1. Establishing and maintaining a connection to the Noray orchestration server.
# 2. Managing the lifecycle of a game session, including hosting and joining.
# 3. Providing a clear interface for the rest of the game to interact with the
#    networking layer, abstracting away the complexities of the underlying
#    `netfox.noray` addon.
# By centralizing this logic, we ensure that networking code is organized,
# reusable, and easier to debug.

extends Node

# A signal to notify the game when a session has been successfully hosted.
# We'll emit this once Noray provides us with a public OpenID (oid).
# The UI will listen for this signal to display the oid to be shared.
signal session_hosted(oid)

# A signal to notify the game that we have successfully connected to a host.
# This tells the UI it's time to switch from the main menu to the game scene.
signal session_joined

# A signal to handle and display networking-related errors to the user.
# This is crucial for providing feedback if a connection fails.
signal network_error(message)

# According to the blueprint, we will use the public Noray server for development.
# This avoids the need to self-host an orchestrator during the MVP phase.
const NORAY_SERVER_URL = "tomfol.io"
const NORAY_SERVER_PORT = 8890

# A reference to the `Noray` singleton provided by the `netfox.noray` addon.
# We get this once, on initialization, to interact with the Noray service.
var noray

# Called when the node enters the scene tree for the first time.
# As an autoload singleton, this runs once when the game starts.
func _ready():
	# It's good practice to check if the addon's singleton is available.
	# This prevents crashes if the plugin is disabled or failed to load.
	if not Engine.has_singleton("Noray"):
		push_error("Netfox Noray addon is not enabled or failed to load.")
		return

	# Store a reference to the Noray singleton for easy access.
	noray = get_node("/root/Noray")

	# Connect to Noray's signals to handle the different stages of the
	# connection lifecycle. This is the core of our event-driven networking.
	# We are listening for specific events from the Noray addon and will
	# trigger our own logic in response.
	noray.registered_with_server.connect(_on_noray_registered_with_server)
	noray.connection_failed.connect(_on_noray_connection_failed)
	noray.connected_to_peer.connect(_on_noray_connected_to_peer)

	# Immediately try to connect to the Noray server upon game start.
	# This gets our client registered and ready to host or join a session.
	print("Connecting to Noray server at %s:%d" % [NORAY_SERVER_URL, NORAY_SERVER_PORT])
	noray.connect_to_server(NORAY_SERVER_URL, NORAY_SERVER_PORT)


# --- Public Methods ---
# These methods are the primary interface for the rest of the game (e.g., the UI)
# to interact with the networking system.

# Public function to initiate hosting a new game session.
func host_session():
	# We are already connected to the Noray server, so we just need to
	# tell Godot's high-level multiplayer system to start acting as a server.
	# The `create_peer()` method on the MultiplayerAPI handles this.
	var peer = ENetMultiplayerPeer.new()
	var error = peer.create_server(NORAY_SERVER_PORT) # Will use a random port if 0
	if error != OK:
		emit_signal("network_error", "Failed to create server.")
		return

	multiplayer.multiplayer_peer = peer
	print("Server created. Waiting for Noray registration to complete.")
	# The actual "hosted" state is confirmed in the `_on_noray_registered_with_server`
	# callback, which is triggered after Noray confirms our registration.


# Public function to join an existing game session using its OpenID (oid).
func join_session(oid: String):
	# Input validation is crucial. An empty OID is invalid.
	if oid.strip_edges().is_empty():
		emit_signal("network_error", "The Session ID cannot be empty.")
		return

	# We ask Noray to orchestrate the connection to the host.
	# Noray will then attempt NAT punch-through or relaying.
	print("Attempting to join session: ", oid)
	noray.connect_to_host(oid)


# --- Signal Handlers ---
# These private functions are callbacks that execute in response to signals
# emitted by the `netfox.noray` addon.

# This function is called when Noray confirms we are registered as a host.
func _on_noray_registered_with_server(oid: String, _pid: String):
	# Now that we have our public OpenID (oid), the session is officially hosted.
	# We emit our custom signal to let the UI know it can display the oid.
	print("Successfully registered with Noray. Our Session ID is: ", oid)
	emit_signal("session_hosted", oid)


# This function is called if Noray fails to establish a connection.
func _on_noray_connection_failed():
	# This is a general failure signal. It could be that the host OID was
	# invalid, the host is no longer online, or NAT punch-through and
	# relaying both failed.
	print("Error: Connection to peer failed.")
	emit_signal("network_error", "Failed to connect to the host.")
	multiplayer.multiplayer_peer = null # Clean up the failed connection


# This function is called when a direct peer-to-peer connection is made.
func _on_noray_connected_to_peer(peer: ENetMultiplayerPeer):
	# Noray has successfully orchestrated a connection. It hands off the
	# established peer connection for us to use.
	# We set this as our active multiplayer peer, and from this point on,
	# all communication is handled by Godot's high-level multiplayer API.
	print("Successfully connected to peer!")
	multiplayer.multiplayer_peer = peer
	emit_signal("session_joined")
