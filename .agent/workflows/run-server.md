---
description: Start the TinyMUD development server
---

# Run Server Workflow

## Quick Start

// turbo

1. Start the server:

```bash
cd server && python server.py
```

The server will start on `http://localhost:5000` by default.

## With Environment Variables

2. Start with custom settings:

```bash
cd server && set MUD_TICK_ENABLE=1 && set MUD_TICK_SECONDS=30 && python server.py
```

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MUD_TICK_ENABLE` | `0` | Enable world tick (NPC actions) |
| `MUD_TICK_SECONDS` | `60` | Seconds between ticks |
| `MUD_SAVE_DEBOUNCE_MS` | `5000` | Save debounce interval |
| `MUD_MAX_MESSAGE_LEN` | `1000` | Max message length |
| `MUD_RATE_ENABLE` | `0` | Enable rate limiting |
| `GEMINI_API_KEY` | - | Google AI API key for NPC AI |

## Reset World State

// turbo
3. Purge and reset to defaults:

```bash
cd server && python server.py --purge --yes
```

## Debug Mode

4. Run with Flask debug mode:

```bash
cd server && set FLASK_DEBUG=1 && python server.py
```
