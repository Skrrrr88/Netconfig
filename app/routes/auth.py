from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models import User
import logging

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)


@auth_bp.route('/login', methods=['GET'])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('login.html')


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password are required'}), 400

    user = User.query.filter_by(username=username).first()

    if not user or not user.check_password(password):
        logger.warning(f"Failed login attempt for username: {username}")
        return jsonify({'success': False, 'error': 'Invalid username or password'}), 401

    if not user.is_active:
        return jsonify({'success': False, 'error': 'Account is disabled'}), 403

    login_user(user, remember=data.get('remember', False))
    user.update_last_login()
    db.session.commit()

    logger.info(f"User '{username}' logged in successfully")
    return jsonify({
        'success': True,
        'message': 'Login successful',
        'user': user.to_dict()
    })


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    First user registration is open (creates admin).
    Subsequent registrations require an existing admin to be logged in.
    """
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')
    display_name = data.get('display_name', '').strip()

    # Validation
    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password are required'}), 400

    if len(username) < 3:
        return jsonify({'success': False, 'error': 'Username must be at least 3 characters'}), 400

    if len(password) < 8:
        return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400

    if password != confirm_password:
        return jsonify({'success': False, 'error': 'Passwords do not match'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'error': 'Username already exists'}), 409

    # Check if this is the first user (auto-admin) or requires auth
    user_count = User.query.count()
    if user_count > 0:
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Registration requires admin approval'}), 403
        if current_user.role != 'admin':
            return jsonify({'success': False, 'error': 'Only admins can create new users'}), 403

    # Create user
    role = 'admin' if user_count == 0 else data.get('role', 'operator')
    if role not in ('admin', 'operator', 'viewer'):
        role = 'operator'

    user = User(
        username=username,
        display_name=display_name or username,
        role=role,
    )
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    logger.info(f"New user registered: '{username}' (role: {role})")

    # Auto-login if first user
    if user_count == 0:
        login_user(user)
        return jsonify({
            'success': True,
            'message': 'Admin account created and logged in',
            'user': user.to_dict()
        }), 201

    return jsonify({
        'success': True,
        'message': f'User "{username}" created successfully',
        'user': user.to_dict()
    }), 201


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    username = current_user.username
    logout_user()
    logger.info(f"User '{username}' logged out")
    return jsonify({'success': True, 'message': 'Logged out successfully'})


@auth_bp.route('/me', methods=['GET'])
@login_required
def get_current_user():
    return jsonify({'success': True, 'user': current_user.to_dict()})


@auth_bp.route('/users', methods=['GET'])
@login_required
def list_users():
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    users = User.query.order_by(User.created_at).all()
    return jsonify([u.to_dict() for u in users])


@auth_bp.route('/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    if current_user.id == user_id:
        return jsonify({'success': False, 'error': 'Cannot delete your own account'}), 400

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    logger.info(f"User '{user.username}' deleted by '{current_user.username}'")
    return jsonify({'success': True, 'message': f'User "{user.username}" deleted'})


@auth_bp.route('/users/<int:user_id>/role', methods=['PUT'])
@login_required
def update_user_role(user_id):
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Admin access required'}), 403

    data = request.json
    new_role = data.get('role', '')
    if new_role not in ('admin', 'operator', 'viewer'):
        return jsonify({'success': False, 'error': 'Invalid role'}), 400

    user = User.query.get_or_404(user_id)
    user.role = new_role
    db.session.commit()
    logger.info(f"User '{user.username}' role changed to '{new_role}' by '{current_user.username}'")
    return jsonify({'success': True, 'message': f'Role updated to {new_role}', 'user': user.to_dict()})

