extends Panel

# Small options panel for the chat UI
# - Adjust text size and background color
# - Configure server host/port
# - Emits signals so the parent can apply changes
# - Stays simple so new contributors can add more toggles easily

signal text_size_changed(new_size: int)
signal bg_color_changed(new_color: Color)
signal server_settings_applied(host: String, port: int)
signal closed
signal password_censor_toggled(enabled: bool)
signal auto_reconnect_toggled(enabled: bool)
signal reconnect_pressed()

@onready var text_size_spin: SpinBox = $VBox/TextSizeHBox/TextSizeSpin
@onready var bg_color_picker: ColorPickerButton = $VBox/BgHBox/BgColorPicker
@onready var host_edit: LineEdit = $VBox/ServerHBox/HostEdit
@onready var port_spin: SpinBox = $VBox/ServerHBox/PortSpin
@onready var censor_passwords_check: CheckBox = $VBox/PasswordHBox/CensorPasswordsCheck
@onready var auto_reconnect_check: CheckBox = $VBox/ConnectionHBox/AutoReconnectCheck
@onready var reconnect_now_btn: Button = $VBox/ConnectionHBox/ReconnectNow
@onready var apply_btn: Button = $VBox/ButtonsHBox/ApplyButton
@onready var close_btn: Button = $VBox/ButtonsHBox/CloseButton

func _ready():
	text_size_spin.value_changed.connect(_on_text_size_changed)
	bg_color_picker.color_changed.connect(_on_bg_color_changed)
	censor_passwords_check.toggled.connect(_on_censor_passwords_toggled)
	auto_reconnect_check.toggled.connect(_on_auto_reconnect_toggled)
	reconnect_now_btn.pressed.connect(_on_reconnect_now)
	apply_btn.pressed.connect(_on_apply)
	close_btn.pressed.connect(_on_close)

func set_initial_values(p_size: int, color: Color, host: String, port: int, censor_passwords: bool = true, auto_reconnect: bool = false):
	text_size_spin.value = p_size
	bg_color_picker.color = color
	host_edit.text = host
	port_spin.value = port
	censor_passwords_check.button_pressed = censor_passwords
	auto_reconnect_check.button_pressed = auto_reconnect

func _on_text_size_changed(v: float):
	emit_signal("text_size_changed", int(v))

func _on_bg_color_changed(c: Color):
	emit_signal("bg_color_changed", c)

func _on_apply():
	var host := host_edit.text.strip_edges()
	var port := int(port_spin.value)
	if host == "":
		host = "127.0.0.1"
	emit_signal("server_settings_applied", host, port)

func _on_censor_passwords_toggled(pressed: bool) -> void:
	emit_signal("password_censor_toggled", pressed)

func _on_auto_reconnect_toggled(pressed: bool) -> void:
	emit_signal("auto_reconnect_toggled", pressed)

func _on_reconnect_now() -> void:
	emit_signal("reconnect_pressed")

func _on_close():
	visible = false
	emit_signal("closed")
