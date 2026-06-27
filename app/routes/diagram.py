from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Device, DeviceLink
import logging

diagram_bp = Blueprint('diagram', __name__)
logger = logging.getLogger(__name__)


@diagram_bp.route('/topology', methods=['GET'])
def get_topology():
    devices = Device.query.all()
    nodes = []
    for device in devices:
        node_type = 'switch'
        if 'gateway' in (device.device_type or '') or 'udm' in (device.device_type or ''):
            node_type = 'gateway'
        elif 'router' in (device.hostname or '').lower():
            node_type = 'router'
        elif 'core' in (device.hostname or '').lower():
            node_type = 'core_switch'
        elif 'ap' in (device.device_type or ''):
            node_type = 'ap'

        nodes.append({
            'id': device.ip_address,
            'hostname': device.hostname,
            'ip': device.ip_address,
            'type': node_type,
            'isOnline': device.is_online,
            'isUnifi': (device.device_type or '').startswith('unifi'),
            'platform': device.platform,
            'mac': device.mac_address,
        })
    return jsonify({'nodes': nodes})


@diagram_bp.route('/links', methods=['GET'])
def get_links():
    links = DeviceLink.query.all()
    return jsonify([l.to_dict() for l in links])


@diagram_bp.route('/links', methods=['POST'])
def create_link():
    data = request.json
    source = Device.query.filter_by(ip_address=data.get('source_ip')).first()
    dest = Device.query.filter_by(ip_address=data.get('dest_ip')).first()
    if not source or not dest:
        return jsonify({'success': False, 'error': 'Device not found'}), 404

    link = DeviceLink(
        source_device_id=source.id,
        dest_device_id=dest.id,
        source_interface=data.get('source_interface', ''),
        dest_interface=data.get('dest_interface', ''),
        link_speed=data.get('link_speed', '1G'),
        link_type=data.get('link_type', 'trunk'),
        is_up=True,
    )
    db.session.add(link)
    db.session.commit()
    return jsonify({'success': True, 'link': link.to_dict()})


@diagram_bp.route('/links/<int:link_id>', methods=['DELETE'])
def delete_link(link_id):
    link = DeviceLink.query.get_or_404(link_id)
    db.session.delete(link)
    db.session.commit()
    return jsonify({'success': True})
