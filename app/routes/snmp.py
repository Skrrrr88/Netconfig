from flask import Blueprint, request, jsonify
from app.models import Device
from app.services.snmp_service import snmp_service
import logging

snmp_bp = Blueprint('snmp', __name__)
logger = logging.getLogger(__name__)

# In-memory alert history
_alerts = []
MAX_ALERTS = 100


def check_thresholds(ip, hostname, poll_data):
    """Generate alerts based on threshold checks."""
    global _alerts
    import time
    ts = time.strftime('%H:%M:%S')

    cpu = poll_data.get('cpu')
    if cpu is not None:
        if cpu > 80:
            _alerts.insert(0, {'time': ts, 'severity': 'critical', 'source': hostname, 'message': f'CPU at {cpu}% (>80%)'})
        elif cpu > 60:
            _alerts.insert(0, {'time': ts, 'severity': 'warning', 'source': hostname, 'message': f'CPU at {cpu}% (>60%)'})

    mem = poll_data.get('memory')
    if mem is not None:
        if mem > 85:
            _alerts.insert(0, {'time': ts, 'severity': 'critical', 'source': hostname, 'message': f'Memory at {mem}% (>85%)'})
        elif mem > 70:
            _alerts.insert(0, {'time': ts, 'severity': 'warning', 'source': hostname, 'message': f'Memory at {mem}% (>70%)'})

    temp = poll_data.get('temperature')
    if temp is not None:
        if temp > 149:
            _alerts.insert(0, {'time': ts, 'severity': 'critical', 'source': hostname, 'message': f'Temperature {temp}°C (>149°F)'})
        elif temp > 131:
            _alerts.insert(0, {'time': ts, 'severity': 'warning', 'source': hostname, 'message': f'Temperature {temp}°C (>131°F)'})

    for iface in poll_data.get('interfaces', []):
        if iface['errors'] > 10:
            _alerts.insert(0, {'time': ts, 'severity': 'warning', 'source': f"{hostname}/{iface['interface']}", 'message': f"Errors: {iface['errors']}"})

    env = poll_data.get('environment', {})
    for psu in env.get('psus', []):
        if psu['status'] != 'OK':
            _alerts.insert(0, {'time': ts, 'severity': 'critical', 'source': hostname, 'message': f"PSU {psu['id']} FAILED"})
    for fan in env.get('fans', []):
        if fan['status'] != 'OK':
            _alerts.insert(0, {'time': ts, 'severity': 'warning', 'source': hostname, 'message': f"Fan {fan['id']} FAILED"})

    _alerts = _alerts[:MAX_ALERTS]


@snmp_bp.route('/poll/<ip_address>')
def poll_device(ip_address):
    """Poll a single device via SNMP."""
    device = Device.query.filter_by(ip_address=ip_address).first()
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404

    result = snmp_service.poll_device(ip_address)
    check_thresholds(ip_address, device.hostname, result)
    return jsonify(result)


@snmp_bp.route('/system/<ip_address>')
def get_system_info(ip_address):
    """Get system info only."""
    info = snmp_service.get_system_info(ip_address)
    return jsonify({'success': True, 'system': info})


@snmp_bp.route('/interfaces/<ip_address>')
def get_interfaces(ip_address):
    """Get interface traffic data."""
    interfaces = snmp_service.get_interfaces(ip_address)
    return jsonify({'success': True, 'interfaces': interfaces})


@snmp_bp.route('/alerts')
def get_alerts():
    """Get recent SNMP alerts."""
    return jsonify({'success': True, 'alerts': _alerts})


@snmp_bp.route('/alerts/clear', methods=['POST'])
def clear_alerts():
    """Clear all alerts."""
    global _alerts
    _alerts = []
    return jsonify({'success': True, 'message': 'Alerts cleared'})

