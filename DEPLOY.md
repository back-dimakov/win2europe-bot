# Deploy Guide

This file describes how to deploy **Win2Europe VPN Bot** on a VPS together with an existing **Marzban** installation.

## Overview

The bot is designed to run as a separate Python service.

Recommended setup:

- `Marzban` runs on the server
- the Telegram bot runs from `/opt/vpn-bot`
- the bot is managed through `systemd`
- environment variables are stored in `/opt/vpn-bot/.env`

## Expected VPS layout

```text
/opt/vpn-bot/
  back.py
  .env
  requirements.txt
  .venv/
  vpn_bot.db
```

## 1. Create the project directory

```bash
mkdir -p /opt/vpn-bot
cd /opt/vpn-bot
python3 -m venv .venv
```

## 2. Copy project files

Copy these files from the repository to the server:

- `back.py`
- `requirements.txt`
- `.env` based on `.env.example`

Do not upload:

- `.env.example` as a runtime config
- `.git`
- local cache files
- `__pycache__`

## 3. Install dependencies

```bash
cd /opt/vpn-bot
/opt/vpn-bot/.venv/bin/pip install -U pip
/opt/vpn-bot/.venv/bin/pip install -r requirements.txt
```

## 4. Configure environment variables

Create `/opt/vpn-bot/.env` from the repository template and fill in real values.

Minimum required variables:

```env
BOT_TOKEN=
SUPPORT_USERNAME=@wintoeurope_bot
SUPPORT_URL=https://t.me/win2europe?direct
ADMIN_IDS=123456789

USE_MOCK_MARZBAN=0

DB_PATH=/opt/vpn-bot/vpn_bot.db
CHECK_EXPIRED_EVERY_SECONDS=60

MARZBAN_BASE_URL=http://127.0.0.1:8000
MARZBAN_USERNAME=
MARZBAN_PASSWORD=
MARZBAN_VLESS_INBOUND=VLESS TCP REALITY

VPN_ADDRESS=vpn.win2europe.xyz
VPN_PORT=443
VPN_SNI=www.microsoft.com
VPN_PUBLIC_KEY=
VPN_SHORT_ID=
VPN_FINGERPRINT=chrome
VPN_ALPN=
VPN_FLOW=xtls-rprx-vision
VPN_SPIDER_X=
```

## 5. Test manual start

Before using `systemd`, verify that the bot starts correctly:

```bash
cd /opt/vpn-bot
/opt/vpn-bot/.venv/bin/python /opt/vpn-bot/back.py
```

Expected result:

- the bot starts polling;
- there is no `TelegramConflictError`;
- the log shows `mock Marzban: False` in production mode.

Stop the manual run with `Ctrl+C` before moving to the service step.

## 6. Configure systemd

Copy the example unit file to the system directory:

```bash
cp /opt/vpn-bot/wintoeurope-bot.service.example /etc/systemd/system/vpn-bot.service
```

If needed, edit it:

```bash
nano /etc/systemd/system/vpn-bot.service
```

Recommended unit:

```ini
[Unit]
Description=WintoEurope VPN Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/vpn-bot
EnvironmentFile=/opt/vpn-bot/.env
ExecStart=/opt/vpn-bot/.venv/bin/python /opt/vpn-bot/back.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then reload and start:

```bash
systemctl daemon-reload
systemctl enable vpn-bot.service
systemctl restart vpn-bot.service
systemctl status vpn-bot.service --no-pager
```

## 7. View logs

```bash
journalctl -u vpn-bot.service -n 100 --no-pager
```

Realtime logs:

```bash
journalctl -u vpn-bot.service -f
```

## 8. Update code after changes

After replacing `back.py` or updating environment variables:

```bash
python3 -m py_compile /opt/vpn-bot/back.py
systemctl restart vpn-bot.service
journalctl -u vpn-bot.service -n 50 --no-pager
```

## 9. Verify the VPN side

Useful server checks:

```bash
ss -tulpn | grep ':443 '
ufw status verbose
getent hosts vpn.win2europe.xyz
```

Useful Marzban checks:

```bash
cd /opt/marzban
docker compose ps
docker logs --tail 80 marzban-marzban-1
```

## 10. Common problems

### TelegramConflictError

Cause:

- more than one bot instance is running with the same token

Fix:

- stop the duplicate instance
- keep only one active polling process

### Bot sends old or invalid links

Check:

- `/opt/vpn-bot/.env`
- `VPN_PUBLIC_KEY`
- `VPN_SHORT_ID`
- `VPN_SNI`
- `VPN_ADDRESS`

Then restart the bot service.

### Marzban is reachable only on localhost

This is acceptable if:

- the bot runs on the same VPS
- the bot accesses Marzban through `http://127.0.0.1:8000`

Public HTTPS for the panel is a separate deployment task.

## 11. Production note

For production use, keep the repository clean and keep secrets out of Git:

- use `.env.example` as a template only
- never commit the real `.env`
- never commit real tokens, passwords, or private keys

