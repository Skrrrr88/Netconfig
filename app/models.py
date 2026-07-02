from datetime import datetime
from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(100))
    role = db.Column(db.String(20), default='operator')  # admin, operator, viewer
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='scrypt')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def update_last_login(self):
        self.last_login = datetime.now(timezone.utc)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'display_name': self.display_name,
            'role': self.role,
            'is_active': self.is_active,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Device(db.Model):
    __tablename__ = 'devices'
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(255), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False, unique=True)
    device_type = db.Column(db.String(50), nullable=False)
    platform = db.Column(db.String(100))
    ssh_port = db.Column(db.Integer, default=22)
    username = db.Column(db.String(100))
    password_encrypted = db.Column(db.LargeBinary)
    enable_secret_encrypted = db.Column(db.LargeBinary)
    unifi_controller_url = db.Column(db.String(255))
    unifi_site = db.Column(db.String(50), default='default')
    mac_address = db.Column(db.String(17))
    is_online = db.Column(db.Boolean, default=False)
    manually_disconnected = db.Column(db.Boolean, default=False)
    last_seen = db.Column(db.DateTime)
    uptime = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    configs = db.relationship('ConfigBackup', backref='device', lazy=True, cascade='all, delete-orphan')
    port_assignments = db.relationship('PortVlanAssignment', backref='device', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'hostname': self.hostname,
            'ip_address': self.ip_address,
            'device_type': self.device_type,
            'platform': self.platform,
            'ssh_port': self.ssh_port,
            'is_online': self.is_online,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'uptime': self.uptime,
            'mac_address': self.mac_address,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class GlobalVlan(db.Model):
    __tablename__ = 'global_vlans'
    id = db.Column(db.Integer, primary_key=True)
    vlan_id = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    subnet = db.Column(db.String(18))
    gateway = db.Column(db.String(45))
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'vlan_id': self.vlan_id,
            'name': self.name,
            'subnet': self.subnet,
            'gateway': self.gateway,
            'description': self.description,
            'is_active': self.is_active,
        }


class PortVlanAssignment(db.Model):
    __tablename__ = 'port_vlan_assignments'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    port_name = db.Column(db.String(50), nullable=False)
    vlan_id = db.Column(db.Integer)
    mode = db.Column(db.String(10), default='access')
    description = db.Column(db.String(255))
    is_up = db.Column(db.Boolean, default=True)
    speed = db.Column(db.String(20))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'device_id': self.device_id,
            'port_name': self.port_name,
            'vlan_id': self.vlan_id,
            'mode': self.mode,
            'description': self.description,
            'is_up': self.is_up,
            'speed': self.speed,
        }


class ConfigBackup(db.Model):
    __tablename__ = 'config_backups'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    config_type = db.Column(db.String(20))
    config_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(100), default='system')

    def to_dict(self):
        return {
            'id': self.id,
            'device_id': self.device_id,
            'config_type': self.config_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by': self.created_by,
            'size': len(self.config_text) if self.config_text else 0,
        }


class DeviceLink(db.Model):
    __tablename__ = 'device_links'
    id = db.Column(db.Integer, primary_key=True)
    source_device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    dest_device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    source_interface = db.Column(db.String(50))
    dest_interface = db.Column(db.String(50))
    link_speed = db.Column(db.String(20))
    link_type = db.Column(db.String(20))
    is_up = db.Column(db.Boolean, default=True)
    source_device = db.relationship('Device', foreign_keys=[source_device_id])
    dest_device = db.relationship('Device', foreign_keys=[dest_device_id])

    def to_dict(self):
        return {
            'id': self.id,
            'source': self.source_device.to_dict() if self.source_device else None,
            'dest': self.dest_device.to_dict() if self.dest_device else None,
            'source_interface': self.source_interface,
            'dest_interface': self.dest_interface,
            'link_speed': self.link_speed,
            'link_type': self.link_type,
            'is_up': self.is_up,
        }
