# TinyMUD Development Commands

## Environment Setup
- **Create venv**: From project root, Python will auto-create if needed
- **Install deps**: `python -m pip install -r .\requirements.txt` (from repo root)
- **Set API key**: `$env:GEMINI_API_KEY = "YOUR_KEY_HERE"` (PowerShell)

## Running the Application
- **Start server**: `python server\server.py` or use VS Code task "Run server to verify startup print"
- **Run client**: Open `project.godot` in Godot 4, run `ChatUI.tscn` scene
- **Reset world**: `python server\server.py --purge --yes` 

## Testing
- **Run tests**: `pytest -q server` (from repo root) or VS Code task "Run pytest server"
- **Test specific module**: `pytest server/test_specific.py`

## Windows PowerShell Commands
- **Directory listing**: `ls` or `dir`
- **Change directory**: `cd path`
- **Find files**: `Get-ChildItem -Recurse -Name "*pattern*"`
- **Search in files**: `Select-String -Path "*.py" -Pattern "search_term"`
- **Git operations**: Standard git commands work in PowerShell

## Development Workflow
1. Make changes to server code
2. Run tests: `pytest -q server`
3. Test manually by starting server and client
4. Check for AI functionality if Gemini key is set