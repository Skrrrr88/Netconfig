import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:////app/instance/netconfig.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    FERNET_KEY = os.getenv('FERNET_KEY', '')
    SSH_TIMEOUT = int(os.getenv('SSH_TIMEOUT', '30'))
    SSH_GLOBAL_DELAY_FACTOR = int(os.getenv('SSH_GLOBAL_DELAY_FACTOR', '1'))
    UNIFI_CONTROLLER_URL = os.getenv('UNIFI_CONTROLLER_URL', '')
    UNIFI_USERNAME = os.getenv('UNIFI_USERNAME', '')
    UNIFI_PASSWORD = os.getenv('UNIFI_PASSWORD', '')
    UNIFI_SITE = os.getenv('UNIFI_SITE', 'default')
    UNIFI_VERIFY_SSL = os.getenv('UNIFI_VERIFY_SSL', 'false').lower() == 'true'


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_ECHO = False


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = True


config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}
