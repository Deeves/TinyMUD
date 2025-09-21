
extends Node

# Simple demo script that connects to the Socket.IO server on startup
# and sends one message. Useful as a minimal example separate from the
# full Chat UI. You can ignore this if you're using ChatUI.tscn.

@onready var sio: Node = preload("res://src/socket_io_client.gd").new()

func _ready() -> void:
	add_child(sio)
	sio.connected.connect(_on_connected)
	sio.disconnected.connect(_on_disconnected)
	sio.event_received.connect(_on_event)
	# Connect to Flask-SocketIO server
	var url := "ws://127.0.0.1:5000/socket.io/?EIO=4&transport=websocket"
	sio.connect_to_server(url)

func _on_connected() -> void:
	print("Socket.IO connected!")
	send_npc_message("Hello from Godot via Socket.IO!")

func _on_disconnected() -> void:
	print("Socket.IO disconnected.")

func _on_event(event_name: String, data: Variant) -> void:
	if event_name == "message":
		# Server emits: {'type': 'npc','name':'The Wizard','content': '...'}
		print("NPC says:", data)
	else:
		print("Event ", event_name, ": ", data)

func send_npc_message(message_text: String) -> void:
	# Emit the event expected by server
	sio.emit("message_to_server", {"content": message_text})
