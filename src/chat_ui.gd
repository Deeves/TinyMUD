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
@onready var log_display: RichTextLabel = $RichTextLabel
@onready var input_box: LineEdit = $LineEdit
@onready var background_rect: ColorRect = $Background
@onready var options_button: Button = $OptionsButton
var options_menu_scene: PackedScene = preload("res://OptionsMenu.tscn")
var options_menu: Panel

# --- Socket.IO helper over WebSocketPeer ---
@onready var sio: Node = preload("res://src/socket_io_client.gd").new()

# --- Settings ---
const SETTINGS_PATH := "user://settings.cfg"
const SETTINGS_SECTION := "chat_ui"
var current_font_size: int = 16
var current_bg_color: Color = Color.BLACK
var server_host: String = "127.0.0.1"
var server_port: int = 5000
var censor_passwords: bool = true
var auto_reconnect: bool = false
var theme_name: String = "Modern"
var _reconnect_timer: SceneTreeTimer
var _reconnect_attempts: int = 0
const RECONNECT_BASE_DELAY := 1.5
const RECONNECT_MAX_DELAY := 10.0
var _wrap_cols_cache: int = -1

# --- UX helpers ---
var _last_sent_message: String = ""
const ACK_TIMEOUT_SEC := 1.2
# Pending acknowledgement state for last non-slash input
var _pending_ack: Dictionary = {}
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
	if options_menu.has_signal("theme_option_changed"):
		options_menu.theme_option_changed.connect(_on_theme_option_changed)
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
	# Apply font family/theme before sizing, then apply size and colors
	_apply_theme_by_name(theme_name)
	_apply_font_size(current_font_size)
	_apply_background(current_bg_color)
	# Initialize options panel controls
	if options_menu.has_method("set_initial_values"):
		# Pass through the persisted theme so the dropdown reflects it
		options_menu.set_initial_values(current_font_size, current_bg_color, server_host, server_port, censor_passwords, auto_reconnect, theme_name)

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
	# Export builds on some GPUs/drivers can crash when RichTextLabel runs threaded.
	# Make sure threading is disabled regardless of scene defaults.
	log_display.threaded = false
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

	# Keep wrap cache up to date on size/theme changes
	_refresh_wrap_cache()
	if has_signal("resized"):
		resized.connect(_refresh_wrap_cache)
	if is_instance_valid(log_display) and log_display.has_signal("resized"):
		log_display.resized.connect(_refresh_wrap_cache)
	if has_signal("theme_changed"):
		theme_changed.connect(_refresh_wrap_cache)
	if is_instance_valid(log_display) and log_display.has_signal("theme_changed"):
		log_display.theme_changed.connect(_refresh_wrap_cache)

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

func _on_event(event_name: String, data: Variant) -> void:
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
			_handle_system_message(String(data.get("content", "")))
		"player":
			_handle_player_message(String(data.get("name", "Someone")), String(data.get("content", "...")))
		"npc":
			_handle_npc_message(String(data.get("name", "Someone")), String(data.get("content", "...")))
		"error":
			append_to_log("[color=red]Server Error: %s[/color]" % data.get("content", ""))
		_:
			append_to_log("[color=purple]Unknown message type: %s[/color]" % data["type"])

func _handle_system_message(content: String) -> void:
	# Help tables need monospace to keep columns aligned; detect and render as code
	if _looks_like_help_table(content):
		append_to_log("[color=green][code]%s[/code][/color]" % _normalize_help_text(content))
		return
	# Detect ASCII art style banners: many lines, heavy use of punctuation, few letters
	if _looks_like_ascii_art(content):
		append_to_log("[color=green][code]%s[/code][/color]" % content.strip_edges())
		return
	append_to_log("[color=green]%s[/color]" % content)
	var c := content.to_lower()
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


# Heuristic to decide if a system message is ASCII art. We avoid relying on server
# tags to keep transport simple.
func _looks_like_ascii_art(text: String) -> bool:
	# Basic shape: at least 6 lines and average line length >= 20
	var lines := text.split("\n")
	if lines.size() < 6:
		return false
	var long_count := 0
	var symbol_count := 0
	var letter_count := 0
	for l_raw in lines:
		var l := String(l_raw)
		if l.length() >= 20:
			long_count += 1
		for i in l:
			var ch := String(i)
			if ch.is_valid_identifier():
				# Count ASCII letters and digits as letters bucket
				letter_count += 1
			else:
				# Punctuation, spaces, symbols
				symbol_count += 1
	# Many long lines and symbol density should dominate letters
	var enough_long := long_count >= int(lines.size() * 0.5)
	var symbol_ratio := 0.0
	if symbol_count + letter_count > 0:
		symbol_ratio = float(symbol_count) / float(symbol_count + letter_count)
	return enough_long and symbol_ratio >= 0.7

# Heuristic to decide if a system message is the multi-column /help output.
# Characteristics: many lines, repeated pipes or wide dashes, and known headers.
func _looks_like_help_table(text: String) -> bool:
	var lines := text.split("\n")
	if lines.size() < 10:
		return false
	var header_hint := false
	var pipe_lines := 0
	var double_space_lines := 0
	var dash_lines := 0
	for l_raw in lines:
		var l := String(l_raw)
		var lower := l.to_lower()
		if lower.find("commands") != -1 or lower.find("tips") != -1 or lower.begins_with("auth") or lower.begins_with("player") or lower.begins_with("admin") or lower.begins_with("network"):
			header_hint = true
		# Many help rows use vertical bars and double-spaces for crude columns
		if l.find("|") != -1:
			pipe_lines += 1
		if l.find("  ") != -1:
			double_space_lines += 1
		if l.find("—") != -1 or l.find("–") != -1:
			dash_lines += 1
	var structural := (pipe_lines >= 3 or double_space_lines >= 6 or dash_lines >= 3)
	return header_hint and structural

# Normalize unicode punctuation so monospace fonts align consistently
func _normalize_help_text(text: String) -> String:
	var s := String(text)
	# Normalize newlines first
	s = s.replace("\r\n", "\n")
	s = s.replace("\r", "\n")
	# Replace em/en dashes with a simple ASCII dash surrounded by spaces for clarity
	s = s.replace("—", "-")
	s = s.replace("–", "-")
	# Replace box-drawing vertical bars with ASCII pipes if present
	s = s.replace("│", "|")
	# Normalize any non-breaking or thin spaces to regular spaces
	s = s.replace("\u00A0", " ")
	s = s.replace("\u2007", " ")
	s = s.replace("\u202F", " ")
	s = s.replace("\u2009", " ")
	s = s.replace("\u200A", " ")
	# Expand tabs to spaces to preserve alignment within RichTextLabel
	s = s.replace("\t", "  ")
	# Replace fancy bullets with ASCII asterisks
	s = s.replace("•", "*")
	# Align crude two-column rows so descriptions line up nicely
	return _align_help_columns(s)

# Pad a string on the right up to width using spaces
func _pad_right(src: String, width: int) -> String:
	if src.length() >= width:
		return src
	return src + " ".repeat(width - src.length())

# Align lines that look like "command | - description" so that the dash/description
# column starts at a uniform position. Also applies conservative manual wrapping so
# continuation lines are indented under the description column.
func _align_help_columns(text: String) -> String:
	var lines: Array = text.split("\n")
	var pairs: Array = []
	var max_left := 0
	# Detect separator index for each line and compute max left width
	for l_raw in lines:
		var l := String(l_raw)
		var idx := -1
		# Prefer pipe as column marker; fall back to " - " sequence
		idx = l.find("|")
		if idx == -1:
			idx = l.find(" - ")
		if idx != -1:
			var left := l.substr(0, idx).strip_edges() # ok to trim both sides
			var right := l.substr(idx)
			pairs.append({"left": left, "right": right})
			if left.length() > max_left:
				max_left = left.length()
		else:
			pairs.append(null) # keep positions aligned
	# Rebuild with alignment and simple wrapping
	var out_lines: Array = []
	var wrap_width := _get_wrap_width_chars() # dynamic chars-per-line estimate (cached)
	for i in range(lines.size()):
		var l2 := String(lines[i])
		var meta: Variant = pairs[i]
		if meta == null:
			out_lines.append(l2)
			continue
		var left := String(meta["left"]) if meta != null else ""
		var right := String(meta["right"]) if meta != null else ""
		# Normalize right column start to a clear separator
		# If it begins with a pipe, keep it; otherwise insert " | "
		var sep := " | "
		if right.begins_with("|"):
			# keep existing pipe, strip any extra spacing and dash variants
			right = _lstrip_chars(right.substr(1), " \t")
		else:
			# remove the leading dash spacing if coming from " - " find
			right = _lstrip_chars(right, " -\t")
		# Ensure a simple dash marker before description
		right = "- " + right
		var left_pad := _pad_right(left, max_left + 2)
		var combined := left_pad + sep + right
		# Manual wrap: if the line is very long, break at spaces and indent continuation
		if combined.length() > wrap_width:
			var words: Array = combined.split(" ")
			var cur: String = ""
			var indent := _spaces((max_left + 2) + sep.length() + 2) # align under description
			for w in words:
				var ws: String = String(w)
				var candidate: String
				if cur == "":
					candidate = ws
				else:
					candidate = cur + " " + ws
				if candidate.length() > wrap_width:
					out_lines.append(cur)
					cur = indent + w
				else:
					cur = candidate
			if cur != "":
				out_lines.append(cur)
		else:
			out_lines.append(combined)
	return "\n".join(out_lines)

# Estimate how many monospace characters fit across the log view.
# Uses the RichTextLabel width and the mono font's measured width when available,
# with a safe fallback based on the current font size.
func _compute_wrap_width_chars() -> int:
	var width_px: float = 800.0
	if is_instance_valid(log_display):
		width_px = max(0.0, float(log_display.size.x))
		# Subtract theme stylebox horizontal content margins for more accurate content width
		var sb: StyleBox = log_display.get_theme_stylebox("normal")
		width_px -= _get_stylebox_h_margins(sb)
	# Try to get the monospace font used by [code] in RichTextLabel
	var font_size: int = current_font_size
	var mono_font: Font = null
	if is_instance_valid(log_display):
		mono_font = log_display.get_theme_font("mono_font")
	# Derive average char width
	var char_px: float = max(6.0, float(font_size) * 0.6) # fallback heuristic
	if mono_font != null and mono_font.has_method("get_string_size"):
		var sample := "M".repeat(40)
		var size_v := mono_font.get_string_size(sample, font_size)
		if typeof(size_v) == TYPE_VECTOR2 and size_v.x > 0.0:
			char_px = max(1.0, size_v.x / float(sample.length()))
	# Convert pixels to columns, keep within a sensible range.
	var cols: int = int(floor(width_px / char_px))
	# Leave a tiny margin to avoid accidental wrap due to borders/padding
	cols = cols - 2
	# Clamp to avoid degenerate cases
	cols = clamp(cols, 60, 320)
	return cols

# Cached wrap width computation and invalidation
func _get_wrap_width_chars() -> int:
	if _wrap_cols_cache > 0:
		return _wrap_cols_cache
	_wrap_cols_cache = _compute_wrap_width_chars()
	return _wrap_cols_cache

func _refresh_wrap_cache() -> void:
	_wrap_cols_cache = _compute_wrap_width_chars()

# Sum horizontal content margins from a StyleBox if available
func _get_stylebox_h_margins(sb: StyleBox) -> float:
	if sb == null:
		return 0.0
	var l := 0.0
	var r := 0.0
	if sb.has_method("get_content_margin"):
		l = float(sb.get_content_margin(SIDE_LEFT))
		r = float(sb.get_content_margin(SIDE_RIGHT))
	elif sb.has_method("get_margin"):
		l = float(sb.get_margin(SIDE_LEFT))
		r = float(sb.get_margin(SIDE_RIGHT))
	return l + r

# Left-strip all characters in 'chars' from the start of 's'
func _lstrip_chars(s: String, chars: String) -> String:
	var out := s
	var changed := true
	while changed and out.length() > 0:
		changed = false
		for i in range(chars.length()):
			var ch := String(chars[i])
			if out.begins_with(ch):
				out = out.substr(1)
				changed = true
				break
	return out

# Return a string of N spaces; avoids relying on String.repeat availability
func _spaces(n: int) -> String:
	if n <= 0:
		return ""
	var buf := ""
	for _i in range(n):
		buf += " "
	return buf

func _handle_player_message(pname: String, text: String) -> void:
	append_to_log("[color=yellow]%s says:[/color] %s" % [pname, text])

func _handle_npc_message(npc_name: String, text: String) -> void:
	append_to_log("[color=cyan]%s says:[/color] %s" % [npc_name, text])

func _on_text_submitted(player_text: String):
	if player_text.is_empty():
		return
	# Track if this submission is a password entry from the interactive flow.
	# We reset the masking immediately after, but we also use this flag to avoid logging/storing the raw text.
	var was_password := _expecting_password
	if _expecting_password:
		_expecting_password = false
		input_box.secret = false
	# Don't keep passwords in client history recall either
	_last_sent_message = "" if was_password else player_text
	# Don't echo auth commands as speech
	if player_text.begins_with("/"):
		# Client-side command: /quit — graceful exit without sending to server
		if player_text.strip_edges().to_lower() == "/quit":
			append_to_log("[color=gray]Exiting. Safe travels![/color]")
			sio.close()
			input_box.editable = false
			return
		# For /auth commands, echo with no special coloring but sanitize any password
		if player_text.strip_edges().to_lower().begins_with("/auth"):
			append_to_log(_sanitize_auth_echo(player_text))
		else:
			append_to_log("[color=gray]" + player_text + "[/color]")
		# Client-side /reconnect command
		if player_text.strip_edges().to_lower() == "/reconnect":
			# Treat manual command same as the button: clear prior scrollback
			_clear_log_and_reset()
			_manual_reconnect()
			input_box.clear()
			input_box.grab_focus()
			return
	else:
		# During interactive auth/login, NEVER echo raw passwords.
		# If we just handled a password, show a friendly placeholder instead of the real text.
		if _in_auth_flow:
			if was_password:
				append_to_log("[password hidden]")
			else:
				append_to_log(player_text)
		else:
			# Do not locally echo. Wait for server acknowledgement and then confirm.
			_begin_ack_wait(player_text)
	sio.emit("message_to_server", {"content": player_text})
	input_box.clear()
	# Keep focus in the input for rapid consecutive messages
	input_box.grab_focus()

# --- Security helpers ---
# Sanitize /auth command echos so no password is shown in the log.
# Supports both pipe-delimited (recommended):
#   /auth create <name> | <password> | <description>
#   /auth login  <name> | <password>
# and a minimal space-delimited fallback:
#   /auth create <name> <password> <description...>
#   /auth login  <name> <password>
func _sanitize_auth_echo(text: String) -> String:
	var raw := text
	var trimmed := raw.strip_edges()
	var lower := trimmed.to_lower()
	if not lower.begins_with("/auth"):
		return raw
	var first_space := trimmed.find(" ")
	if first_space == -1:
		return raw
	var head := trimmed.substr(0, first_space + 1) # includes trailing space
	var rest := trimmed.substr(first_space + 1).strip_edges()

	# Try pipe-delimited form first
	if rest.find("|") != -1:
		var segs := rest.split("|", false) # remove empty parts
		# Normalize spacing around segments on reconstruction
		for i in range(segs.size()):
			segs[i] = String(segs[i]).strip_edges()
		if segs.size() >= 2:
			segs[1] = "[hidden]"  # mask password segment
		var sanitized_rest := " | ".join(segs)
		return head + sanitized_rest

	# Space-delimited fallback: mask the 3rd token (action, name, password, ...)
	var tokens := rest.split(" ", false)
	if tokens.size() >= 3:
		tokens[2] = "[hidden]"
		return head + " ".join(tokens)

	return raw

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
	_refresh_wrap_cache()

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

	# Ensure the monospace face (if assigned) respects sizing
	var mono_font: Font = log_display.get_theme_font("mono_font")
	if mono_font != null:
		local_theme.set_font("mono_font", "RichTextLabel", mono_font)
		local_theme.set_font_size("mono_font_size", "RichTextLabel", p_size)

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
	cfg.set_value(SETTINGS_SECTION, "theme_name", theme_name)
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
		theme_name = str(cfg.get_value(SETTINGS_SECTION, "theme_name", theme_name))
	else:
		# Default on first run
		censor_passwords = true
		auto_reconnect = false
		theme_name = "Modern"
	# Start unmasked until explicitly prompted for password
	input_box.secret = false

func _on_theme_option_changed(new_theme_name: String) -> void:
	theme_name = new_theme_name
	# Apply immediately and persist
	_apply_theme_by_name(theme_name)
	# Re-apply current size to ensure theme font resources use our size
	_apply_font_size(current_font_size)
	_save_settings()
	_refresh_wrap_cache()

# --- Theme application ---
func _apply_theme_by_name(theme_name_value: String) -> void:
	var n := String(theme_name_value).to_lower()
	if n == "modern":
		_apply_modern_inter_theme()
	else:
		# Fallback: reset to default font family; keep sizes via subsequent _apply_font_size
		var fallback_theme := Theme.new()
		self.theme = fallback_theme

func _apply_modern_inter_theme() -> void:
	# Load Inter variable font and construct styled variants via OpenType variations
	var font_path := "res://assets/fonts/modern/InterVariable.ttf"
	var base_font: Font = load(font_path)
	if base_font == null:
		# Try TTC as fallback
		font_path = "res://assets/fonts/modern/Inter.ttc"
		base_font = load(font_path)
	if base_font == null:
		# Give up gracefully: let default engine fonts apply
		return
	# Create variation instances for bold/italic/bold-italic if supported
	var bold_font: Font = base_font
	var italic_font: Font = base_font
	var bold_italic_font: Font = base_font
	# FontVariation is available in Godot 4; use it to set OpenType axes when possible
	# Guarded at runtime; if FontVariation class exists, use it for axis variations
	if ClassDB.class_exists("FontVariation"):
		var fv_bold = ClassDB.instantiate("FontVariation")
		fv_bold.base_font = base_font
		# Inter supports 'wght' axis; 700 approximates Bold
		fv_bold.variation_opentype = {"wght": 700.0}
		bold_font = fv_bold

		var fv_italic = ClassDB.instantiate("FontVariation")
		fv_italic.base_font = base_font
		# Inter supports 'ital' axis for true italic, some builds use 'slnt'
		fv_italic.variation_opentype = {"ital": 1.0}
		italic_font = fv_italic

		var fv_bold_italic = ClassDB.instantiate("FontVariation")
		fv_bold_italic.base_font = base_font
		fv_bold_italic.variation_opentype = {"wght": 700.0, "ital": 1.0}
		bold_italic_font = fv_bold_italic

	# Build a theme that assigns Inter to all key UI controls
	var t := Theme.new()
	t.set_default_font(base_font)
	# RichTextLabel supports styled fonts
	t.set_font("normal_font", "RichTextLabel", base_font)
	t.set_font("bold_font", "RichTextLabel", bold_font)
	t.set_font("italics_font", "RichTextLabel", italic_font)
	t.set_font("bold_italics_font", "RichTextLabel", bold_italic_font)
	# Provide a bundled monospace for [code] blocks and help tables
	var mono_path := "res://assets/fonts/classic/PerfectDOSVGA437.ttf"
	var mono_font: Font = load(mono_path)
	if mono_font != null:
		# Godot's RichTextLabel uses 'mono_font' when rendering [code]
		t.set_font("mono_font", "RichTextLabel", mono_font)
	# Core controls that show text
	t.set_font("font", "LineEdit", base_font)
	t.set_font("font", "Button", base_font)
	t.set_font("font", "Label", base_font)
	t.set_font("font", "SpinBox", base_font)
	t.set_font("font", "CheckBox", base_font)
	t.set_font("font", "OptionButton", base_font)
	t.set_font("font", "ColorPickerButton", base_font)
	# Apply to Chat UI subtree
	self.theme = t
	# Theme change affects font metrics
	_refresh_wrap_cache()

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
	# Fresh-start UX: when a player explicitly clicks "Reconnect Now",
	# clear any prior scrollback (including partial acks) so the new session
	# begins clean. We intentionally do NOT clear on auto-reconnects to
	# preserve context during transient network blips.
	_clear_log_and_reset()
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

# --- Log/State Reset Helpers ---
# Clear chat scrollback and any ephemeral pending state. Used for explicit
# user-initiated reconnects to provide a clean slate.
func _clear_log_and_reset() -> void:
	if is_instance_valid(log_display):
		if log_display.has_method("clear"):
			log_display.clear()
		else:
			# Fallback for engines without clear()
			log_display.text = ""
	_has_logged_anything = false
	# Prevent any in-flight ack timeout from appending lines after clearing
	_pending_ack.clear()
