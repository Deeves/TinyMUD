# Deploy the AI MUD Python server to Google Cloud (e2-micro)

This guide shows how to run `server/server.py` 24/7 on a tiny, low-cost e2-micro VM on Google Compute Engine (GCE). It covers VM creation, firewall, Python setup, service auto-start, HTTPS via Cloud Run proxy (optional), and troubleshooting.

Works for a fresh Google Cloud project and a brand‑new VM.

---

## What you'll build

- A Compute Engine VM (e2-micro) running Ubuntu LTS
- Python 3.11+ with a virtualenv and your app installed
- The server listening on port 5000 and bound to 0.0.0.0 so clients can connect
- A systemd service that restarts the app on failure and on reboot
- A firewall rule that allows inbound TCP 5000 (or a different port you choose)
- Optional: A Cloud NAT or static external IP, and optional HTTPS via Cloud Run or a reverse proxy

---

## Prerequisites

- A Google Cloud account and a project with billing enabled
- gcloud CLI installed locally (optional but recommended)
- The repo available (git clone or zipped upload)
- A Gemini API key (optional). If you want AI replies, set one of:
  - `GEMINI_API_KEY`
  - `GOOGLE_API_KEY`

Without a key, the server will run with a friendly offline NPC fallback.

---

## 1) Create the VM

You can do this in the Console or with gcloud. The examples assume Ubuntu 22.04 LTS and open TCP/5000.

### Option A: Console (UI)

1. Go to Compute Engine > VM instances > Create instance
2. Name: `ai-mud-e2micro`
3. Region/Zone: your choice (keep latency in mind)
4. Machine type: Series e2, Machine type `e2-micro`
5. Boot disk: Ubuntu 22.04 LTS (x86/amd64), 10–20 GB
6. Firewall: check "Allow HTTP" only if you plan to serve port 80/443; we'll add a custom rule for 5000 below
7. Click Create

After creation, note the External IP.

### Option B: gcloud (CLI)

Replace REGION and ZONE accordingly.

```powershell
# PowerShell example using gcloud
$PROJECT = "YOUR_GCP_PROJECT_ID"
$REGION = "us-central1"
$ZONE = "us-central1-a"

gcloud config set project $PROJECT

gcloud compute instances create ai-mud-e2micro `
  --zone=$ZONE `
  --machine-type=e2-micro `
  --image-family=ubuntu-2204-lts `
  --image-project=ubuntu-os-cloud `
  --boot-disk-size=20GB `
  --tags=ai-mud
```

The `--tags=ai-mud` lets you attach a firewall rule easily.

---

## 2) Open the firewall for port 5000

Create a firewall rule that allows inbound TCP 5000 from your IP or from 0.0.0.0/0 (public). For testing, opening to the world is fine; for production, restrict to a known IP range if possible.

```powershell
gcloud compute firewall-rules create allow-ai-mud-5000 `
  --allow=tcp:5000 `
  --direction=INGRESS `
  --target-tags=ai-mud `
  --source-ranges=0.0.0.0/0
```

If you created the VM without the `ai-mud` tag, either add the tag to the instance or change `--target-tags` to match.

---

## 3) SSH into the VM

From the Console click SSH, or from CLI:

```powershell
gcloud compute ssh ai-mud-e2micro --zone $ZONE
```

All following commands run inside the VM shell unless noted.

---

## 4) Install system packages and Python

Ubuntu 22.04 includes Python 3.10+. We recommend Python 3.11 or newer for performance with eventlet. Install base tools:

```bash
sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y python3 python3-venv python3-pip git
```

Check versions:

```bash
python3 --version
pip3 --version
```

---

## 5) Get the code onto the VM

Choose one:

- Git clone (recommended):
  ```bash
  cd ~
  git clone https://github.com/YOUR_ORG/ai-multi-user-dungeon.git
  cd ai-multi-user-dungeon
  ```
- Or upload a zip/tar and extract to your home directory, ending with the project at `~/ai-multi-user-dungeon`.

---

## 6) Create a Python virtual environment and install deps

```bash
cd ~/ai-multi-user-dungeon
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

This installs Flask, Flask‑SocketIO, python‑socketio, eventlet, and optional Google Generative AI SDK.

---

## 7) Configure environment and first run

The server defaults to host 127.0.0.1 and port 5000. On a VM you want to listen on all interfaces so clients can reach it.

```bash
export HOST=0.0.0.0
export PORT=5000
# Optional: enable AI replies
export GEMINI_API_KEY=YOUR_GEMINI_KEY
```

Start it manually to verify:

```bash
cd ~/ai-multi-user-dungeon/server
python server.py
```

Expected startup logs:

- "Async mode: eventlet" (if eventlet installed correctly)
- "Listening on: 0.0.0.0:5000"
- If AI key present: "Gemini API configured successfully." Otherwise a message about AI being disabled.

Press Ctrl+C to stop.

---

## 8) Run as a systemd service (auto-restart on reboot)

Create a unit file so the server runs in the background and restarts if it crashes.

```bash
sudo tee /etc/systemd/system/ai-mud.service > /dev/null << 'EOF'
[Unit]
Description=AI MUD Flask-SocketIO Server
After=network.target

[Service]
Type=simple
User=%i
WorkingDirectory=/home/%i/ai-multi-user-dungeon/server
# Use the venv Python
ExecStart=/home/%i/ai-multi-user-dungeon/.venv/bin/python /home/%i/ai-multi-user-dungeon/server/server.py
Restart=always
RestartSec=3
# Environment
Environment=HOST=0.0.0.0
Environment=PORT=5000
# Optional: set your key here, or use an EnvironmentFile
# Environment=GEMINI_API_KEY=REPLACE_ME

[Install]
WantedBy=multi-user.target
EOF
```

Note: The above uses a templated `%i` user. If your Linux username is, for example, `ubuntu`, replace `%i` with that username everywhere or create a user-specific unit at `/etc/systemd/system/ai-mud@ubuntu.service` and enable that template. For simplicity, you can also hardcode your username:

```bash
sudo sed -i "s/%i/ubuntu/g" /etc/systemd/system/ai-mud.service
```

Alternatively, create a user-owned unit under `~/.config/systemd/user/` and enable linger. The global unit above is simpler for beginners.

Reload systemd and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-mud
sudo systemctl start ai-mud
sudo systemctl status ai-mud --no-pager
```

If it fails, check logs:

```bash
journalctl -u ai-mud -e -n 100 --no-pager
```

---

## 9) Test connectivity

From your local machine, browse to:

- http://EXTERNAL_IP:5000/
- WebSocket URL for Godot client: `ws://EXTERNAL_IP:5000/socket.io/?EIO=4&transport=websocket`

In Godot, change the server URL in the options to point to the VM IP and port.

If you want a non-changing IP, reserve a static external IP and attach it to the VM.

---

## 10) Optional: Harden and tune

- Restrict firewall to your office/home IP ranges
- Create a dedicated Linux user (e.g., `aimud`) and chown the repo
- Store secrets in `/etc/ai-mud.env` and reference with `EnvironmentFile=`:
  ```bash
  sudo tee /etc/ai-mud.env > /dev/null << 'EOF'
  GEMINI_API_KEY=REPLACE_ME
  HOST=0.0.0.0
  PORT=5000
  EOF
  sudo chmod 600 /etc/ai-mud.env
  sudo sed -i 's|^Environment=.*||' /etc/systemd/system/ai-mud.service
  echo -e "\nEnvironmentFile=/etc/ai-mud.env" | sudo tee -a /etc/systemd/system/ai-mud.service
  sudo systemctl daemon-reload
  sudo systemctl restart ai-mud
  ```
- Backups: the world state persists to `server/world_state.json`. Periodically copy it off-VM.
- OS Updates: enable unattended-upgrades on Ubuntu.

---

## 11) Optional: HTTPS and domain

WebSockets don’t require HTTPS strictly, but browsers enforce WSS on https pages. Options:

- Simpler: Put a reverse proxy like Caddy or Nginx on the VM to terminate TLS on :443 and forward to 127.0.0.1:5000
- Managed: Place the VM behind a Google HTTPS Load Balancer or run behind Cloud Run/Cloud Run Jobs acting as a proxy

Example: Caddy on the VM (auto TLS via Let’s Encrypt):

```bash
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo tee /etc/apt/keyrings/caddy-stable.asc
echo "deb [signed-by=/etc/apt/keyrings/caddy-stable.asc] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update
sudo apt-get install -y caddy
```

Caddyfile:

```bash
sudo tee /etc/caddy/Caddyfile > /dev/null << 'EOF'
YOUR_DOMAIN {
  encode zstd gzip
  reverse_proxy 127.0.0.1:5000
}
EOF
sudo systemctl reload caddy
```

Point your DNS A record to the VM external IP first.

---

## Troubleshooting

- Server prints: "WARNING: eventlet not installed. Falling back..."
  - Ensure the venv is active and `pip install -r requirements.txt` completed without errors
- Client cannot connect
  - Confirm service is `Listening on: 0.0.0.0:5000`
  - Check GCE firewall rule allows TCP/5000 to the instance tag
  - Verify external IP and that the VM isn’t behind a corporate NAT blocking inbound
- Port already in use
  - Change `PORT` in the env file and firewall rule accordingly
- AI replies not appearing
  - Set a valid `GEMINI_API_KEY` or `GOOGLE_API_KEY` in the environment the service runs under
- After reboot the service didn’t start
  - `systemctl is-enabled ai-mud` should be enabled; check `journalctl -u ai-mud`

---

## Reference

- App entrypoint: `server/server.py`
- Default port: `5000` (override via `PORT`)
- Bind host: `127.0.0.1` by default; use `HOST=0.0.0.0` for external clients
- Dependencies: see `requirements.txt`
- Persistent data: `server/world_state.json`

Happy adventuring on the cloud!
