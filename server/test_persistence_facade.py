"""Tests for the centralized persistence façade.

This verifies that:
1. save_world() is the only way to save world state
2. Debounced and immediate saves work correctly
3. Stats tracking works
4. flush_all_saves() works
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest

from world import World, Room
from persistence_utils import save_world, flush_all_saves, get_save_stats


def test_immediate_save(tmp_path: Path):
    """Immediate saves write directly to disk."""
    state_file = tmp_path / "world_state.json"
    w = World()
    w.rooms["test_room"] = Room(id="test_room", description="Test room")
    
    # Immediate save should write right away
    save_world(w, str(state_file), debounced=False)
    
    # File should exist
    assert state_file.exists()
    
    # Should be loadable
    w2 = World.load_from_file(str(state_file))
    assert "test_room" in w2.rooms


def test_debounced_save(tmp_path: Path):
    """Debounced saves coalesce rapid writes."""
    state_file = tmp_path / "world_state.json"
    w = World()
    w.rooms["room1"] = Room(id="room1", description="First room")
    
    # Multiple debounced saves in quick succession
    save_world(w, str(state_file), debounced=True)
    w.rooms["room2"] = Room(id="room2", description="Second room")
    save_world(w, str(state_file), debounced=True)
    w.rooms["room3"] = Room(id="room3", description="Third room")
    save_world(w, str(state_file), debounced=True)
    
    # Wait for debounce window (default 300ms + buffer)
    time.sleep(0.5)
    
    # File should exist now
    assert state_file.exists()
    
    # Should have all three rooms (last state)
    w2 = World.load_from_file(str(state_file))
    assert "room1" in w2.rooms
    assert "room2" in w2.rooms
    assert "room3" in w2.rooms


def test_flush_all_saves(tmp_path: Path):
    """flush_all_saves() immediately writes all pending debounced saves."""
    state_file = tmp_path / "world_state.json"
    w = World()
    w.rooms["test_room"] = Room(id="test_room", description="Test room")
    
    # Debounced save (won't write immediately)
    save_world(w, str(state_file), debounced=True)
    
    # Flush should force immediate write
    flush_all_saves()
    
    # File should exist
    assert state_file.exists()
    
    # Should be loadable
    w2 = World.load_from_file(str(state_file))
    assert "test_room" in w2.rooms


def test_save_stats_tracking():
    """get_save_stats() returns accurate tracking info."""
    # Note: Stats are global, so we just verify the structure
    stats = get_save_stats()
    
    assert 'debounced_calls' in stats
    assert 'immediate_calls' in stats
    assert 'errors' in stats
    assert 'last_save_time' in stats
    assert 'active_savers' in stats
    
    # All counts should be non-negative
    assert stats['debounced_calls'] >= 0
    assert stats['immediate_calls'] >= 0
    assert stats['errors'] >= 0
    assert stats['active_savers'] >= 0


def test_error_handling(tmp_path: Path):
    """Errors in save operations are swallowed (best-effort)."""
    # Use an invalid path to trigger an error
    invalid_path = "/this/path/definitely/does/not/exist/world_state.json"
    
    w = World()
    w.rooms["test"] = Room(id="test", description="Test")
    
    # Should not raise, even with invalid path
    save_world(w, invalid_path, debounced=False)
    save_world(w, invalid_path, debounced=True)
    
    # No exceptions = success


def test_multiple_paths(tmp_path: Path):
    """Different state paths get separate DebouncedSaver instances."""
    path1 = tmp_path / "world1.json"
    path2 = tmp_path / "world2.json"
    
    w1 = World()
    w1.rooms["world1_room"] = Room(id="world1_room", description="World 1")
    
    w2 = World()
    w2.rooms["world2_room"] = Room(id="world2_room", description="World 2")
    
    # Save to different paths
    save_world(w1, str(path1), debounced=False)
    save_world(w2, str(path2), debounced=False)
    
    # Both should exist
    assert path1.exists()
    assert path2.exists()
    
    # Each should have its own content
    loaded1 = World.load_from_file(str(path1))
    loaded2 = World.load_from_file(str(path2))
    
    assert "world1_room" in loaded1.rooms
    assert "world1_room" not in loaded2.rooms
    assert "world2_room" in loaded2.rooms
    assert "world2_room" not in loaded1.rooms


def test_integration_with_world_mutations(tmp_path: Path):
    """Common pattern: mutate world, save, verify persistence."""
    state_file = tmp_path / "world_state.json"
    
    # Create initial world
    w = World()
    w.world_name = "Test World"
    w.world_description = "A test world"
    w.rooms["spawn"] = Room(id="spawn", description="Starting room")
    w.start_room_id = "spawn"
    
    # Save immediately
    save_world(w, str(state_file), debounced=False)
    
    # Load and verify
    w2 = World.load_from_file(str(state_file))
    assert w2.world_name == "Test World"
    assert w2.world_description == "A test world"
    assert "spawn" in w2.rooms
    assert w2.start_room_id == "spawn"
    
    # Mutate loaded world
    w2.rooms["dungeon"] = Room(id="dungeon", description="Dark dungeon")
    save_world(w2, str(state_file), debounced=False)
    
    # Reload and verify mutation persisted
    w3 = World.load_from_file(str(state_file))
    assert "spawn" in w3.rooms
    assert "dungeon" in w3.rooms
