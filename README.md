
# ⚡ NetConfig v1.1.0

A self-hosted network device management platform built with Flask, Docker, and Redis. Manage Cisco, Arista, Juniper, HP, MikroTik, and Ubiquiti UniFi devices from a single dark-themed web interface.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-green)
![Docker](https://img.shields.io/badge/Docker-Compose-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 🆕 What's New in v1.1.0

### 🔐 Authentication System
- Session-based login/logout with Flask-Login
- First user to register becomes admin automatically
- Role-based access control: **Admin**, **Operator**, **Viewer**
- Admin-only user registration (no open signups after first user)
- Protected API routes with `@login_required` decorator
- `/auth/me` endpoint for session validation

### 🔀 Configuration Diff Engine
- **Execute Diff** — live comparison of running vs startup config
- **Unified view** — color-coded additions (green) and deletions (red) with `@@` hunk headers
- **Side-by-side view** — full configs displayed with line numbers, LCS-based alignment, and highlighted changes
- **History & Diff** — browse backup history and compare any backup against current or previous backups
- **Diff vs Current** — compare any saved backup against the live running config
- **Stats bar** — addition/deletion counts at a glance
- **Save to File** — export config output to `.txt`

### 🎨 UI Improvements
- Removed redundant "Diff" button from config manager
- Dark-themed styling applied to all config action buttons
- Consistent `btn btn-secondary` class usage across new controls

---

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
- **Config diff: running vs startup with unified and side-by-side views**
- **Backup history with diff comparisons**
- Command validation before push
- UniFi devices return API-formatted config (networks, ports, PoE)

### Authentication & Access Control
- Session-based authentication with secure cookies
- Role-based permissions (Admin / Operator / Viewer)
- First-user auto-admin provisioning
- Protected routes — unauthenticated users redirected to login

### VLAN Management
- Global VLAN definitions with subnet/gateway
- Deploy VLANs across all devices (SSH + UniFi)
- Per-port VLAN assignment (access or trunk)
- Port map table with live status, VLAN, speed, and description
- Inline interface description editing
- Delete global VLANs

### SNMP Monitoring
- CPU, memory, and temperature polling
- Interface traffic stats (in/out Mbps)
- System info (sysName, firmware, serial, uptime)
- Environment status (PSUs, fans)
- Alert history with severity levels

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
```bash
git clone https://github.com/Skrrrr88/Netconfig.git
cd Netconfig
bash setup.sh
