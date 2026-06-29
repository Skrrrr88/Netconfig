import os
import logging
from flask import Flask, render_template, jsonify
from app.extensions import db, cors
from app.config import config_map

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'production')

    app = Flask(__name__)
    app.config.from_object(config_map.get(config_name, config_map['production']))

    db.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})

    from app.routes.devices import devices_bp
    from app.routes.config_manager import config_bp
    from app.routes.vlans import vlans_bp
    from app.routes.diagram import diagram_bp
    from app.routes.status import status_bp
    from app.routes.descriptions import desc_bp
    from app.routes.snmp import snmp_bp

    app.register_blueprint(devices_bp, url_prefix='/api/devices')
    app.register_blueprint(config_bp, url_prefix='/api/config')
    app.register_blueprint(vlans_bp, url_prefix='/api/vlans')
    app.register_blueprint(status_bp, url_prefix='/api/devices/status')
    app.register_blueprint(desc_bp, url_prefix='/api/devices/descriptions')
    app.register_blueprint(snmp_bp, url_prefix='/api/snmp')
    app.register_blueprint(diagram_bp, url_prefix='/api/diagram')

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/health')
    def health():
        return jsonify({'status': 'healthy', 'version': '1.0.0', 'service': 'netconfig'})

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f'Server error: {e}')
        return jsonify({'error': 'Internal server error'}), 500

    with app.app_context():
        db.create_all()

    logger.info(f'NetConfig started in {config_name} mode')
    return app


def make_celery(app=None):
    from celery import Celery
    if app is None:
        app = create_app()
    celery = Celery(
        app.import_name,
        broker=app.config['REDIS_URL'],
        backend=app.config['REDIS_URL']
    )
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
