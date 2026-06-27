from flask import Blueprint, jsonify
from app.extensions import db
from app.models import Device
from datetime import datetime
import socket
import os
import logging

status_bp = Blueprint('status', __name__)
logger = logging.getLogger(__name__)


@status_bp.route('/', methods=['GET'])
def check_all_status():
    devices = Device.query.all()
    results = []

    for device in devices:
        info = {
            'id': device.id,
            'ip_address': device.ip_address,
            'hostname': device.hostname,
        }

        # Skip status check for manually disconnected devices
        if device.manually_disconnected:
            info['is_online'] = False
            device.is_online = False
            info['last_seen'] = device.last_seen.isoformat() if device.last_seen else None
            results.append(info)
            continue

        if 'unifi' in (device.device_type or ''):
            info['is_online'] = check_unifi(device)
        else:
            info['is_online'] = check_ssh(device)

        if info['is_online']:
            device.last_seen = datetime.utcnow()
        device.is_online = info['is_online']
        info['last_seen'] = device.last_seen.isoformat() if device.last_seen else None
        results.append(info)

    db.session.commit()
    return jsonify(results)


def check_ssh(device):
    from app.services.ssh_service import ssh_service
    # If manually disconnected, report as offline
    if device.ip_address in ssh_service.manually_disconnected:
        return False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((device.ip_address, device.ssh_port or 22))
        sock.close()
        return result == 0
    except Exception:
        return False


def check_unifi(device):
    try:
        from app.services.unifi_service import UniFiService
        url = device.unifi_controller_url or os.getenv('UNIFI_CONTROLLER_URL', '')
        user = os.getenv('UNIFI_USERNAME', '')
        pw = os.getenv('UNIFI_PASSWORD', '')
        if not url or not user or not pw:
            return device.is_online

        unifi = UniFiService(controller_url=url, username=user, password=pw, site=device.unifi_site or 'default', verify_ssl=False)
        api_devs = unifi.get_devices()
        unifi.logout()

        for d in api_devs:
            if d.get('ip') == device.ip_address or d.get('mac', '').lower() == (device.mac_address or '').lower():
                uptime_sec = d.get('uptime', 0)
                if uptime_sec:
                    days = uptime_sec // 86400
                    hours = (uptime_sec % 86400) // 3600
                    device.uptime = f'{days}d {hours}h'
                return d.get('state', 0) == 1
        return False
    except Exception as e:
        logger.warning(f"UniFi status check failed: {e}")
        return device.is_online
