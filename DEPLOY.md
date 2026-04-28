# Deploy WintoEurope Bot

## Local source of truth

Use this folder as the only source of truth:

- `бэк.py`
- `.env.example`
- `requirements.txt`
- `wintoeurope-bot.service.example`

## Target layout on VPS

```bash
/opt/vpn-bot/
  back.py
  .env
  requirements.txt
  .venv/
```

## First-time setup on VPS

```bash
sudo mkdir -p /opt/vpn-bot
cd /opt/vpn-bot
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## Copy files from local machine

Copy these files to `/opt/vpn-bot`:

- `бэк.py` -> rename to `back.py` on the server
- `.env`
- `requirements.txt`

## Run manually

```bash
cd /opt/vpn-bot
/opt/vpn-bot/.venv/bin/python /opt/vpn-bot/back.py
```

## systemd service

Copy `wintoeurope-bot.service.example` to:

```bash
/etc/systemd/system/wintoeurope-bot.service
```

Then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable wintoeurope-bot
sudo systemctl restart wintoeurope-bot
sudo systemctl status wintoeurope-bot --no-pager
```

## Logs

```bash
journalctl -u wintoeurope-bot -n 100 --no-pager
```

## Restart after code update

```bash
sudo systemctl restart wintoeurope-bot
```

## Check what file is actually running

```bash
ps aux | grep -E 'python|back|bot' | grep -v grep
cat /proc/PID/cmdline | tr '\\0' ' '
readlink -f /proc/PID/cwd
```
