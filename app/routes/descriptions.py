from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Device
from app.services.ssh_service import ssh_service
import os
import logging

desc_bp = Blueprint('descriptions', __name__)
logger = logging.getLogger(__name__)


@desc_bp.route('/<ip_address>', methods=['GET'])
def get_descriptions(ip_address):
    device = Device.query.filter_by(ip_address=ip_address).first()
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404

    if 'unifi' in (device.device_type or ''):
        return jsonify({'success': True, 'descriptions': {}})

    result = ssh_service.send_command(ip_address, 'show interfaces description')
    if not result.get('success'):
        return jsonify(result), 400

    desc_map = {}
    for line in result.get('output', '').split(''):
        parts = line.split()
        if parts and ('Gi' in parts or 'Te' in parts or 'Fa' in parts):
            intf = parts
            raw = line[len(intf):].strip()
            chunks = raw.split()
            if len(chunks) >= 2:
                desc_map[intf] = ' '.join(chunks[2:]) if len(chunks) > 2 else ''
            else:
                desc_map[intf] = ''
    return jsonify({'success': True, 'descriptions': desc_map})


@desc_bp.route('/<ip_address>', methods=['POST'])
def set_description(ip_address):
    data = request.json
    interface = data.get('interface', '')
    description = data.get('description', '')

    if not interface:
        return jsonify({'success': False, 'error': 'No interface specified'}), 400

    device = Device.query.filter_by(ip_address=ip_address).first()
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404

    commands = ['interface ' + interface]
    if description:
        commands.append('description ' + description)
    else:
        commands.append('no description')
    result = ssh_service.push_config(ip_address, commands)
    return jsonify(result)
