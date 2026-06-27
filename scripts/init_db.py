import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import create_app
from app.extensions import db
from app.models import GlobalVlan

app = create_app()

DEFAULT_VLANS = [
    {'vlan_id': 1, 'name': 'Default', 'subnet': '', 'gateway': '', 'description': 'Default VLAN'},
    {'vlan_id': 10, 'name': 'Management', 'subnet': '10.10.10.0/24', 'gateway': '10.10.10.1', 'description': 'Network management'},
    {'vlan_id': 20, 'name': 'Servers', 'subnet': '10.20.20.0/24', 'gateway': '10.20.20.1', 'description': 'Server infrastructure'},
    {'vlan_id': 30, 'name': 'Workstations', 'subnet': '10.30.30.0/24', 'gateway': '10.30.30.1', 'description': 'Employee workstations'},
    {'vlan_id': 40, 'name': 'VoIP', 'subnet': '10.40.40.0/24', 'gateway': '10.40.40.1', 'description': 'Voice over IP'},
    {'vlan_id': 50, 'name': 'IoT', 'subnet': '10.50.50.0/24', 'gateway': '10.50.50.1', 'description': 'IoT devices'},
    {'vlan_id': 99, 'name': 'Guest', 'subnet': '10.99.99.0/24', 'gateway': '10.99.99.1', 'description': 'Guest network - isolated'},
]

with app.app_context():
    for vlan_data in DEFAULT_VLANS:
        existing = GlobalVlan.query.filter_by(vlan_id=vlan_data['vlan_id']).first()
        if not existing:
            vlan = GlobalVlan(**vlan_data)
            db.session.add(vlan)
            print(f"  + VLAN {vlan_data['vlan_id']} ({vlan_data['name']})")
    db.session.commit()
    print("[✓] Default VLANs seeded")
