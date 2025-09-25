# TinyMUD NPC planning smoke test
#
# This script boots the server module in-process, stubs the planning model to a
# deterministic JSON plan, seeds a room with an NPC and a food item, then
# executes a couple of actions while printing any room broadcasts.
#
# Usage (PowerShell):
#   $env:MUD_TICK_ENABLE='0'; $env:MUD_NO_INTERACTIVE='1'; .\.venv\Scripts\python.exe server\smoke_npc_plan.py

import os
import sys
import json
import importlib
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(ROOT, 'server')
# Ensure both repo root and server dir are on sys.path so 'world' resolves
for p in (ROOT, SERVER_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

# Disable heartbeat and any prompts for this smoke run
os.environ.setdefault('MUD_TICK_ENABLE', '0')
os.environ.setdefault('MUD_NO_INTERACTIVE', '1')

# Import the main server module by file path to avoid namespace/package conflicts
SERVER_PY = os.path.join(SERVER_DIR, 'server.py')
spec = importlib.util.spec_from_file_location('srv_mod', SERVER_PY)
assert spec and spec.loader, f"Failed to load spec for {SERVER_PY}"
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)  # type: ignore[arg-type]

# Import data model classes from world.py (on sys.path via SERVER_DIR)
from world import Room, Object

# Replace socketio with a test double that prints room broadcasts
class _FakeSocketIO:
    def emit(self, event_name: str, payload=None, to: str | None = None, **kwargs):
        if event_name == 'message' and payload is not None:
            print(f"[broadcast] {payload}")
    def sleep(self, seconds: float):
        # No-op for this offline smoke
        pass

srv.socketio = _FakeSocketIO()

# Reset world to a tiny fresh state
srv.world.rooms.clear()
srv.world.players.clear()
srv.world.npc_sheets.clear()

# Create a test room with one present player (audience) and one NPC
room = Room(id='start', description='A small test room.')
room.players.add('sidSmoke')  # ensure audience so AI planning path is permitted
room.npcs.add('Innkeeper')
srv.world.rooms['start'] = room
srv.world.start_room_id = 'start'

# Ensure the NPC has a sheet and set needs to trigger hunger planning
sheet = srv._ensure_npc_sheet('Innkeeper')
sheet.hunger = 10.0
sheet.thirst = 80.0
sheet.action_points = 2
sheet.plan_queue = []

# Place a food object in the room
bread = Object(display_name='Bread', description='A crusty loaf.', object_tags={'small'})
bread.satiation_value = 60
bread.hydration_value = 0
room.objects[bread.uuid] = bread

# Stub the planning model to return a deterministic plan
class _FakeAIResponse:
    def __init__(self, text: str):
        self.text = text

class _FakePlanModel:
    def generate_content(self, prompt, safety_settings=None):  # noqa: D401
        plan = [
            {"tool": "get_object", "args": {"object_name": "Bread"}},
            {"tool": "consume_object", "args": {"object_uuid": bread.uuid}},
        ]
        return _FakeAIResponse(json.dumps(plan))

srv.plan_model = _FakePlanModel()

# Ask the NPC to think (queue a plan) then execute up to two actions
srv.npc_think('Innkeeper')
print(f"Plan queued: {sheet.plan_queue}")

rid = 'start'
steps = 0
while sheet.plan_queue and sheet.action_points > 0 and steps < 3:
    action = sheet.plan_queue.pop(0)
    srv._npc_execute_action('Innkeeper', rid, action)
    sheet.action_points -= 1
    steps += 1

print("Needs after:", {"hunger": sheet.hunger, "thirst": sheet.thirst})
print("Done.")
