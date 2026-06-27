import os
import threading
import logging
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

logger = logging.getLogger(__name__)


class SSHService:
    DEVICE_TYPE_MAP = {
        'cisco_ios': 'cisco_ios',
        'cisco_nxos': 'cisco_nxos',
        'cisco_xe': 'cisco_xe',
        'arista_eos': 'arista_eos',
        'juniper_junos': 'juniper_junos',
        'hp_procurve': 'hp_procurve',
        'mikrotik_routeros': 'mikrotik_routeros',
        'unifi_switch': 'linux',
        'unifi_gateway': 'linux',
    }

    def __init__(self):
        self.connections = {}
        
        self._lock = threading.Lock()

    def connect(self, device_config):
        try:
            netmiko_device = {
                'device_type': self.DEVICE_TYPE_MAP.get(device_config['device_type'], 'autodetect'),
                'host': device_config['ip_address'],
                'username': device_config['username'],
                'password': device_config['password'],
                'port': device_config.get('port', 22),
                'timeout': int(os.getenv('SSH_TIMEOUT', 30)),
                'global_delay_factor': int(os.getenv('SSH_GLOBAL_DELAY_FACTOR', 1)),
            }
            if device_config.get('secret'):
                netmiko_device['secret'] = device_config['secret']

            connection = ConnectHandler(**netmiko_device)
            with self._lock:
                self.connections[device_config['ip_address']] = connection
                

            prompt = connection.find_prompt()
            logger.info(f"Connected to {device_config['ip_address']} ({prompt})")
            return {
                'success': True,
                'message': f"Connected to {device_config.get('hostname', device_config['ip_address'])}",
                'prompt': prompt,
            }
        except NetmikoTimeoutException:
            return {'success': False, 'error': f"Timeout connecting to {device_config['ip_address']}"}
        except NetmikoAuthenticationException:
            return {'success': False, 'error': f"Authentication failed for {device_config['ip_address']}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_connection(self, ip_address):
        with self._lock:
            conn = self.connections.get(ip_address)

        # Check if connection is still alive
        if conn:
            try:
                conn.find_prompt()
            except Exception:
                logger.warning(f"Connection to {ip_address} lost, removing stale session")
                with self._lock:
                    self.connections.pop(ip_address, None)
                conn = None

        # Auto-reconnect using stored credentials
        if not conn:
            conn = self._auto_reconnect(ip_address)

        return conn

    def _auto_reconnect(self, ip_address):
        """Try to reconnect using stored credentials from the database."""
        try:
            from app.models import Device
            from cryptography.fernet import Fernet

            # Skip if manually disconnected
            device = Device.query.filter_by(ip_address=ip_address).first()
            if device and device.manually_disconnected:
                logger.info(f"Device {ip_address} is manually disconnected, skipping")
                return None
            if not device or not device.password_encrypted:
                logger.warning(f"No stored credentials for {ip_address}")
                return None

            # Decrypt password
            key = os.environ.get('FERNET_KEY', '')
            if key:
                try:
                    password = Fernet(key.encode()).decrypt(device.password_encrypted).decode()
                except Exception:
                    if isinstance(device.password_encrypted, bytes):
                        password = device.password_encrypted.decode()
                    else:
                        password = str(device.password_encrypted)
            else:
                if isinstance(device.password_encrypted, bytes):
                    password = device.password_encrypted.decode()
                else:
                    password = str(device.password_encrypted)

            logger.info(f"Auto-reconnecting to {ip_address}...")
            result = self.connect({
                'hostname': device.hostname,
                'ip_address': device.ip_address,
                'device_type': device.device_type or 'cisco_ios',
                'username': device.username or '',
                'password': password,
                'port': device.ssh_port or 22,
                'secret': '',
            })
            if result.get('success'):
                logger.info(f"Auto-reconnected to {ip_address}")
                return self.connections.get(ip_address)
            else:
                logger.warning(f"Auto-reconnect failed: {result.get('error')}")
                return None
        except Exception as e:
            logger.warning(f"Auto-reconnect error for {ip_address}: {e}")
            return None

    def disconnect(self, ip_address):
        with self._lock:
            conn = self.connections.pop(ip_address, None)
            
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass
        logger.info(f"Manually disconnected from {ip_address}")

    def send_command(self, ip_address, command):
        conn = self.get_connection(ip_address)
        if not conn:
            return {'success': False, 'error': 'No active connection and auto-reconnect failed.'}
        try:
            output = conn.send_command(command, read_timeout=30)
            return {'success': True, 'output': output}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_running_config(self, ip_address):
        conn = self.get_connection(ip_address)
        if not conn:
            return {'success': False, 'error': 'No active connection and auto-reconnect failed.'}
        try:
            config = conn.send_command('show running-config', read_timeout=60)
            return {'success': True, 'config': config}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_startup_config(self, ip_address):
        conn = self.get_connection(ip_address)
        if not conn:
            return {'success': False, 'error': 'No active connection and auto-reconnect failed.'}
        try:
            config = conn.send_command('show startup-config', read_timeout=60)
            return {'success': True, 'config': config}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def push_config(self, ip_address, commands):
        conn = self.get_connection(ip_address)
        if not conn:
            return {'success': False, 'error': 'No active connection and auto-reconnect failed.'}
        try:
            if not conn.check_enable_mode():
                conn.enable()
            output = conn.send_config_set(commands, read_timeout=30)
            save_output = conn.save_config()
            output += f"\n{save_output}"
            logger.info(f"Config pushed to {ip_address}: {len(commands)} commands")
            return {'success': True, 'output': output}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def create_vlan(self, ip_address, vlan_id, vlan_name):
        return self.push_config(ip_address, [f'vlan {vlan_id}', f'name {vlan_name}'])

    def assign_vlan_to_port(self, ip_address, interface, vlan_id, mode='access'):
        if mode == 'access':
            commands = [
                f'interface {interface}',
                'switchport mode access',
                f'switchport access vlan {vlan_id}',
                'spanning-tree portfast',
                'no shutdown',
            ]
        elif mode == 'trunk':
            commands = [
                f'interface {interface}',
                'switchport mode trunk',
                f'switchport trunk allowed vlan add {vlan_id}',
                'no shutdown',
            ]
        else:
            return {'success': False, 'error': f'Invalid mode: {mode}'}
        return self.push_config(ip_address, commands)


ssh_service = SSHService()
