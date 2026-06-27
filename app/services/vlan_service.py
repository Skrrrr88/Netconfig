import logging
from app.extensions import db
from app.models import Device, GlobalVlan
from app.services.ssh_service import ssh_service
from app.services.unifi_service import UniFiService

logger = logging.getLogger(__name__)


class VlanService:
    def deploy_vlan_to_device(self, device, vlan):
        if device.device_type.startswith('unifi'):
            return self._deploy_to_unifi(device, vlan)
        return self._deploy_to_ssh(device, vlan)

    def deploy_vlan_to_all(self, vlan, targets='all'):
        results = []
        devices = Device.query.filter_by(is_online=True).all()
        for device in devices:
            if targets == 'cisco_arista' and device.device_type.startswith('unifi'):
                continue
            if targets == 'unifi' and not device.device_type.startswith('unifi'):
                continue
            result = self.deploy_vlan_to_device(device, vlan)
            result['device'] = device.hostname
            results.append(result)
        return results

    def get_deployment_status(self):
        devices = Device.query.filter_by(is_online=True).all()
        global_vlans = GlobalVlan.query.filter_by(is_active=True).all()
        global_vlan_ids = {v.vlan_id for v in global_vlans}
        status = []
        for device in devices:
            device_vlans = self._get_device_vlans(device)
            missing = global_vlan_ids - device_vlans
            status.append({
                'hostname': device.hostname,
                'ip_address': device.ip_address,
                'vlans': sorted(list(device_vlans & global_vlan_ids)),
                'missing': sorted(list(missing)),
                'in_sync': len(missing) == 0,
                'last_sync': device.updated_at.strftime('%Y-%m-%d %H:%M') if device.updated_at else None,
            })
        return status

    def _deploy_to_ssh(self, device, vlan):
        try:
            result = ssh_service.create_vlan(device.ip_address, vlan.vlan_id, vlan.name)
            if result.get('success') and vlan.subnet and vlan.gateway:
                prefix = int(vlan.subnet.split('/')[1])
                mask_int = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
                mask = f"{(mask_int >> 24) & 0xFF}.{(mask_int >> 16) & 0xFF}.{(mask_int >> 8) & 0xFF}.{mask_int & 0xFF}"
                svi_commands = [
                    f'interface Vlan{vlan.vlan_id}',
                    f'description {vlan.description or vlan.name}',
                    f'ip address {vlan.gateway} {mask}',
                    'no shutdown',
                ]
                ssh_service.push_config(device.ip_address, svi_commands)
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _deploy_to_unifi(self, device, vlan):
        try:
            from flask import current_app
            unifi = UniFiService(
                controller_url=device.unifi_controller_url or current_app.config['UNIFI_CONTROLLER_URL'],
                username=current_app.config['UNIFI_USERNAME'],
                password=current_app.config['UNIFI_PASSWORD'],
                site=device.unifi_site or current_app.config['UNIFI_SITE'],
                verify_ssl=current_app.config['UNIFI_VERIFY_SSL'],
            )
            existing = unifi.get_network_id_by_vlan(vlan.vlan_id)
            if existing:
                unifi.logout()
                return {'success': True, 'message': 'VLAN already exists'}
            result = unifi.create_network(
                name=vlan.name,
                vlan_id=vlan.vlan_id,
                subnet=vlan.subnet or f'10.{vlan.vlan_id}.0.0/24',
                gateway=vlan.gateway or f'10.{vlan.vlan_id}.0.1',
            )
            unifi.logout()
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _get_device_vlans(self, device):
        if device.device_type.startswith('unifi'):
            return self._get_unifi_vlans(device)
        return self._get_ssh_vlans(device)

    def _get_ssh_vlans(self, device):
        result = ssh_service.get_vlan_brief(device.ip_address)
        if not result.get('success'):
            return set()
        vlans = set()
        for line in result.get('output', '').split('\n'):
            parts = line.split()
            if parts and parts[0].isdigit():
                vlans.add(int(parts[0]))
        return vlans

    def _get_unifi_vlans(self, device):
        try:
            from flask import current_app
            unifi = UniFiService(
                controller_url=device.unifi_controller_url or current_app.config['UNIFI_CONTROLLER_URL'],
                username=current_app.config['UNIFI_USERNAME'],
                password=current_app.config['UNIFI_PASSWORD'],
                site=device.unifi_site or current_app.config['UNIFI_SITE'],
                verify_ssl=current_app.config['UNIFI_VERIFY_SSL'],
            )
            networks = unifi.get_networks()
            unifi.logout()
            return {int(n['vlan']) for n in networks if n.get('vlan')}
        except Exception:
            return set()


vlan_service = VlanService()
