
# ⚡ NetConfig v1.0.0

A self-hosted network device management platform built with Flask, Docker, and Redis. Manage Cisco, Arista, Juniper, HP, MikroTik, and Ubiquiti UniFi devices from a single dark-themed web interface.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-green)
![Docker](https://img.shields.io/badge/Docker-Compose-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 🎯 Features

### Device Management
- Connect to devices via SSH or UniFi API
- Disconnect/reconnect with persistent state (survives container restarts)
- Per-device polling toggle
- Auto-reconnect using encrypted stored credentials
- Delete devices from management

### Live Monitoring
- Real-time online/offline status indicators (green/red)
- Last Seen counter (ticks every second)
- Auto status polling every 30 seconds
- Platform and uptime info pulled on connect

### Configuration Management
- Pull running/startup configuration via SSH
- Push configuration commands to devices
- Configuration backup history (last 20 per device)
- UniFi devices return API-formatted config (networks, ports, PoE)

### VLAN Management
- Global VLAN definitions with subnet/gateway
- Deploy VLANs across all devices (SSH + UniFi)
- Per-port VLAN assignment (access or trunk)
- Port map table with live status, VLAN, speed, and description
- Inline interface description editing
- Delete global VLANs

### Network Topology
- Auto-generated SVG topology diagram
- Devices layered by type (gateway → core → switch → AP)
- Online/offline color-coded links
- UniFi devices highlighted in blue

### UniFi Integration
- UDM-Pro / UniFi OS authentication
- Auto-discovery of all adopted devices
- Port table with PoE status and power draw
- VLAN/network creation via controller API

---

## 🖥️ Supported Devices

| Type | Protocol | Notes |
|------|----------|-------|
| Cisco IOS / IOS-XE / NX-OS | SSH (Netmiko) | Full support |
| Arista EOS | SSH (Netmiko) | Full support |
| Juniper JunOS | SSH (Netmiko) | Full support |
| HP ProCurve | SSH (Netmiko) | Full support |
| MikroTik RouterOS | SSH (Netmiko) | Full support |
| UniFi Switch (USW) | UniFi API | Ports, VLANs, PoE |
| UniFi Gateway (UDM) | UniFi API | Networks, config |
| UniFi Access Point (UAP) | UniFi API | Status, uptime |

---

## 🚀 Quick Start

### Prerequisites
- Docker + Docker Compose
- Python 3 (for key generation during setup)
- Linux host on the same network as managed devices
- UniFi local admin account (if managing UniFi devices)

### First-Time Setup
```
git clone https://github.com/Skrrrr88/netconfig.git
cd netconfig
bash setup.sh
```

---

## Setup Script 

| Step | What it does |
|------|-------------|
| 1 | Auto-generates encryption keys (SECRET_KEY + FERNET_KEY) |
| 2 | Configures app port, SSH timeout, and worker count |
| 3 | UniFi controller setup (URL, username, password) — or skip if not applicable |
| 4 | Default SSH credentials for new devices |
| 5 | Writes all settings to `.env` |
| 6 | Optionally builds and launches the Docker stack |

### Re-running Setup
To reconfigure at any time, just run bash setup.sh again. It will regenerate keys and overwrite the .env file.

    ⚠️ Warning: Re-running setup generates new encryption keys. If you already have devices saved, their stored passwords will become unreadable. Back up your .env file before re-running.

--- 

### Common Commands
| Command | Description |
|---------|-------------|
| `sudo docker compose up -d` | Start NetConfig |
| `sudo docker compose down` | Stop NetConfig |
| `sudo docker compose logs -f` | View live logs |
| `sudo docker compose up -d --build` | Rebuild after changes |
| `sudo docker compose restart netconfig` | Restart app only |