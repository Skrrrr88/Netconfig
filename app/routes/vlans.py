from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import GlobalVlan, PortVlanAssignment, Device
from app.services.vlan_service import vlan_service
from app.services.ssh_service import ssh_service
import logging

vlans_bp = Blueprint('vlans', __name__)
logger = logging.getLogger(__name__)


@vlans_bp.route('/', methods=['GET'])
def list_vlans():
    vlans = GlobalVlan.query.order_by(GlobalVlan.vlan_id).all()
    return jsonify([v.to_dict() for v in vlans])


@vlans_bp.route('/', methods=['POST'])
def create_vlan():
    data = request.json
    vlan_id = data.get('vlan_id')
    name = data.get('name')
    if not vlan_id or not name:
        return jsonify({'success': False, 'error': 'VLAN ID and name are required'}), 400
    if GlobalVlan.query.filter_by(vlan_id=vlan_id).first():
        return jsonify({'success': False, 'error': f'VLAN {vlan_id} already exists'}), 409

    vlan = GlobalVlan(
        vlan_id=vlan_id,
        name=name,
        subnet=data.get('subnet', ''),
        gateway=data.get('gateway', ''),
        description=data.get('description', ''),
    )
    db.session.add(vlan)
    db.session.commit()

    deploy_to = data.get('deploy_to', 'all')
    results = vlan_service.deploy_vlan_to_all(vlan, deploy_to)
    return jsonify({'success': True, 'vlan': vlan.to_dict(), 'deployment': results})


@vlans_bp.route('/<int:vlan_id>', methods=['DELETE'])
def delete_vlan(vlan_id):
    vlan = GlobalVlan.query.filter_by(vlan_id=vlan_id).first()
    if not vlan:
        return jsonify({'success': False, 'error': 'VLAN not found'}), 404
    db.session.delete(vlan)
    db.session.commit()
    logger.info(f"VLAN {vlan_id} ({vlan.name}) deleted")
    return jsonify({'success': True, 'message': f'VLAN {vlan_id} ({vlan.name}) deleted'})


@vlans_bp.route('/<int:vlan_id>/deploy', methods=['POST'])
def deploy_vlan(vlan_id):
    vlan = GlobalVlan.query.filter_by(vlan_id=vlan_id).first()
    if not vlan:
        return jsonify({'success': False, 'error': 'VLAN not found'}), 404
    data = request.json or {}
    targets = data.get('targets', 'all')
    results = vlan_service.deploy_vlan_to_all(vlan, targets)
    return jsonify({'success': True, 'results': results})


@vlans_bp.route('/ports/<ip_address>', methods=['GET'])
def get_port_assignments(ip_address):
    device = Device.query.filter_by(ip_address=ip_address).first()
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404

    # Pull live data from device
    device_type = device.device_type or 'cisco_ios'
    if 'mikrotik' in device_type:
        result = ssh_service.send_command(ip_address, '/interface print')
    elif 'juniper' in device_type:
        result = ssh_service.send_command(ip_address, 'show interfaces terse')
    elif 'hp' in device_type:
        result = ssh_service.send_command(ip_address, 'show interfaces brief')
    else:
        result = ssh_service.send_command(ip_address, 'show interfaces status')

    if not result.get('success'):
        # Fall back to database
        assignments = PortVlanAssignment.query.filter_by(device_id=device.id).all()
        return jsonify([a.to_dict() for a in assignments])

    # Parse the output into assignments
    assignments = parse_port_assignments(result.get('output', ''), device_type)
    return jsonify(assignments)


def parse_port_assignments(output, device_type):
    """Parse show interfaces status into port assignment list."""
    assignments = []
    if not output:
        return assignments

    lines = output.strip().split('\n')

    if 'cisco' in device_type or 'arista' in device_type:
        for line in lines:
            # Skip headers and separator lines
            if line.startswith('Port') or line.startswith('-') or not line.strip():
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            port = parts[0]
            # Skip non-physical ports
            if any(x in port.lower() for x in ['vlan', 'loop', 'null', 'cpu', 'app']):
                continue

            # Cisco "show interfaces status" format:
            # Port  Name  Status  Vlan  Duplex  Speed  Type
            status = 'up' if 'connected' in line.lower() else 'down'
            vlan = ''
            mode = 'access'
            description = ''
            speed = ''

            # Try to find VLAN - look for numbers that could be VLAN IDs
            if 'trunk' in line.lower():
                mode = 'trunk'
                vlan = 'trunk'
            else:
                # Find the vlan column value
                for p in parts[1:]:
                    if p.isdigit() and 1 <= int(p) <= 4094:
                        vlan = p
                        break

            # Description is usually the second field
            if len(parts) > 1 and not parts[1].isdigit() and parts[1] not in ['connected', 'notconnect', 'disabled', 'trunk']:
                description = parts[1]

            assignments.append({
                'port': port,
                'vlan': vlan,
                'mode': mode,
                'description': description,
                'status': status,
            })

    return assignments


@vlans_bp.route('/ports/<ip_address>', methods=['POST'])
def assign_vlan_to_port(ip_address):
    data = request.json
    port = data.get('port')
    vlan_id = data.get('vlan_id')
    mode = data.get('mode', 'access')
    if not port or not vlan_id:
        return jsonify({'success': False, 'error': 'Port and VLAN ID required'}), 400

    device = Device.query.filter_by(ip_address=ip_address).first()
    if not device:
        return jsonify({'success': False, 'error': 'Device not found'}), 404

    result = ssh_service.assign_vlan_to_port(ip_address, port, vlan_id, mode)
    if result.get('success'):
        assignment = PortVlanAssignment.query.filter_by(device_id=device.id, port_name=port).first()
        if not assignment:
            assignment = PortVlanAssignment(device_id=device.id, port_name=port)
            db.session.add(assignment)
        assignment.vlan_id = vlan_id
        assignment.mode = mode
        db.session.commit()
    return jsonify(result)


@vlans_bp.route('/deployment-status', methods=['GET'])
def deployment_status():
    status = vlan_service.get_deployment_status()
    return jsonify(status)
