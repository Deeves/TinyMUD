# TinyMUD Project Overview

## Purpose
TinyMUD is a minimalistic, extensible MUD (Multi-User Dungeon) server built with cutting-edge technology. It's designed as a thought experiment in modern MUD architecture.

## Tech Stack
- **Client**: Godot 4 (GDScript) - lightweight chat-based interface
- **Server**: Python Flask-SocketIO with optional Google Gemini AI integration
- **Transport**: Socket.IO (EIO v4) over WebSocket
- **Persistence**: Single JSON file (world_state.json)
- **AI**: Google Gemini API for NPC interactions and GOAP planning

## Key Features
- AI-powered NPCs with GOAP (Goal-Oriented Action Planning)
- Real-time multiplayer text adventure
- Admin tools for world building
- Offline fallbacks when AI is unavailable
- Deterministic NPC behavior for testing

## Architecture Patterns
- Router → Service → Emit pattern for command handling
- Service modules return (handled/ok, err, emits[, broadcasts]) tuples
- CommandContext passed to routers with shared state
- Safe execution using safe_call() utilities
- Fuzzy resolution for user input parsing