
import sys
import os

# Add server directory to path
sys.path.append(os.path.join(os.getcwd(), 'server'))

try:
    import server
except ImportError:
    # Fallback if run from root
    sys.path.append('server')
    import server

def verify_help():
    print("Verifying Help Text...")
    
    # Mock World State
    sid = "test_sid"
    server.world.players[sid] = "exists" # Just needs to be in the dict
    
    # 1. Verify Player Help
    print("\n[PLAYER HELP]")
    text = server._build_help_text(sid)
    print(text)
    
    if "[b][u]COMMANDS REFERENCE[/u][/b]" not in text:
        print("FAIL: Header missing")
        return
    if "/settimedesc" in text:
        print("FAIL: Admin command visible to player")
        return
        
    # 2. Verify Admin Help
    print("\n[ADMIN HELP]")
    server.admins.add(sid)
    text_admin = server._build_help_text(sid)
    # print(text_admin) # Too verbose, just check key items
    
    if "/settimedesc" not in text_admin:
        print("FAIL: /settimedesc missing from admin help")
        return
    if "[b][u]ADMINISTRATION[/u][/b]" not in text_admin:
        print("FAIL: Admin header missing")
        return

    print("\nSUCCESS: Help text verified.")

if __name__ == "__main__":
    verify_help()
