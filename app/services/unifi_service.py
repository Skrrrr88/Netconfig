import requests
import urllib3
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)


class UniFiService:
    def __init__(self, controller_url, username, password, site='default', verify_ssl=False):
        self.base_url = controller_url.rstrip('/')
        self.site = site
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.is_udm = False
        self._authenticate(username, password)

    def _authenticate(self, username, password):
        """Try UDM-Pro auth first, then classic controller."""
        # Try UniFi OS (UDM-Pro, UDM-SE, Cloud Key Gen2+)
        try:
            resp = self.session.post(
                f"{self.base_url}/api/auth/login",
                json={"username": username, "password": password},
                timeout=10,
            )
            if resp.status_code == 200:
                self.is_udm = True
                logger.info("Authenticated to UniFi OS (UDM)")
                return
        except Exception as e:
            logger.debug(f"UDM auth failed: {e}")

        # Try classic controller
        try:
            resp = self.session.post(
                f"{self.base_url}/api/login",
                json={"username": username, "password": password},
                timeout=10,
            )
            if resp.status_code == 200:
                self.is_udm = False
                logger.info("Authenticated to classic UniFi controller")
                return
        except Exception as e:
            logger.debug(f"Classic auth failed: {e}")

        raise Exception("Failed to authenticate with UniFi controller")

    def _api_url(self, path):
        if self.is_udm:
            return f"{self.base_url}/proxy/network/api/s/{self.site}/{path}"
        return f"{self.base_url}/api/s/{self.site}/{path}"

    def get_devices(self):
        """Get all adopted devices with full details."""
        resp = self.session.get(self._api_url("stat/device"), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get('data', [])

    def get_device_details(self, mac):
        """Get detailed info for a specific device by MAC."""
        devices = self.get_devices()
        for d in devices:
            if d.get('mac', '').lower() == mac.lower():
                return d
        return None

    def get_device_ports(self, mac):
        """Get port table for a specific device."""
        device = self.get_device_details(mac)
        if not device:
            return []
        return device.get('port_table', [])

    def get_networks(self):
        """Get all networks/VLANs."""
        resp = self.session.get(self._api_url("rest/networkconf"), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get('data', [])

    def create_network(self, name, vlan_id, subnet=None, dhcp_enabled=False):
        """Create a new network/VLAN."""
        payload = {
            "name": name,
            "vlan": str(vlan_id),
            "vlan_enabled": True,
            "purpose": "corporate",
            "networkgroup": "LAN",
        }
        if subnet:
            payload["ip_subnet"] = subnet
        if dhcp_enabled:
            payload["dhcpd_enabled"] = True

        resp = self.session.post(self._api_url("rest/networkconf"), json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json().get('data', [])

    def delete_network(self, network_id):
        """Delete a network/VLAN by its _id."""
        resp = self.session.delete(self._api_url(f"rest/networkconf/{network_id}"), timeout=10)
        resp.raise_for_status()
        return True

    def get_port_profiles(self):
        """Get all port profiles."""
        resp = self.session.get(self._api_url("rest/portconf"), timeout=10)
        resp.raise_for_status()
        return resp.json().get('data', [])

    def assign_port_vlan(self, device_id, port_idx, network_id):
        """Assign a VLAN to a port on a UniFi switch."""
        payload = {
            "port_overrides": [{
                "port_idx": port_idx,
                "native_networkconf_id": network_id,
            }]
        }
        resp = self.session.put(
            self._api_url(f"rest/device/{device_id}"),
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_clients(self):
        """Get all connected clients."""
        resp = self.session.get(self._api_url("stat/sta"), timeout=10)
        resp.raise_for_status()
        return resp.json().get('data', [])

    def logout(self):
        try:
            if self.is_udm:
                self.session.post(f"{self.base_url}/api/auth/logout", timeout=5)
            else:
                self.session.post(f"{self.base_url}/api/logout", timeout=5)
        except Exception:
            pass
