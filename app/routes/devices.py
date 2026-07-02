
from flask import Blueprint, request, jsonify
from datetime import datetime
from app.extensions import db
from app.models import Device
from app.services.ssh_service import ssh_service
from app.services.unifi_service import UniFiService
from cryptography.fernet import Fernet
from flask_login import login_required, current_user
from app.decorators import api_login_required, admin_required, operator_required, viewer_required
import os
import re
import logging

devices_bp = Blueprint('devices', __name__)
logger = logging.getLogger(__name__)


def encrypt_password(password):
    key = os.getenv('FERNET_KEY', '')
    if not key:
        return password.encode()
    try:
        return Fernet(key.encode()).encrypt(password.encode())
    except Exception:
        return password.encode()


def decrypt_password(encrypted):
    key = os.getenv('FERNET_KEY', '')
    if not key:
        return encrypted.decode()
    try:
        return Fernet(key.encode()).decrypt(encrypted).decode()
    except Exception:
        return encrypted.decode()


def parse_device_info(output, device_type):
    """Parse show version output for platform and uptime."""
    info = {'platform': '', 'uptime': ''}
    if not output:
        return info

    # Cisco IOS/IOS-XE
    if 'cisco' in device_type:
        match = re.search(r'(?:Cisco\s+)?(\S+\s*\S*)\s+(?:processor|Software)', output, re.IGNORECASE)
        model_match = re.search(r'[Mm]odel\s+[Nn]umber\s*:\s*(\S+)', output)
        hw_match = re.search(r'cisco\s+(\S+)', output, re.IGNORECASE)
        if model_match:
            info['platform'] = model_match.group(1)
        elif hw_match:
            info['platform'] = f"Cisco {hw_match.group(1)}"
        uptime_match = re.search(r'uptime is\s+(.+)', output, re.IGNORECASE)
        if uptime_match:
            info['uptime'] = uptime_match.group(1).strip()

    # Arista EOS
    elif 'arista' in device_type:
        model_match = re.search(r'Arista\s+(\S+)', output)
        if model_match:
            info['platform'] = f"Arista {model_match.group(1)}"
        uptime_match = re.search(r'Uptime:\s+(.+)', output)
        if uptime_match:
            info['uptime'] = uptime_match.group(1).strip()

    # Juniper
    elif 'juniper' in device_type:
        model_match = re.search(r'Model:\s*(\S+)', output)
        if model_match:
            info['platform'] = f"Juniper {model_match.group(1)}"

    # HP ProCurve
    elif 'hp' in device_type:
        model_match = re.search(r'(J\d+\S+)', output)
        if model_match:
            info['platform'] = f"HP {model_match.group(1)}"

    # MikroTik
    elif 'mikrotik' in device_type:
        model_match = re.search(r'model:\s*(\S+)', output, re.IGNORECASE)
        if model_match:
            info['platform'] = f"MikroTik {model_match.group(1)}"
        uptime_match = re.search(r'uptime:\s*(.+)', output, re.IGNORECASE)
        if uptime_match:
            info['uptime'] = uptime_match.group(1).strip()

    return info


@devices_bp.route('/', methods=['GET'])
@api_login_required
def list_devices():
    devices = Device.query.order_by(Device.hostname).all()
    return jsonify([d.to_dict() for d in devices])


@devices_bp.route('/connect', methods=['POST'])
@operator_required
def connect_device():
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    # Handle UniFi devices
    if data.get('device_type', '').startswith('unifi'):
        controller_url = data.get('unifi_controller_url', '')
        if not controller_url:
            return jsonify({'success': False, 'error': 'UniFi Controller URL required'}), 400
        try:
            unifi = UniFiService(
                controller_url=controller_url,
                username=data.get('username', ''),
                password=data.get('password', ''),
                site=data.get('unifi_site', 'default'),
                verify_ssl=False,
            )
            devices = unifi.get_devices()
            for ud in devices:
                if not ud.get('ip'):
                    continue
                existing = Device.query.filter_by(ip_address=ud['ip']).first()
                if not existing:
                    model = ud.get('model', '')
                    if 'UDM' in model or 'UGW' in model:
                        dtype = 'unifi_gateway'
                    elif 'UAP' in model or 'U6' in model or 'U7' in model:
                        dtype = 'unifi_ap'
                    else:
                        dtype = 'unifi_switch'
                    new_device = Device(
                        hostname=ud.get('name', ud['ip']),
                        ip_address=ud['ip'],
                        device_type=dtype,
                        platform=f"UniFi {model}",
                        mac_address=ud.get('mac', ''),
                        unifi_controller_url=controller_url,
                        unifi_site=data.get('unifi_site', 'default'),
                        is_online=ud.get('state', 0) == 1,
                        last_seen=datetime.utcnow(),
                        uptime=str(ud.get('uptime', '')),
                    )
                    db.session.add(new_device)
                else:
                    existing.is_online = ud.get('state', 0) == 1
                    existing.last_seen = datetime.utcnow()
                    existing.platform = f"UniFi {ud.get('model', '')}"
                    if ud.get('uptime'):
                        hours = int(ud['uptime']) // 3600
                        days = hours // 24
                        existing.uptime = f"{days}d {hours % 24}h" if days else f"{hours}h"
            db.session.commit()
            unifi.logout()
            return jsonify({
                'success': True,
                'message': f'Discovered {len(devices)} UniFi device(s)',
                'devices': [{'name': d.get('name', ''), 'model': d.get('model', ''),
                             'ip': d.get('ip', ''), 'mac': d.get('mac', '')} for d in devices],
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 400

    # Handle SSH devices
    if not data.get('ip_address'):
        return jsonify({'success': False, 'error': 'IP address is required'}), 400

    result = ssh_service.connect({
        'hostname': data.get('hostname', data['ip_address']),
        'ip_address': data['ip_address'],
        'device_type': data.get('device_type', 'cisco_ios'),
        'username': data.get('username', ''),
        'password': data.get('password', ''),
        'port': data.get('port', 22),
        'secret': data.get('secret', ''),
    })

    if result['success']:
        # Gather device info (platform, uptime)
        device_info = {'platform': '', 'uptime': ''}
        try:
            device_type = data.get('device_type', 'cisco_ios')
            if 'mikrotik' in device_type:
                ver_result = ssh_service.send_command(data['ip_address'], '/system resource print')
            elif 'juniper' in device_type:
                ver_result = ssh_service.send_command(data['ip_address'], 'show version')
            else:
                ver_result = ssh_service.send_command(data['ip_address'], 'show version')

            if ver_result.get('success'):
                device_info = parse_device_info(ver_result['output'], device_type)
        except Exception as e:
            logger.warning(f"Could not gather device info: {e}")

        # Save/update device in database
        device = Device.query.filter_by(ip_address=data['ip_address']).first()
        if not device:
            device = Device(
                hostname=data.get('hostname', data['ip_address']),
                ip_address=data['ip_address'],
                device_type=data.get('device_type', 'cisco_ios'),
                ssh_port=data.get('port', 22),
                username=data.get('username', ''),
            )
            if data.get('password'):
                device.password_encrypted = encrypt_password(data['password'])
            db.session.add(device)

        device.is_online = True
        device.manually_disconnected = False
        device.last_seen = datetime.utcnow()
        # Always update stored credentials for auto-reconnect
        if data.get('password'):
            device.password_encrypted = encrypt_password(data['password'])
        if data.get('username'):
            device.username = data['username']
        if device_info.get('platform'):
            device.platform = device_info['platform']
        if device_info.get('uptime'):
            device.uptime = device_info['uptime']
        db.session.commit()

        result['platform'] = device_info.get('platform', '')
        result['uptime'] = device_info.get('uptime', '')

    return jsonify(result)


@devices_bp.route('/disconnect/<ip_address>', methods=['POST'])
@operator_required
def disconnect_device(ip_address):
    ssh_service.disconnect(ip_address)
    device = Device.query.filter_by(ip_address=ip_address).first()
    if device:
        device.manually_disconnected = True
        device.is_online = False
        db.session.commit()
    device = Device.query.filter_by(ip_address=ip_address).first()
    if device:
        device.is_online = False
        db.session.commit()
    return jsonify({'success': True, 'message': f'Disconnected from {ip_address}'})


@devices_bp.route('/test', methods=['POST'])
@operator_required
def test_connection():
    data = request.json
    result = ssh_service.connect({
        'hostname': data.get('hostname', data.get('ip_address', '')),
        'ip_address': data.get('ip_address', ''),
        'device_type': data.get('device_type', 'cisco_ios'),
        'username': data.get('username', ''),
        'password': data.get('password', ''),
        'port': data.get('port', 22),
        'secret': data.get('secret', ''),
    })
    if result['success']:
        ssh_service.disconnect(data.get('ip_address', ''))
    return jsonify(result)


@devices_bp.route('/<int:device_id>', methods=['DELETE'])
@admin_required
def delete_device(device_id):
    device = Device.query.get_or_404(device_id)
    ssh_service.disconnect(device.ip_address)
    db.session.delete(device)
    db.session.commit()
    return jsonify({'success': True, 'message': f'{device.hostname} removed'})


@devices_bp.route('/interfaces/<ip_address>', methods=['GET'])
@api_login_required
def get_interfaces(ip_address):
    """Get interface/port information for a device."""
    device = Device.query.filter_by(ip_address=ip_address).first()
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404

    device_type = device.device_type or 'cisco_ios'

    # UniFi devices use the API, not SSH
    if 'unifi' in device_type:
        return get_unifi_interfaces(device)

    # SSH devices
    if 'mikrotik' in device_type:
        result = ssh_service.send_command(ip_address, '/interface print')
    elif 'juniper' in device_type:
        result = ssh_service.send_command(ip_address, 'show interfaces terse')
    elif 'hp' in device_type:
        result = ssh_service.send_command(ip_address, 'show interfaces brief')
    else:
        result = ssh_service.send_command(ip_address, 'show interfaces status')

    if not result.get('success'):
        return jsonify({'success': False, 'error': result.get('error', 'Failed to get interfaces')})

    # Parse interfaces
    interfaces = parse_interfaces(result.get('output', ''), device_type)
    return jsonify({'success': True, 'interfaces': interfaces})


def get_unifi_interfaces(device):
    """Get port info from UniFi device via API."""
    try:
        from app.services.unifi_service import UniFiService
        from cryptography.fernet import Fernet

        controller_url = device.unifi_controller_url
        site = device.unifi_site or 'default'

        if not controller_url:
            return jsonify({'success': False, 'error': 'No UniFi controller URL stored'}), 400

        # Get UniFi credentials from .env or from the device that discovered it
        username = os.getenv('UNIFI_USERNAME', '')
        password = os.getenv('UNIFI_PASSWORD', '')

        if not username or not password:
            return jsonify({'success': False, 'error': 'UniFi credentials not configured in .env'}), 400

        unifi = UniFiService(
            controller_url=controller_url,
            username=username,
            password=password,
            site=site,
            verify_ssl=False,
        )

        # Find device by MAC or IP
        devices = unifi.get_devices()
        target = None
        for d in devices:
            if d.get('ip') == device.ip_address or d.get('mac', '').lower() == (device.mac_address or '').lower():
                target = d
                break

        if not target:
            unifi.logout()
            return jsonify({'success': False, 'error': 'Device not found on UniFi controller'})

        # Get port table
        port_table = target.get('port_table', [])
        networks = unifi.get_networks()
        unifi.logout()

        # Build network ID to VLAN name map
        net_map = {}
        for n in networks:
            net_map[n.get('_id', '')] = {'name': n.get('name', ''), 'vlan': n.get('vlan', '')}

        interfaces = []
        for port in port_table:
            port_idx = port.get('port_idx', 0)
            is_up = port.get('up', False)
            speed = port.get('speed', 0)
            name = port.get('name', f'Port {port_idx}')
            native_net = port.get('native_networkconf_id', '')
            vlan_info = net_map.get(native_net, {})
            vlan_display = vlan_info.get('vlan', '') or vlan_info.get('name', '')

            interfaces.append({
                'port': name if name != f'Port {port_idx}' else f'Port {port_idx}',
                'status': 'up' if is_up else 'down',
                'vlan': vlan_display,
                'speed': f'{speed}M' if speed else '',
                'description': name,
                'poe': port.get('poe_enable', False),
                'poe_power': port.get('poe_power', ''),
            })

        return jsonify({'success': True, 'interfaces': interfaces})

    except Exception as e:
        logger.error(f"UniFi interface fetch error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@devices_bp.route('/reconnect/<ip_address>', methods=['POST'])
@operator_required
def reconnect_device(ip_address):
    """Force reconnect to a device using stored credentials."""
    device = Device.query.filter_by(ip_address=ip_address).first()
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404

    # For UniFi devices, just verify via API
    if 'unifi' in (device.device_type or ''):
        try:
            from app.services.unifi_service import UniFiService
            import os
            unifi = UniFiService(
                controller_url=device.unifi_controller_url or os.getenv('UNIFI_CONTROLLER_URL', ''),
                username=os.getenv('UNIFI_USERNAME', ''),
                password=os.getenv('UNIFI_PASSWORD', ''),
                site=device.unifi_site or 'default',
                verify_ssl=False,
            )
            devices = unifi.get_devices()
            target = None
            for d in devices:
                if d.get('ip') == ip_address or d.get('mac', '').lower() == (device.mac_address or '').lower():
                    target = d
                    break
            unifi.logout()
            if target:
                device.is_online = target.get('state', 0) == 1
                uptime_sec = target.get('uptime', 0)
                if uptime_sec:
                    days = uptime_sec // 86400
                    hours = (uptime_sec % 86400) // 3600
                    device.uptime = f'{days}d {hours}h'
                device.platform = f"UniFi {target.get('model', '')}"
                device.last_seen = datetime.utcnow()
                db.session.commit()
                return jsonify({'success': True, 'message': f'Reconnected to {device.hostname}', 'platform': device.platform, 'uptime': device.uptime})
            return jsonify({'success': False, 'error': 'Device not found on controller'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    # For SSH devices, disconnect and reconnect
    ssh_service.disconnect(ip_address)

    if not device.password_encrypted:
        return jsonify({'success': False, 'error': 'No stored credentials. Please connect manually.'})

    # Decrypt password
    key = os.environ.get('FERNET_KEY', '')
    try:
        if key:
            password = Fernet(key.encode()).decrypt(device.password_encrypted).decode()
        else:
            password = device.password_encrypted.decode() if isinstance(device.password_encrypted, bytes) else str(device.password_encrypted)
    except Exception:
        return jsonify({'success': False, 'error': 'Failed to decrypt stored credentials'})

    result = ssh_service.connect({
        'hostname': device.hostname,
        'ip_address': device.ip_address,
        'device_type': device.device_type or 'cisco_ios',
        'username': device.username or '',
        'password': password,
        'port': device.ssh_port or 22,
        'secret': '',
    })

    if result.get('success'):
        device.is_online = True
        device.manually_disconnected = False
        device.last_seen = datetime.utcnow()
        # Refresh platform/uptime
        try:
            ver_result = ssh_service.send_command(ip_address, 'show version')
            if ver_result.get('success'):
                info = parse_device_info(ver_result['output'], device.device_type or 'cisco_ios')
                if info.get('platform'):
                    device.platform = info['platform']
                if info.get('uptime'):
                    device.uptime = info['uptime']
        except Exception:
            pass
        db.session.commit()

    return jsonify(result)


def parse_interfaces(output, device_type):
    """Parse interface status output into structured data."""
    interfaces = []
    if not output:
        return interfaces

    lines = output.strip().split('\n')

    if 'cisco' in device_type or 'arista' in device_type:
        # Skip header lines
        for line in lines:
            parts = line.split()
            if len(parts) >= 2 and not line.startswith('Port') and not line.startswith('-'):
                port_name = parts[0]
                # Skip non-physical interfaces
                if any(x in port_name.lower() for x in ['vlan', 'loop', 'null', 'cpu']):
                    continue
                status = 'up' if 'connected' in line.lower() else 'down'
                vlan = ''
                speed = ''
                # Try to extract VLAN and speed from typical "show interfaces status" output
                for p in parts:
                    if p.isdigit() and int(p) < 4095:
                        vlan = p
                    if 'a-' in p or '/' in p and ('G' in p or 'M' in p):
                        speed = p
                interfaces.append({
                    'port': port_name,
                    'status': status,
                    'vlan': vlan,
                    'speed': speed,
                    'description': '',
                })
    else:
        # Generic parsing
        for line in lines:
            parts = line.split()
            if len(parts) >= 2 and not line.startswith('#') and not line.startswith('-'):
                interfaces.append({
                    'port': parts[0],
                    'status': 'up' if 'up' in line.lower() else 'down',
                    'vlan': '',
                    'speed': '',
                    'description': '',
                })

    return interfaces

