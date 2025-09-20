extends Control

# Chat UI script (beginner-friendly):
# - Shows a chat log and an input box
# - Connects to the Python server via a minimal Socket.IO client
# - Sends your text, prints NPC/system replies, and saves a few settings
#
# To extend:
# - Add client-side commands in _on_text_submitted (e.g., local UI effects)
# - Adjust how messages are formatted in _on_event
# - Add more options in OptionsMenu.tscn/options_menu.gd

# --- UI Node References ---
@onready var log_display = $RichTextLabel
@onready var input_box = $LineEdit
@onready var background_rect: ColorRect = $Background
@onready var options_button: Button = $OptionsButton
var options_menu_scene: PackedScene = preload("res://OptionsMenu.tscn")
var options_menu: Panel

# --- Socket.IO helper over WebSocketPeer ---
@onready var sio := preload("res://src/socket_io_client.gd").new()

# --- Settings ---
const SETTINGS_PATH := "user://settings.cfg"
const SETTINGS_SECTION := "chat_ui"
var current_font_size: int = 16
var current_bg_color: Color = Color.BLACK
var server_host: String = "127.0.0.1"
var server_port: int = 5000
var censor_passwords: bool = true
var auto_reconnect: bool = false
var _reconnect_timer: SceneTreeTimer
var _reconnect_attempts: int = 0
const RECONNECT_BASE_DELAY := 1.5
const RECONNECT_MAX_DELAY := 10.0

# --- UX helpers ---
var _last_sent_message: String = ""
const ACK_TIMEOUT_SEC := 1.2
# Pending acknowledgement state for last non-slash input
var _pending_ack := {}
# Whether we're in interactive auth/login flow; echo inputs plainly
var _in_auth_flow: bool = true
var _expecting_password: bool = false
# Track if we've printed anything yet to control inter-entry spacing
var _has_logged_anything: bool = false
# Keys used when populated:
#  - 'original': String   (full text sent)
#  - 'verb': String       (first token, lowercased)
#  - 'rest': String       (text after the first space)
#  - 'timer': Object      (SceneTreeTimer instance)
#  - 'acknowledged': bool (whether we've confirmed already)

func _ready():
	# Wire UI
	options_button.pressed.connect(show_options)
	# Instance options menu
	options_menu = options_menu_scene.instantiate()
	add_child(options_menu)
	options_menu.text_size_changed.connect(_on_text_size_changed)
	options_menu.bg_color_changed.connect(_on_bg_color_changed)
	options_menu.closed.connect(_on_options_closed)
	# Server settings from options menu
	if options_menu.has_signal("server_settings_applied"):
		options_menu.server_settings_applied.connect(_on_server_settings_applied)
		# Password censoring toggle
		if options_menu.has_signal("password_censor_toggled"):
			options_menu.password_censor_toggled.connect(_on_password_censor_toggled)
		if options_menu.has_signal("auto_reconnect_toggled"):
			options_menu.auto_reconnect_toggled.connect(_on_auto_reconnect_toggled)
		if options_menu.has_signal("reconnect_pressed"):
			options_menu.reconnect_pressed.connect(_on_reconnect_pressed)

	# Load settings and apply
	_load_settings()
	_apply_font_size(current_font_size)
	_apply_background(current_bg_color)
	# Initialize options panel controls
	if options_menu.has_method("set_initial_values"):
		options_menu.set_initial_values(current_font_size, current_bg_color, server_host, server_port, censor_passwords, auto_reconnect)

	input_box.text_submitted.connect(_on_text_submitted)
	input_box.gui_input.connect(_on_input_box_gui_input)
	input_box.grab_focus()

	# Ensure log readability and behavior
	# - Enable BBCode (for [color] etc.)
	# - Word wrap within viewport
	# - Follow newest messages automatically
	log_display.bbcode_enabled = true
	log_display.autowrap_mode = TextServer.AUTOWRAP_WORD
	log_display.scroll_following = true
	# Avoid the log attempting to grow with content height if containers allow it
	# (defaults are typically fine, this is just a safety)
	if log_display.has_method("set_fit_content"):
		log_display.fit_content = false

	# Keep input from expanding to the full length of typed text
	# and ensure it fills available width instead of growing past it
	if input_box.has_method("set_expand_to_text_length"):
		input_box.expand_to_text_length = false
	input_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	# Make sure the caret is always visible while typing (if supported)
	if input_box.has_method("set_caret_force_displayed"):
		input_box.caret_force_displayed = true

	add_child(sio)
	sio.transport_opened.connect(_on_transport_opened)
	sio.connected.connect(_on_connected)
	sio.disconnected.connect(_on_disconnected)
	sio.event_received.connect(_on_event)

	_connect_to_configured_server()

func _on_transport_opened():
	# Underlying WebSocket engine is open; print immediately before any namespace events
	append_to_log("[color=light blue]Connected.[/color]")

func _on_connected():
	# Namespace connected; nothing additional needed here for log ordering
	# Reset reconnect backoff when connected
	_reconnect_attempts = 0
	_reconnect_timer = null
	_in_auth_flow = true
	_expecting_password = false
	input_box.secret = false

func _on_disconnected():
	append_to_log("[color=red]Disconnected.[/color]")
	_schedule_reconnect()

func _on_event(event_name: String, data) -> void:
	if event_name != "message":
		return
	# If we were waiting for a server acknowledgement, confirm once on first message back
	if _pending_ack.has("timer") and not _pending_ack.get("acknowledged", false):
		var verb: String = str(_pending_ack.get("verb", "")).strip_edges()
		var rest: String = str(_pending_ack.get("rest", "")).strip_edges()
		var cmd_text = verb if rest == "" else verb + " " + rest
		if cmd_text != "":
			append_to_log("[color=yellow] You %s [/color]" % cmd_text)
		_pending_ack["acknowledged"] = true
		# Clear immediately; timeout handler will no-op if it fires later
		_pending_ack.clear()
	if typeof(data) != TYPE_DICTIONARY:
		append_to_log("[color=red]Malformed message from server.[/color]")
		return
	if not data.has("type"):
		append_to_log("[color=red]Malformed message from server (no type).[/color]")
		return
	match data["type"]:
		"system":
			append_to_log("[color=green]%s[/color]" % data.get("content", ""))
			# Track auth flow state based on server guidance
			var c := String(data.get("content", "")).to_lower()
			if c.find("welcome back,") != -1 or c.find("character created. welcome,") != -1:
				_in_auth_flow = false
			elif c.find("type \"create\" to forge a new character or \"login\" to sign in") != -1:
				_in_auth_flow = true
			elif c.find("login selected. enter your display name:") != -1:
				_in_auth_flow = true
			elif c.find("creation selected. choose a display name") != -1:
				_in_auth_flow = true
			elif c.find("enter password:") != -1:
				_in_auth_flow = true
				_expecting_password = true
				input_box.secret = censor_passwords
			elif c.find("enter a short character description") != -1:
				_in_auth_flow = true
			elif c.find("cancelled. type \"create\" or \"login\" to continue.") != -1:
				_in_auth_flow = true
			# Treat world setup wizard as an auth-like flow (plain local echo, no special color)
			elif c.find("let's set up your world!") != -1:
				_in_auth_flow = true
			elif c.find("describe the world") != -1:
				_in_auth_flow = true
			elif c.find("describe the main conflict") != -1:
				_in_auth_flow = true
			elif c.find("create the starting room") != -1:
				_in_auth_flow = true
			elif c.find("enter a description for the starting room") != -1:
				_in_auth_flow = true
			elif c.find("create an npc") != -1:
				_in_auth_flow = true
			elif c.find("enter a short description for") != -1:
				_in_auth_flow = true
			elif c.find("world setup complete!") != -1:
				_in_auth_flow = false
				_expecting_password = false
				input_box.secret = false
			elif c.find("setup cancelled.") != -1:
				_in_auth_flow = false
				_expecting_password = false
				input_box.secret = false
		"player":
			var pname = data.get("name", "Someone")
			var ptext = data.get("content", "...")
			append_to_log("[color=yellow]%s says:[/color] %s" % [pname, ptext])
		"npc":
			var npc_name = data.get("name", "Someone")
			var npc_content = data.get("content", "...")
			append_to_log("[color=cyan]%s says:[/color] %s" % [npc_name, npc_content])
		"error":
			append_to_log("[color=red]Server Error: %s[/color]" % data.get("content", ""))
		_:
			append_to_log("[color=purple]Unknown message type: %s[/color]" % data["type"])

func _on_text_submitted(player_text: String):
	if player_text.is_empty():
		return
	# If we just entered a password, unmask after submission
	if _expecting_password:
		_expecting_password = false
		input_box.secret = false
	_last_sent_message = player_text
	# Don't echo auth commands as speech
	if player_text.begins_with("/"):
		# Client-side /help: show quick tips without round-trip
		var low := player_text.strip_edges().to_lower()
		if low == "/help":
			var lines := [
				"[b]Client Help[/b]",
				"Type plain text to chat. Use 'say <text>' for NPC replies.",
				"[b]Auth[/b]: /auth create <name> | <password> | <description> | /auth login <name> | <password>",
				"[b]Basics[/b]: look | /rename <new> | /describe <text> | /sheet",
				"[b]Admin[/b]: /teleport <room_id>  |  /teleport <player> | <room_id>",
				"         /bring <player> | <room_id>  |  /kick <player>",
				"[b]Network[/b]: /reconnect — retry connection now",
				"Note: room ids accept fuzzy matches (prefix/substring).",
			]
			for l in lines:
				append_to_log(l)
			input_box.clear()
			input_box.grab_focus()
			return
		# Client-side command: /quit — graceful exit without sending to server
		if player_text.strip_edges().to_lower() == "/quit":
			append_to_log("[color=gray]Exiting. Safe travels![/color]")
			sio.close()
			input_box.editable = false
			return
		# For /auth commands, echo with no special coloring
		if player_text.strip_edges().to_lower().begins_with("/auth"):
			append_to_log(player_text)
		else:
			append_to_log("[color=gray]" + player_text + "[/color]")
		# Client-side /reconnect command
		if player_text.strip_edges().to_lower() == "/reconnect":
			_manual_reconnect()
			input_box.clear()
			input_box.grab_focus()
			return
	else:
		# During interactive auth/login, echo raw with no special coloring
		if _in_auth_flow:
			append_to_log(player_text)
		else:
			# Do not locally echo. Wait for server acknowledgement and then confirm.
			_begin_ack_wait(player_text)
	sio.emit("message_to_server", {"content": player_text})
	input_box.clear()
	# Keep focus in the input for rapid consecutive messages
	input_box.grab_focus()

func _on_input_box_gui_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		var kev := event as InputEventKey
		if kev.keycode == KEY_UP:
			# Fill last sent message if available; don't clobber existing text
			if _last_sent_message != "" and input_box.text.strip_edges() == "":
				input_box.text = _last_sent_message
				input_box.caret_column = input_box.text.length()
				accept_event()

func append_to_log(text: String):
	# Insert a blank line between entries for readability,
	# but avoid a leading blank line for the very first entry
	if _has_logged_anything:
		log_display.append_text("\n\n" + text)
	else:
		log_display.append_text(text)
		_has_logged_anything = true
	# Extra guard to keep view at the bottom even if follow timing races
	if log_display.get_line_count() > 0:
		log_display.scroll_to_line(log_display.get_line_count() - 1)

# --- Ack/Confirm Helpers ---
func _begin_ack_wait(text: String) -> void:
	# Cancel any existing pending ack
	if _pending_ack.has("timer"):
		_pending_ack.clear()
	var verb := ""
	var rest := ""
	var trimmed := text.strip_edges()
	if trimmed != "":
		var parts := trimmed.split(" ", false, 1)
		verb = parts[0].to_lower()
		if parts.size() > 1:
			rest = parts[1]
	var t := get_tree().create_timer(ACK_TIMEOUT_SEC)
	# Pass the timer back into the timeout handler so we can detect stale timers
	t.timeout.connect(Callable(self, "_on_ack_timeout").bind(t))
	_pending_ack = {
		"original": text,
		"verb": verb,
		"rest": rest,
		"timer": t,
		"acknowledged": false,
	}

func _on_ack_timeout(timer):
	# Only act if this timeout corresponds to the current pending ack
	if not _pending_ack.has("timer"):
		return
	if _pending_ack.get("timer") != timer:
		return
	if _pending_ack.get("acknowledged", false):
		return
	# Light-hearted nudge suggesting proper command usage
	var lines := [
		"[color=gray]Sorry, didn't quite catch that…[/color]",
		"[color=gray]The winds whisk your words away. Try 'say …'?[/color]",
		"[color=gray]Huh? The void echoes back nothing.[/color]",
		"[color=gray]Your message wanders off into the dungeon tunnels…[/color]",
	]
	var idx := randi() % lines.size()
	append_to_log(lines[idx])
	_pending_ack.clear()

# --- Options Menu Logic ---
func show_options():
	options_menu.visible = not options_menu.visible

func _on_options_closed():
	_save_settings() # persist when closing

func _on_text_size_changed(value: float) -> void:
	current_font_size = int(value)
	_apply_font_size(current_font_size)

func _on_bg_color_changed(color: Color) -> void:
	current_bg_color = color
	_apply_background(current_bg_color)

func _apply_font_size(p_size: int) -> void:
	# Adjust font size via theme overrides
	var local_theme := Theme.new()
	# Use default theme fonts; override sizes safely without assigning font.size
	var base_font: Font = log_display.get_theme_font("normal_font")
	if base_font == null:
		base_font = self.get_theme_default_font()
	# Set global defaults so child controls inherit if not explicitly overridden
	local_theme.set_default_font(base_font)
	local_theme.set_default_font_size(p_size)
	local_theme.set_font("normal_font", "RichTextLabel", base_font)
	local_theme.set_font_size("normal_font_size", "RichTextLabel", p_size)

	# Ensure styled variants match the same size
	var bold_font: Font = log_display.get_theme_font("bold_font")
	if bold_font != null:
		local_theme.set_font("bold_font", "RichTextLabel", bold_font)
	local_theme.set_font_size("bold_font_size", "RichTextLabel", p_size)

	var italics_font: Font = log_display.get_theme_font("italics_font")
	if italics_font != null:
		local_theme.set_font("italics_font", "RichTextLabel", italics_font)
	local_theme.set_font_size("italics_font_size", "RichTextLabel", p_size)

	var bold_italics_font: Font = log_display.get_theme_font("bold_italics_font")
	if bold_italics_font != null:
		local_theme.set_font("bold_italics_font", "RichTextLabel", bold_italics_font)
	local_theme.set_font_size("bold_italics_font_size", "RichTextLabel", p_size)

	var line_font: Font = input_box.get_theme_font("font")
	if line_font == null:
		line_font = self.get_theme_default_font()
	local_theme.set_font("font", "LineEdit", line_font)
	local_theme.set_font_size("font_size", "LineEdit", p_size)
	# Buttons (includes OptionsButton and ColorPickerButton)
	local_theme.set_font("font", "Button", base_font)
	local_theme.set_font_size("font_size", "Button", p_size)
	# Labels (for options labels)
	local_theme.set_font("font", "Label", base_font)
	local_theme.set_font_size("font_size", "Label", p_size)
	# SpinBox (value editor + arrows)
	local_theme.set_font("font", "SpinBox", base_font)
	local_theme.set_font_size("font_size", "SpinBox", p_size)
	# CheckBox
	local_theme.set_font("font", "CheckBox", base_font)
	local_theme.set_font_size("font_size", "CheckBox", p_size)
	# Apply to this subtree only
	self.theme = local_theme

func _apply_background(color: Color) -> void:
	background_rect.color = color

func _save_settings() -> void:
	var cfg := ConfigFile.new()
	var _err = cfg.load(SETTINGS_PATH)
	# It's ok if it fails; we'll overwrite
	cfg.set_value(SETTINGS_SECTION, "font_size", current_font_size)
	cfg.set_value(SETTINGS_SECTION, "bg_color", current_bg_color)
	cfg.set_value(SETTINGS_SECTION, "server_host", server_host)
	cfg.set_value(SETTINGS_SECTION, "server_port", server_port)
	cfg.set_value(SETTINGS_SECTION, "censor_passwords", censor_passwords)
	cfg.set_value(SETTINGS_SECTION, "auto_reconnect", auto_reconnect)
	cfg.save(SETTINGS_PATH)

func _load_settings() -> void:
	var cfg := ConfigFile.new()
	var err = cfg.load(SETTINGS_PATH)
	if err == OK:
		current_font_size = int(cfg.get_value(SETTINGS_SECTION, "font_size", current_font_size))
		var col = cfg.get_value(SETTINGS_SECTION, "bg_color", current_bg_color)
		if typeof(col) == TYPE_COLOR:
			current_bg_color = col
		else:
			# handle legacy string color like "#RRGGBBAA"
			if typeof(col) == TYPE_STRING:
				current_bg_color = Color(col)
		server_host = str(cfg.get_value(SETTINGS_SECTION, "server_host", server_host))
		server_port = int(cfg.get_value(SETTINGS_SECTION, "server_port", server_port))
		censor_passwords = bool(cfg.get_value(SETTINGS_SECTION, "censor_passwords", true))
		auto_reconnect = bool(cfg.get_value(SETTINGS_SECTION, "auto_reconnect", false))
	else:
		# Default on first run
		censor_passwords = true
		auto_reconnect = false
	# Start unmasked until explicitly prompted for password
	input_box.secret = false

func _on_password_censor_toggled(enabled: bool) -> void:
	censor_passwords = enabled
	if _expecting_password:
		input_box.secret = censor_passwords
	_save_settings()

func _on_auto_reconnect_toggled(enabled: bool) -> void:
	auto_reconnect = enabled
	_save_settings()
	if auto_reconnect and not sio.is_open():
		_schedule_reconnect(true)

func _on_reconnect_pressed() -> void:
	_manual_reconnect()

func _connect_to_configured_server() -> void:
	var url = "ws://%s:%d/socket.io/?EIO=4&transport=websocket" % [server_host, server_port]
	append_to_log("[color=gray]Connecting to %s:%d...[/color]" % [server_host, server_port])
	sio.connect_to_server(url)

func _schedule_reconnect(immediate: bool = false) -> void:
	if not auto_reconnect:
		return
	if sio.is_open():
		return
	# Exponential backoff with cap
	if immediate:
		_reconnect_attempts = 0
	var delay: float = min(float(RECONNECT_BASE_DELAY * pow(2.0, float(_reconnect_attempts))), RECONNECT_MAX_DELAY)
	_reconnect_attempts = min(_reconnect_attempts + 1, 10)
	if _reconnect_timer:
		# cancel previous; creating a new timer is enough
		pass
	_reconnect_timer = get_tree().create_timer(delay)
	_reconnect_timer.timeout.connect(Callable(self, "_do_reconnect_attempt"))
	append_to_log("[color=gray]Reconnecting in %.1f s…[/color]" % delay)

func _do_reconnect_attempt() -> void:
	if sio.is_open():
		return
	append_to_log("[color=gray]Reconnecting…[/color]")
	_connect_to_configured_server()

func _manual_reconnect() -> void:
	append_to_log("[color=gray]Manual reconnect requested.[/color]")
	sio.close()
	_reconnect_attempts = 0
	_connect_to_configured_server()

func _on_server_settings_applied(host: String, port: int) -> void:
	server_host = host
	server_port = port
	_save_settings()
	# Reconnect to new server
	sio.close()
	_connect_to_configured_server()
