extends Node

# Minimal Socket.IO v4 client for Godot 4
# What it does:
# - Connects to a Socket.IO server URL (engine.io v4)
# - Handles open/ping/pong and basic 'event' packets on the default namespace
# - Emits events with JSON payloads
#
# What it doesn't do (by design to stay tiny):
# - Namespaces other than '/'
# - Binary payloads or acks
# - Reconnection/backoff
#
# Good enough for this demo and easy to read/modify.

# Minimal Socket.IO v4 client over WebSocketPeer for Godot 4
# Supports: connect, ping/pong, emit event, receive event on default namespace

signal connected
signal disconnected
signal event_received(event_name, data)
signal transport_opened

var socket := WebSocketPeer.new()
var _is_open := false
var _sid := ""
var _engine_open := false

func connect_to_server(url: String) -> void:
	# Example url: ws://127.0.0.1:5000/socket.io/?EIO=4&transport=websocket
	_engine_open = false
	var err := socket.connect_to_url(url)
	if err != OK:
		push_error("WebSocket connect error: %s" % err)
	else:
		set_process(true)

func _process(_delta: float) -> void:
	socket.poll()
	var state := socket.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN:
		# Read all pending packets
		while socket.get_available_packet_count() > 0:
			var pkt: PackedByteArray = socket.get_packet()
			var text := pkt.get_string_from_utf8()
			_handle_engineio_message(text)
	elif state == WebSocketPeer.STATE_CLOSING:
		# Keep polling to finish close
		pass
	elif state == WebSocketPeer.STATE_CLOSED:
		if _is_open:
			_is_open = false
			emit_signal("disconnected")
		set_process(false)

func _handle_engineio_message(msg: String) -> void:
	# Engine.IO frame types (v4):
	# 0: open, 2: ping, 3: pong, 4: message
	if msg.length() == 0:
		return
	var frame := msg[0]
	match frame:
		"0":
			# Open: contains JSON with sid, etc.
			var payload := msg.substr(1)
			var data = JSON.parse_string(payload)
			if typeof(data) == TYPE_DICTIONARY and data.has("sid"):
				_sid = data["sid"]
			# Now open Socket.IO default namespace by sending "40"
			socket.send_text("40")
			# Notify engine transport is open (emit once)
			if not _engine_open:
				_engine_open = true
				emit_signal("transport_opened")
		"2":
			# Ping from server, respond with pong "3"
			socket.send_text("3")
		"4":
			# Socket.IO packet
			if msg.length() >= 2:
				var siotype := msg[1] # 0 connect, 1 disconnect, 2 event, 3 ack, 4 error, 5 binary event, 6 binary ack
				match siotype:
					"0":
						# Connected to namespace
						_is_open = true
						emit_signal("connected")
					"1":
						# Disconnected from namespace
						_is_open = false
						emit_signal("disconnected")
					"2":
						# Event: format "42[\"event\", data]" (namespace omitted for default '/').
						var bracket_idx := msg.find("[")
						if bracket_idx != -1:
							var arr = JSON.parse_string(msg.substr(bracket_idx))
							if typeof(arr) == TYPE_ARRAY and arr.size() >= 1:
								var event_name = arr[0]
								var data = arr[1] if arr.size() > 1 else null
								emit_signal("event_received", event_name, data)
					_:
						# Other packet types not handled in this minimal client
						pass
		_:
			# Unhandled frame types
			pass

func emit(event_name: String, data) -> void:
	if !_is_open:
		push_warning("Socket.IO not open; cannot emit event.")
		return
	var payload := "42" + JSON.stringify([event_name, data])
	socket.send_text(payload)

func close(code: int = 1000, reason: String = "") -> void:
	socket.close(code, reason)
	_engine_open = false
	set_process(false)
