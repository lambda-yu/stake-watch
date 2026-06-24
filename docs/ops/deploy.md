# Deployment

Single-process tool — FastAPI + APScheduler run inside one Python process at port 8000. SQLite is the only datastore.

## Local foreground

```bash
uv sync
uv run python -m stake_watch.main
```

The frontend dev server (`cd frontend && npm run dev`) is for **development** only — Vite proxies `/api/*` to `localhost:8000`. In production, build the SPA once and serve the static bundle behind any reverse proxy:

```bash
cd frontend && npm run build
# bundle in frontend/dist/ — serve with caddy / nginx / static host
```

## systemd (Linux)

`/etc/systemd/system/stake-watch.service`:

```ini
[Unit]
Description=Stake Watch (yield monitor + risk alerts)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=stake-watch
WorkingDirectory=/opt/stake-watch
Environment="DATABASE_URL=sqlite:///opt/stake-watch/data/stake_watch.db"
ExecStart=/opt/stake-watch/.venv/bin/python -m stake_watch.main
Restart=on-failure
RestartSec=10
# Log to journald
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd -r -s /usr/sbin/nologin stake-watch
sudo install -d -o stake-watch -g stake-watch /opt/stake-watch/data
sudo -u stake-watch git clone https://… /opt/stake-watch
cd /opt/stake-watch && sudo -u stake-watch uv sync
sudo systemctl daemon-reload
sudo systemctl enable --now stake-watch
sudo journalctl -u stake-watch -f
```

## macOS launchd

`~/Library/LaunchAgents/dev.stakewatch.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>dev.stakewatch</string>
  <key>WorkingDirectory</key><string>/Users/you/code/stake-watch</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/you/.local/bin/uv</string>
    <string>run</string>
    <string>python</string>
    <string>-m</string>
    <string>stake_watch.main</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/you/Library/Logs/stake-watch.log</string>
  <key>StandardErrorPath</key><string>/Users/you/Library/Logs/stake-watch.err</string>
</dict>
</plist>
```

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.stakewatch.plist
launchctl print gui/$(id -u)/dev.stakewatch
```

## Docker

Minimal Dockerfile:

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY . .
RUN uv sync --frozen
ENV DATABASE_URL=sqlite:////data/stake_watch.db
VOLUME ["/data"]
EXPOSE 8000
CMD ["uv", "run", "python", "-m", "stake_watch.main"]
```

Run:

```bash
docker build -t stake-watch .
docker run -d --name stake-watch \
  -p 8000:8000 \
  -v stake-watch-data:/data \
  --restart unless-stopped \
  stake-watch
```

## Backups

The whole state lives in one SQLite file. Two snapshot routes:

```bash
# Raw .db file
curl -O http://localhost:8000/api/backup/sqlite

# Portable JSON (recommended for archiving — survives schema changes)
curl http://localhost:8000/api/backup/json > backup.json
```

Set a daily cron:

```bash
0 4 * * * curl -sf http://localhost:8000/api/backup/json \
  > /var/backups/stake-watch/$(date +\%F).json && \
  find /var/backups/stake-watch -mtime +30 -delete
```

## Telegram bot

Configure via the **推送配置 (Notifications)** page in the UI, or directly:

```bash
curl -X PUT http://localhost:8000/api/config/telegram \
  -H 'Content-Type: application/json' \
  -d '{"bot_token":"123:abc","chat_id":"-1001234567"}'
curl -X POST http://localhost:8000/api/config/telegram/test
```

Without bot_token + chat_id, the scheduler still runs — alerts are written to the DB and visible at `/alerts` in the UI, just never pushed.

## Upgrades

```bash
git pull
uv sync                          # picks up new Python deps
cd frontend && npm install && npm run build && cd ..
sudo systemctl restart stake-watch
```

Schema changes are lightweight (`ALTER TABLE ADD COLUMN`-style migrations live in `storage/db.py:initialize()`). Always **`/api/backup/sqlite` before** a release with schema changes.

## Health checks

```bash
curl -fs http://localhost:8000/api/status
```

Returns scheduler health + last-collection age + alert counts. Wire this into uptime monitors.
