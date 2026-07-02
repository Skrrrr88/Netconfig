from functools import wraps
from flask import jsonify
from flask_login import current_user, login_required


def api_login_required(f):
    """Require authentication for API routes."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Require admin role."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role != 'admin':
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


def operator_required(f):
    """Require operator or admin role (can make changes)."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role not in ('admin', 'operator'):
            return jsonify({'success': False, 'error': 'Operator access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


def viewer_required(f):
    """Require any authenticated user (viewer, operator, or admin)."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

