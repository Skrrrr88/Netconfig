import os
import time
import logging
from pysnmp.hlapi import (
    getCmd, nextCmd, bulkCmd,
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity
)

logger = logging.getLogger(__name__)


class SNMPService:
    """SNMP polling service for network devices."""

    # Standard OIDs
    OID_SYS_NAME = '1.3.6.1.2.1.1.5.0'
    OID_SYS_DESCR = '1.3.6.1.2.1.1.1.0'
    OID_SYS_LOCATION = '1.3.6.1.2.1.1.6.0'
    OID_SYS_CONTACT = '1.3.6.1.2.1.1.4.0'
    OID_SYS_UPTIME = '1.3.6.1.2.1.1.3.0'
    OID_IF_DESCR = '1.3.6.1.2.1.2.2.1.2'
    OID_IF_OPER_STATUS = '1.3.6.1.2.1.2.2.1.8'
    OID_IF_IN_OCTETS = '1.3.6.1.2.1.31.1.1.1.6'
    OID_IF_OUT_OCTETS = '1.3.6.1.2.1.31.1.1.1.10'
    OID_IF_IN_ERRORS = '1.3.6.1.2.1.2.2.1.14'
    OID_IF_OUT_ERRORS = '1.3.6.1.2.1.2.2.1.20'
    OID_IF_SPEED = '1.3.6.1.2.1.31.1.1.1.15'
    # Cisco-specific
    OID_CPU_5MIN = '1.3.6.1.4.1.9.9.109.1.1.1.1.6.19'
    OID_MEM_USED = '1.3.6.1.4.1.9.9.48.1.1.1.5.1'
    OID_MEM_FREE = '1.3.6.1.4.1.9.9.48.1.1.1.6.1'
    OID_TEMP = '1.3.6.1.4.1.9.9.91.1.1.1.1.4'
    OID_SERIAL = '1.3.6.1.2.1.47.1.1.1.1.11.1'
    OID_FIRMWARE = '1.3.6.1.2.1.47.1.1.1.1.10.1'
    OID_PSU_STATUS = '1.3.6.1.4.1.9.9.117.1.1.2.1.2'
    OID_FAN_STATUS = '1.3.6.1.4.1.9.9.117.1.4.1.1.1'

    def __init__(self):
        self.community = os.getenv('SNMP_COMMUNITY', 'public')
        self.version = os.getenv('SNMP_VERSION', '2c')
        self.timeout = int(os.getenv('SNMP_TIMEOUT', '5'))
        self.retries = int(os.getenv('SNMP_RETRIES', '2'))
        self.port = int(os.getenv('SNMP_PORT', '161'))
        self._prev_counters = {}

    def _get(self, ip, oid):
        """SNMP GET a single OID."""
        import subprocess
        try:
            cmd = ['snmpget', '-v2c', '-c', self.community, '-OQv', ip, oid]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if proc.returncode != 0:
                return None
            val = proc.stdout.strip().strip('"')
            if 'No Such' in val or 'noSuch' in val:
                return None
            return val
        except Exception as e:
            logger.debug(f"SNMP GET {oid} from {ip} failed: {e}")
            return None

    def _walk(self, ip, oid):
        """SNMP WALK using subprocess snmpwalk."""
        import subprocess
        results = {}
        try:
            cmd = ['snmpwalk', '-v2c', '-c', self.community, '-OQn', ip, oid]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                return results
            for line in proc.stdout.strip().split('\n'):
                if ' = ' not in line:
                    continue
                oid_part, val = line.split(' = ', 1)
                oid_part = oid_part.strip()
                val = val.strip()
                if 'No Such' in val or 'noSuch' in val:
                    continue
                idx = oid_part.split('.')[-1]
                results[idx] = val.strip('"').strip('"').strip('"')
        except Exception as e:
            logger.debug(f"SNMP WALK {oid} from {ip} failed: {e}")
        return results

    def get_system_info(self, ip):
        """Get system information via SNMP."""
        return {
            'sysName': self._get(ip, self.OID_SYS_NAME) or '',
            'sysDescr': self._get(ip, self.OID_SYS_DESCR) or '',
            'sysLocation': self._get(ip, self.OID_SYS_LOCATION) or '',
            'sysContact': self._get(ip, self.OID_SYS_CONTACT) or '',
            'sysUptime': self._format_uptime(self._get(ip, self.OID_SYS_UPTIME)),
            'serial': self._get(ip, self.OID_SERIAL) or '',
            'firmware': self._get(ip, self.OID_FIRMWARE) or '',
        }
    def _format_uptime(self, raw):
        """Convert SNMP timeticks (DD:HH:MM:SS.th) to human readable, omitting zero leaders."""
        if not raw:
            return ""
        try:
            # Separate the main time segments from the centiseconds
            clean = raw.split('.')
            parts = clean[0].split(':')
            
            if len(parts) == 4:
                # Safely parse strings directly to integers
                days = int(parts[0])
                hours = int(parts[1])
                minutes = int(parts[2])
                seconds = int(parts[3])
                
                output = []
                if days > 0:
                    output.append(f"{days}d")
                if hours > 0 or days > 0: 
                    output.append(f"{hours}h")
                if minutes > 0 or hours > 0 or days > 0: 
                    output.append(f"{minutes}m")
                
                # Always show seconds, even if 0
                output.append(f"{seconds}s")
                
                return " ".join(output)
                
            return raw
        except Exception:
            return raw

    def get_cpu(self, ip):
        """Get CPU usage (Cisco 5-min average)."""
        val = self._get(ip, self.OID_CPU_5MIN)
        if val and val.isdigit():
            return int(val)
        return None

    def get_memory(self, ip):
        """Get memory usage percentage."""
        used = self._get(ip, self.OID_MEM_USED)
        free = self._get(ip, self.OID_MEM_FREE)
        if used and free and used.isdigit() and free.isdigit():
            u = int(used)
            f = int(free)
            total = u + f
            if total > 0:
                return round((u / total) * 100, 1)
        return None

    def get_temperature(self, ip):
        """Get temperature readings in Fahrenheit."""
        temps = self._walk(ip, self.OID_TEMP)
        readings = []
        for idx, val in temps.items():
            try:
                readings.append(int(val))
            except (ValueError, TypeError):
                pass
        if readings:
            celsius = max(readings) / 10
            fahrenheit = (celsius * 9 / 5) + 32
            return round(fahrenheit, 1)
        return None
    def get_environment(self, ip):
        """Get PSU and fan status."""
        psu_data = self._walk(ip, self.OID_PSU_STATUS)
        fan_data = self._walk(ip, self.OID_FAN_STATUS)

        psus = []
        for idx, val in psu_data.items():
            status = 'OK' if val in ('2', '9') else 'FAIL'
            psus.append({'id': idx, 'status': status})

        fans = []
        for idx, val in fan_data.items():
            status = 'OK' if val in ('1', '2') else 'FAIL'
            fans.append({'id': idx, 'status': status})

        return {'psus': psus, 'fans': fans}

    def get_interfaces(self, ip):
        """Get interface traffic and status."""
        names = self._walk(ip, self.OID_IF_DESCR)
        statuses = self._walk(ip, self.OID_IF_OPER_STATUS)
        in_octets = self._walk(ip, self.OID_IF_IN_OCTETS)
        out_octets = self._walk(ip, self.OID_IF_OUT_OCTETS)
        in_errors = self._walk(ip, self.OID_IF_IN_ERRORS)
        out_errors = self._walk(ip, self.OID_IF_OUT_ERRORS)
        speeds = self._walk(ip, self.OID_IF_SPEED)

        now = time.time()
        prev = self._prev_counters.get(ip, {})
        prev_time = prev.get('_time', now)
        interval = now - prev_time
        if interval < 1:
            interval = 1

        interfaces = []
        for idx, name in names.items():
            # Skip non-physical interfaces
            if any(x in name.lower() for x in ['vlan', 'loopback', 'null', 'stack', 'cpu']):
                continue

            status_val = statuses.get(idx, '2')
            status = 'up' if status_val == '1' else 'down'

            # Calculate rates
            in_oct = int(in_octets.get(idx, 0) or 0)
            out_oct = int(out_octets.get(idx, 0) or 0)
            prev_in = prev.get(f'in_{idx}', in_oct)
            prev_out = prev.get(f'out_{idx}', out_oct)

            in_rate = max(0, (in_oct - prev_in) * 8 / interval / 1_000_000)
            out_rate = max(0, (out_oct - prev_out) * 8 / interval / 1_000_000)

            in_err = int(in_errors.get(idx, 0) or 0)
            out_err = int(out_errors.get(idx, 0) or 0)
            speed = int(speeds.get(idx, 0) or 0)

            interfaces.append({
                'interface': name,
                'status': status,
                'in_mbps': round(in_rate, 2),
                'out_mbps': round(out_rate, 2),
                'errors': in_err + out_err,
                'speed': speed,
            })

        # Store counters for next poll
        new_prev = {'_time': now}
        for idx in names:
            new_prev[f'in_{idx}'] = int(in_octets.get(idx, 0) or 0)
            new_prev[f'out_{idx}'] = int(out_octets.get(idx, 0) or 0)
        self._prev_counters[ip] = new_prev

        return interfaces

    def poll_device(self, ip):
        """Full SNMP poll of a device."""
        result = {
            'success': True,
            'ip': ip,
            'timestamp': time.time(),
            'system': self.get_system_info(ip),
            'cpu': self.get_cpu(ip),
            'memory': self.get_memory(ip),
            'temperature': self.get_temperature(ip),
            'environment': self.get_environment(ip),
            'interfaces': self.get_interfaces(ip),
        }
        return result


snmp_service = SNMPService()
