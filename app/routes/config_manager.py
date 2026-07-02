from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Device, ConfigBackup
from app.services.ssh_service import ssh_service
import os
import logging
import difflib


config_bp = Blueprint('config', __name__)
logger = logging.getLogger(__name__)


@config_bp.route('/running/<ip_address>', methods=['GET'])
def get_running_config(ip_address):
    device = Device.query.filter_by(ip_address=ip_address).first()

    # UniFi devices - pull config via API
    if device and 'unifi' in (device.device_type or ''):
        return get_unifi_config(device)

    # SSH devices
    result = ssh_service.get_running_config(ip_address)
    if result.get('success') and device:
        backup = ConfigBackup(device_id=device.id, config_type='running', config_text=result['config'])
        db.session.add(backup)
        db.session.commit()
    return jsonify(result)


@config_bp.route('/startup/<ip_address>', methods=['GET'])
def get_startup_config(ip_address):
    device = Device.query.filter_by(ip_address=ip_address).first()

    # UniFi devices - same as running (no startup concept)
    if device and 'unifi' in (device.device_type or ''):
        return get_unifi_config(device)

    # SSH devices
    result = ssh_service.get_startup_config(ip_address)
    if result.get('success') and device:
        backup = ConfigBackup(device_id=device.id, config_type='startup', config_text=result['config'])
        db.session.add(backup)
        db.session.commit()
    return jsonify(result)


@config_bp.route('/push/<ip_address>', methods=['POST'])
def push_config(ip_address):
    data = request.json
    commands = data.get('commands', [])
    if not commands:
        return jsonify({'success': False, 'error': 'No commands provided'}), 400
    if isinstance(commands, str):
        commands = [c.strip() for c in commands.split('\n') if c.strip()]
    result = ssh_service.push_config(ip_address, commands)
    return jsonify(result)


@config_bp.route('/backup/<ip_address>', methods=['POST'])
def backup_config(ip_address):
    device = Device.query.filter_by(ip_address=ip_address).first()

    if device and 'unifi' in (device.device_type or ''):
        # Backup UniFi config
        result = get_unifi_config_data(device)
        if result:
            backup = ConfigBackup(device_id=device.id, config_type='backup', config_text=result)
            db.session.add(backup)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Config backed up', 'backup_id': backup.id})
        return jsonify({'success': False, 'error': 'Failed to pull UniFi config'})

    result = ssh_service.get_running_config(ip_address)
    if result.get('success') and device:
        backup = ConfigBackup(device_id=device.id, config_type='backup', config_text=result['config'])
        db.session.add(backup)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Config backed up', 'backup_id': backup.id})
    return jsonify(result)


@config_bp.route('/command/<ip_address>', methods=['POST'])
def send_command(ip_address):
    data = request.json
    command = data.get('command', '')
    if not command:
        return jsonify({'success': False, 'error': 'No command provided'}), 400
    result = ssh_service.send_command(ip_address, command)
    return jsonify(result)


@config_bp.route('/history/<ip_address>', methods=['GET'])
def get_config_history(ip_address):
    device = Device.query.filter_by(ip_address=ip_address).first()
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404
    backups = ConfigBackup.query.filter_by(device_id=device.id).order_by(
        ConfigBackup.created_at.desc()).limit(20).all()
    return jsonify([b.to_dict() for b in backups])


def get_unifi_config(device):
    """Pull configuration from a UniFi device via the controller API and return as JSON response."""
    config_text = get_unifi_config_data(device)
    if config_text:
        # Save backup
        backup = ConfigBackup(device_id=device.id, config_type='running', config_text=config_text)
        db.session.add(backup)
        db.session.commit()
        return jsonify({'success': True, 'config': config_text})
    return jsonify({'success': False, 'error': 'Failed to pull UniFi configuration'}), 400


def get_unifi_config_data(device):
    """Pull configuration from a UniFi device and return as text string."""
    try:
        from app.services.unifi_service import UniFiService

        controller_url = device.unifi_controller_url or os.getenv('UNIFI_CONTROLLER_URL', '')
        username = os.getenv('UNIFI_USERNAME', '')
        password = os.getenv('UNIFI_PASSWORD', '')

        if not controller_url or not username:
            logger.error("UniFi credentials not configured in .env")
            return None

        unifi = UniFiService(
            controller_url=controller_url,
            username=username,
            password=password,
            site=device.unifi_site or 'default',
            verify_ssl=False,
        )

        # Get all devices and find ours
        devices = unifi.get_devices()
        target = None
        for d in devices:
            if d.get('ip') == device.ip_address or d.get('mac', '').lower() == (device.mac_address or '').lower():
                target = d
                break

        if not target:
            unifi.logout()
            logger.error(f"Device {device.ip_address} not found on UniFi controller")
            return None

        # Get networks for context
        networks = unifi.get_networks()
        unifi.logout()

        # Build network ID to name/vlan map
        net_map = {}
        for n in networks:
            net_map[n.get('_id', '')] = {
                'name': n.get('name', 'Unknown'),
                'vlan': n.get('vlan', ''),
                'subnet': n.get('ip_subnet', ''),
            }

        # Build readable config output
        lines = []
        lines.append("!" * 60)
        lines.append("! UniFi Device Configuration")
        lines.append("! Retrieved via UniFi Controller API")
        lines.append(f"! Controller: {controller_url}")
        lines.append("!" * 60)
        lines.append("")
        lines.append(f"hostname {target.get('name', 'Unknown')}")
        lines.append(f"!")
        lines.append(f"! Hardware")
        lines.append(f"model {target.get('model', 'Unknown')}")
        lines.append(f"mac-address {target.get('mac', 'Unknown')}")
        lines.append(f"ip-address {target.get('ip', 'Unknown')}")
        lines.append(f"firmware {target.get('version', 'Unknown')}")

        uptime = target.get('uptime', 0)
        if uptime:
            days = uptime // 86400
            hours = (uptime % 86400) // 3600
            mins = (uptime % 3600) // 60
            lines.append(f"uptime {days} days, {hours} hours, {mins} minutes")

        lines.append("")
        lines.append("!" * 60)
        lines.append("! Networks / VLANs")
        lines.append("!" * 60)

        for net in networks:
            vlan = net.get('vlan', '')
            name = net.get('name', '')
            subnet = net.get('ip_subnet', '')
            purpose = net.get('purpose', '')
            dhcp = net.get('dhcpd_enabled', False)
            lines.append("")
            lines.append(f"network {name}")
            if vlan:
                lines.append(f"  vlan-id {vlan}")
            if subnet:
                lines.append(f"  ip-subnet {subnet}")
            if purpose:
                lines.append(f"  purpose {purpose}")
            lines.append(f"  dhcp-server {'enabled' if dhcp else 'disabled'}")
            if dhcp and net.get('dhcpd_start'):
                lines.append(f"  dhcp-range {net.get('dhcpd_start')} to {net.get('dhcpd_stop', '')}")
            if net.get('dhcpd_dns1'):
                lines.append(f"  dns-server {net.get('dhcpd_dns1', '')} {net.get('dhcpd_dns2', '')}")

        # Port configuration
        port_table = target.get('port_table', [])
        if port_table:
            lines.append("")
            lines.append("!" * 60)
            lines.append("! Port Configuration")
            lines.append("!" * 60)

            for port in port_table:
                idx = port.get('port_idx', 0)
                name = port.get('name', f'Port {idx}')
                speed = port.get('speed', 0)
                is_up = port.get('up', False)
                poe = port.get('poe_enable', False)
                native_net = port.get('native_networkconf_id', '')
                net_info = net_map.get(native_net, {})
                net_name = net_info.get('name', 'Default')
                net_vlan = net_info.get('vlan', '')

                lines.append("")
                lines.append(f"interface port {idx}")
                if name and name != f'Port {idx}':
                    lines.append(f"  description {name}")
                lines.append(f"  state {'up' if is_up else 'down'}")
                if speed:
                    lines.append(f"  speed {speed} Mbps")
                else:
                    lines.append(f"  speed auto")
                lines.append(f"  native-network {net_name}" + (f" (VLAN {net_vlan})" if net_vlan else ""))
                if poe:
                    poe_power = port.get('poe_power', '0')
                    lines.append(f"  poe enabled")
                    lines.append(f"  poe-power {poe_power}W")
                # Traffic stats
                rx = port.get('rx_bytes', 0)
                tx = port.get('tx_bytes', 0)
                if rx or tx:
                    rx_mb = round(rx / 1048576, 1)
                    tx_mb = round(tx / 1048576, 1)
                    lines.append(f"  rx-bytes {rx_mb} MB")
                    lines.append(f"  tx-bytes {tx_mb} MB")

        # Port overrides
        port_overrides = target.get('port_overrides', [])
        if port_overrides:
            lines.append("")
            lines.append("!" * 60)
            lines.append("! Port Overrides (Custom Settings)")
            lines.append("!" * 60)

            for override in port_overrides:
                idx = override.get('port_idx', 0)
                lines.append("")
                lines.append(f"port-override {idx}")
                if override.get('name'):
                    lines.append(f"  name {override['name']}")
                if override.get('native_networkconf_id'):
                    net_info = net_map.get(override['native_networkconf_id'], {})
                    lines.append(f"  native-network {net_info.get('name', override['native_networkconf_id'])}")
                if override.get('poe_mode'):
                    lines.append(f"  poe-mode {override['poe_mode']}")
                if override.get('autoneg') is not None:
                    lines.append(f"  autoneg {'enabled' if override['autoneg'] else 'disabled'}")

        lines.append("")
        lines.append("!" * 60)
        lines.append("! End of Configuration")
        lines.append("!" * 60)

        return '\n'.join(lines)

    except Exception as e:
        logger.error(f"UniFi config pull error: {e}")
        return None





@config_bp.route('/diff/<ip_address>', methods=['GET'])
def diff_running_startup(ip_address):
    """Compare running config vs startup config for a device."""
    try:
        device = Device.query.filter_by(ip_address=ip_address).first()
        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        if 'unifi' in (device.device_type or ''):
            return jsonify({'success': False, 'error': 'Diff not supported for UniFi devices (no startup config concept)'}), 400

        # Pull both configs live
        running = ssh_service.get_running_config(ip_address)
        if not running.get('success'):
            return jsonify({'success': False, 'error': f"Failed to pull running config: {running.get('error', 'Unknown')}"}), 400

        startup = ssh_service.get_startup_config(ip_address)
        if not startup.get('success'):
            return jsonify({'success': False, 'error': f"Failed to pull startup config: {startup.get('error', 'Unknown')}"}), 400

        # Store full configs for side-by-side display
        running_full = running['config']
        startup_full = startup['config']

        # Generate unified diff
        running_lines = running_full.splitlines(keepends=True)
        startup_lines = startup_full.splitlines(keepends=True)

        diff = list(difflib.unified_diff(
            startup_lines,
            running_lines,
            fromfile='startup-config',
            tofile='running-config',
            lineterm=''
        ))

        has_changes = len(diff) > 0

        return jsonify({
            'success': True,
            'has_changes': has_changes,
            'summary': 'Changes detected between running and startup' if has_changes else 'Configs are identical',
            'unified_diff': ''.join(diff) if diff else 'No differences found.',
            'startup_config': startup_full,
            'running_config': running_full,
            'stats': {
                'additions': sum(1 for line in diff if line.startswith('+') and not line.startswith('+++')),
                'deletions': sum(1 for line in diff if line.startswith('-') and not line.startswith('---')),
                'running_lines': len(running_lines),
                'startup_lines': len(startup_lines),
            }
        })

    except Exception as e:
        logger.error(f"Diff error for {ip_address}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500



@config_bp.route('/diff/backups', methods=['POST'])
def diff_backups():
    """Compare two specific config backups by ID."""
    try:
        data = request.json
        backup_id_a = data.get('backup_a')
        backup_id_b = data.get('backup_b')

        if not backup_id_a or not backup_id_b:
            return jsonify({'success': False, 'error': 'Two backup IDs required (backup_a, backup_b)'}), 400

        backup_a = ConfigBackup.query.get(backup_id_a)
        backup_b = ConfigBackup.query.get(backup_id_b)

        if not backup_a:
            return jsonify({'success': False, 'error': f'Backup {backup_id_a} not found'}), 404
        if not backup_b:
            return jsonify({'success': False, 'error': f'Backup {backup_id_b} not found'}), 404

        # Generate unified diff
        lines_a = backup_a.config_text.splitlines(keepends=True)
        lines_b = backup_b.config_text.splitlines(keepends=True)

        from_label = f"{backup_a.config_type} ({backup_a.created_at.strftime('%Y-%m-%d %H:%M')})"
        to_label = f"{backup_b.config_type} ({backup_b.created_at.strftime('%Y-%m-%d %H:%M')})"

        diff = list(difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile=from_label,
            tofile=to_label,
            lineterm=''
        ))

        has_changes = len(diff) > 0

        return jsonify({
            'success': True,
            'has_changes': has_changes,
            'summary': f"Comparing {from_label} → {to_label}",
            'unified_diff': ''.join(diff) if diff else 'No differences found.',
            'stats': {
                'additions': sum(1 for line in diff if line.startswith('+') and not line.startswith('+++')),
                'deletions': sum(1 for line in diff if line.startswith('-') and not line.startswith('---')),
                'lines_a': len(lines_a),
                'lines_b': len(lines_b),
            },
            'backup_a': backup_a.to_dict(),
            'backup_b': backup_b.to_dict(),
        })

    except Exception as e:
        logger.error(f"Backup diff error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

### CONFIG DIFF: Current vs Backup
@config_bp.route('/diff/current-vs-backup/<ip_address>/<int:backup_id>', methods=['GET'])
def diff_current_vs_backup(ip_address, backup_id):
    """Compare current running config against a specific backup."""
    try:
        device = Device.query.filter_by(ip_address=ip_address).first()
        if not device:
            return jsonify({'success': False, 'error': 'Device not found'}), 404

        backup = ConfigBackup.query.get(backup_id)
        if not backup:
            return jsonify({'success': False, 'error': 'Backup not found'}), 404

        # Pull current config
        if 'unifi' in (device.device_type or ''):
            current_text = get_unifi_config_data(device)
            if not current_text:
                return jsonify({'success': False, 'error': 'Failed to pull current UniFi config'}), 400
        else:
            result = ssh_service.get_running_config(ip_address)
            if not result.get('success'):
                return jsonify({'success': False, 'error': f"Failed to pull running config: {result.get('error', 'Unknown')}"}), 400
            current_text = result['config']

        # Generate diff
        backup_lines = backup.config_text.splitlines(keepends=True)
        current_lines = current_text.splitlines(keepends=True)

        from_label = f"Backup ({backup.config_type} - {backup.created_at.strftime('%Y-%m-%d %H:%M')})"
        to_label = "Current Running Config"

        diff = list(difflib.unified_diff(
            backup_lines,
            current_lines,
            fromfile=from_label,
            tofile=to_label,
            lineterm=''
        ))

        has_changes = len(diff) > 0

        return jsonify({
            'success': True,
            'has_changes': has_changes,
            'summary': f"{'Changes detected' if has_changes else 'No changes'} since {backup.created_at.strftime('%Y-%m-%d %H:%M')}",
            'unified_diff': ''.join(diff) if diff else 'No differences found.',
            'stats': {
                'additions': sum(1 for line in diff if line.startswith('+') and not line.startswith('+++')),
                'deletions': sum(1 for line in diff if line.startswith('-') and not line.startswith('---')),
                'backup_lines': len(backup_lines),
                'current_lines': len(current_lines),
            }
        })

    except Exception as e:
        logger.error(f"Current vs backup diff error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

