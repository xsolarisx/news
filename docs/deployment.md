# Deployment Guide — Proxmox LXC

This guide covers running News Digest in a Proxmox LXC container with a systemd timer that fires at 06:00 and 18:00 daily.

---

## 1. Create the LXC Container

In the Proxmox web UI or via `pct`:

```bash
pct create 200 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname news-digest \
  --cores 1 \
  --memory 512 \
  --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --unprivileged 1 \
  --start 1
```

Recommended specs:

| Resource | Value |
|---|---|
| OS | Debian 12 (Bookworm) |
| CPU | 1 vCPU |
| RAM | 512 MB |
| Disk | 8 GB |
| Network | DHCP or static on your LAN bridge |

Start the container and open a shell:

```bash
pct start 200
pct enter 200
```

---

## 2. System Preparation

Inside the container:

```bash
apt-get update && apt-get upgrade -y
apt-get install -y python3 python3-pip python3-venv git curl
```

---

## 3. Create the Application User and Directories

```bash
useradd --system --shell /usr/sbin/nologin --home /opt/news-digest news-digest
mkdir -p /opt/news-digest
mkdir -p /etc/news-digest
chown news-digest:news-digest /opt/news-digest
```

---

## 4. Clone the Repository and Install Dependencies

```bash
cd /opt/news-digest
git clone <your-repo-url> .
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install aiohttp feedparser rich langdetect anthropic requests
```

On Python versions below 3.11:

```bash
venv/bin/pip install tomli
```

---

## 5. Run setup.sh

If the repository includes a `setup.sh`:

```bash
bash /opt/news-digest/setup.sh
```

This script is expected to:
- Copy `config.toml.example` to `/opt/news-digest/config.toml` if not already present
- Create the SQLite cache directory
- Set permissions

---

## 6. Configure /etc/news-digest/env

Create the environment file that the systemd service will load:

```bash
cat > /etc/news-digest/env << 'EOF'
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
EOF

chmod 600 /etc/news-digest/env
chown news-digest:news-digest /etc/news-digest/env
```

Edit `/opt/news-digest/config.toml` to set SMTP credentials and recipient addresses for email delivery.

---

## 7. Create the systemd Service Unit

```bash
cat > /etc/systemd/system/news-digest.service << 'EOF'
[Unit]
Description=News Digest
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=news-digest
WorkingDirectory=/opt/news-digest
EnvironmentFile=/etc/news-digest/env
ExecStart=/opt/news-digest/venv/bin/python3 /opt/news-digest/news_digest.py \
    --output html \
    --email \
    --config /opt/news-digest/config.toml
StandardOutput=journal
StandardError=journal
EOF
```

---

## 8. Create the systemd Timer Unit

```bash
cat > /etc/systemd/system/news-digest.timer << 'EOF'
[Unit]
Description=Run News Digest at 06:00 and 18:00

[Timer]
OnCalendar=*-*-* 06:00:00
OnCalendar=*-*-* 18:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

---

## 9. Enable and Start the Timer

```bash
systemctl daemon-reload
systemctl enable --now news-digest.timer
```

Verify the timer is active:

```bash
systemctl list-timers news-digest.timer
```

---

## 10. Verify the Timer

```
NEXT                        LEFT     LAST                        PASSED  UNIT
Sat 2026-03-07 06:00:00 UTC 11h left Fri 2026-03-06 18:00:00 UTC 1h ago  news-digest.timer
```

Run it immediately for a test:

```bash
systemctl start news-digest.service
```

---

## 11. Viewing Logs

```bash
# Last run output
journalctl -u news-digest.service -n 50

# Follow live during a run
journalctl -u news-digest.service -f

# All historical runs
journalctl -u news-digest.service --since "2026-03-01"
```

---

## 12. Cron Alternative

If you prefer cron over systemd timers:

```bash
crontab -u news-digest -e
```

Add:

```
0 6,18 * * * cd /opt/news-digest && /opt/news-digest/venv/bin/python3 news_digest.py --output html --email --config /opt/news-digest/config.toml >> /var/log/news-digest.log 2>&1
```

Create the log file with correct ownership:

```bash
touch /var/log/news-digest.log
chown news-digest:news-digest /var/log/news-digest.log
```

---

## 13. Updating

```bash
cd /opt/news-digest
git pull
venv/bin/pip install --upgrade aiohttp feedparser rich langdetect anthropic requests
systemctl restart news-digest.service   # optional: test the new version immediately
```

---

## 14. Troubleshooting

### Service fails immediately

```bash
journalctl -u news-digest.service -n 100 --no-pager
```

Check that the virtual environment exists and the Python path is correct:

```bash
/opt/news-digest/venv/bin/python3 --version
```

### No email received

- Confirm SMTP settings in `config.toml` are correct
- Test manually: `systemctl start news-digest.service` and inspect logs
- Check that port 587 (or 465) is not blocked by the Proxmox host firewall or your ISP

### Feed errors in logs

Lines like `[skip] NZZ: ...` in the journal indicate a feed fetch failed. This is non-fatal; other feeds continue. Use the health check to diagnose:

```bash
/opt/news-digest/venv/bin/python3 /opt/news-digest/news_digest.py --health
```

### Cache stale / unexpected old stories

Delete the cache database to force a full refresh:

```bash
rm /opt/news-digest/cache.db
```

Or run with `--no-cache` once:

```bash
systemctl start news-digest.service
# or manually:
/opt/news-digest/venv/bin/python3 /opt/news-digest/news_digest.py --no-cache
```

### Permission denied on /etc/news-digest/env

```bash
chown news-digest:news-digest /etc/news-digest/env
chmod 600 /etc/news-digest/env
```

### Container loses network after Proxmox host reboot

Ensure the container is set to auto-start:

```bash
# On the Proxmox host
pct set 200 --onboot 1
```
