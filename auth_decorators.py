"""
权限控制装饰器
提供基于角色的权限检查功能
"""

from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user


def admin_required(f):
    """
    管理员权限装饰器
    只有admin角色的用户才能访问被装饰的视图函数
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('请先登录', 'warning')
            return redirect(url_for('auth.login'))
        
        if current_user.role != 'admin':
            flash('您没有权限访问此页面', 'danger')
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


def manager_required(f):
    """
    经理权限装饰器
    只有admin或manager角色的用户才能访问被装饰的视图函数
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('请先登录', 'warning')
            return redirect(url_for('auth.login'))
        
        if current_user.role not in ['admin', 'manager']:
            flash('您没有权限访问此页面，需要经理级别权限', 'danger')
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    """
    角色权限装饰器
    支持多个角色的权限检查
    
    Args:
        *roles: 允许访问的角色列表
    
    Usage:
        @role_required('admin', 'manager')
        def some_view():
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('请先登录', 'warning')
                return redirect(url_for('auth.login'))
            
            if current_user.role not in roles:
                flash('您没有权限访问此页面', 'danger')
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def check_user_permission(target_user_id=None):
    """
    检查用户是否有权限操作指定用户
    管理员可以操作所有用户，普通用户只能操作自己
    
    Args:
        target_user_id: 目标用户ID，如果为None则不检查
    
    Returns:
        bool: 是否有权限
    """
    if not current_user.is_authenticated:
        return False
    
    # 管理员有所有权限
    if current_user.role == 'admin':
        return True
    
    # 普通用户只能操作自己
    if target_user_id is not None:
        return current_user.id == target_user_id
    
    return True