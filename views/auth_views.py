# auth.py
# This file will contain authentication related routes and logic.

from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
import werkzeug.security
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont
import io
import random
import string

# 定义北京时区
BEIJING_TZ = timezone(timedelta(hours=8))

# 延迟导入避免循环导入问题
def get_user_model():
    from models import User
    return User

def get_db_and_forms():
    from models import db
    from forms import LoginForm, RegistrationForm, PasswordResetRequestForm, PasswordResetForm
    return db, LoginForm, RegistrationForm, PasswordResetRequestForm, PasswordResetForm

auth_bp = Blueprint('auth', __name__, template_folder='templates')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('project.index'))
    
    db, LoginForm, _, _, _ = get_db_and_forms()
    User = get_user_model()
    
    form = LoginForm()
    if form.validate_on_submit():
        # 验证验证码
        if current_app.config.get('ENABLE_CAPTCHA', True):
            user_captcha = form.captcha.data.lower()
            session_captcha = session.get('captcha_text', '').lower()
            if user_captcha != session_captcha:
                flash('验证码错误，请重试。', 'danger')
                return redirect(url_for('auth.login'))
        
        user = User.query.filter_by(username=form.username.data).first()
        
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash('此账户已被禁用，请联系管理员。', 'danger')
                return redirect(url_for('auth.login'))
            
            login_user(user, remember=form.remember_me.data)
            
            # 更新最后登录时间 - 使用北京时间
            user.last_login = datetime.now(BEIJING_TZ)
            db.session.commit()
            
            # 获取请求中的 next 参数
            next_page = request.args.get('next')
            if not next_page or urlparse(next_page).netloc != '':
                next_page = url_for('project.index')
                
            flash(f'欢迎回来，{user.full_name}！', 'success')
            return redirect(next_page)
        else:
            flash('用户名或密码错误，请重试。', 'danger')
    
    return render_template('user/login.html', form=form, enable_captcha=current_app.config.get('ENABLE_CAPTCHA', True))


@auth_bp.route('/generate_captcha')
def generate_captcha():
    # 检查验证码功能是否启用
    if not current_app.config.get('ENABLE_CAPTCHA', True):
        return '', 404
    
    # 生成验证码图片
    width, height = 120, 40
    image = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    # 生成随机字符串
    chars = string.ascii_letters + string.digits
    captcha_text = ''.join(random.choice(chars) for _ in range(4))
    session['captcha_text'] = captcha_text
    
    # 绘制验证码
    font = ImageFont.load_default()
    # 使用更大的字体大小
    try:
        # 尝试加载系统字体，大小为24
        font = ImageFont.truetype('arial.ttf', 24)
    except IOError:
        # 如果系统字体不可用，使用默认字体并增大尺寸
        font = ImageFont.load_default(size=24)
    for i, char in enumerate(captcha_text):
        draw.text((30*i + 10, 5), char, font=font, fill=(0, 0, 0))
    
    # 添加干扰线
    for _ in range(5):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=(0, 0, 0), width=1)
    
    # 添加干扰点
    for _ in range(20):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=(0, 0, 0))
    
    # 保存到内存
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    buffer.seek(0)
    
    from flask import make_response
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'image/png'
    return response


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('您已成功登出。', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('project.index'))
    
    db, _, RegistrationForm, _, _ = get_db_and_forms()
    User = get_user_model()
    
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            # 使用User类创建新用户
            new_user = User(
                username=form.username.data,
                email=form.email.data,
                full_name=form.full_name.data,
                role='user',  # 默认角色
                is_active=True  # 默认激活状态
            )
            new_user.set_password(form.password.data)
            
            db.session.add(new_user)
            db.session.commit()
            
            flash('注册成功，请登录！', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('注册失败，请重试。', 'danger')
            current_app.logger.error(f'用户注册失败: {str(e)}')
    
    return render_template('user/register.html', form=form)



@auth_bp.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('project.index'))
    
    _, _, _, PasswordResetRequestForm, _ = get_db_and_forms()
    form = PasswordResetRequestForm()
    if form.validate_on_submit():
        # 这里需要添加邮件发送逻辑
        flash('密码重置邮件已发送，请检查您的邮箱。', 'info')
        return redirect(url_for('auth.login'))
    
    return render_template('user/reset_password_request.html', form=form)

@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('project.index'))
    
    _, _, _, _, PasswordResetForm = get_db_and_forms()
    form = PasswordResetForm()
    # 这里需要添加token验证逻辑
    if form.validate_on_submit():
        # 这里需要添加密码更新逻辑
        flash('密码已成功重置，请使用新密码登录。', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('user/reset_password.html', form=form)


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """用户个人资料页面"""
    User = get_user_model()
    db, _, _, _, _ = get_db_and_forms()
    
    if request.method == 'POST':
        try:
            # 更新用户信息
            current_user.full_name = request.form.get('full_name')
            current_user.email = request.form.get('email')
            current_user.department = request.form.get('department')
            
            # 如果提供了新密码，则更新密码
            new_password = request.form.get('new_password')
            if new_password:
                current_user.set_password(new_password)
            
            db.session.commit()
            flash('个人信息已更新', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash('更新个人信息失败，请重试', 'danger')
            current_app.logger.error(f'更新个人信息失败: {str(e)}')
    
    return render_template('user/profile.html', user=current_user)


# 用户管理相关路由（管理员功能）
@auth_bp.route('/admin/users')
def admin_users():
    """管理员用户列表页面"""
    from auth_decorators import admin_required
    
    @admin_required
    def _admin_users():
        User = get_user_model()
        
        # 获取分页参数
        page = request.args.get('page', 1, type=int)
        per_page = 10  # 每页显示10个用户
        
        # 获取搜索参数
        search = request.args.get('search', '')
        role_filter = request.args.get('role', 'all')
        status_filter = request.args.get('status', 'all')
        
        # 构建查询
        query = User.query
        
        # 应用搜索过滤
        if search:
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    User.username.contains(search),
                    User.full_name.contains(search),
                    User.email.contains(search)
                )
            )
        
        # 应用角色过滤
        if role_filter != 'all':
            query = query.filter(User.role == role_filter)
        
        # 应用状态过滤
        if status_filter == 'active':
            query = query.filter(User.is_active == True)
        elif status_filter == 'inactive':
            query = query.filter(User.is_active == False)
        
        # 按创建时间排序并分页
        users = query.order_by(User.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # 获取用户统计信息
        stats = {
            'total_users': User.query.count(),
            'active_users': User.query.filter(User.is_active == True).count(),
            'inactive_users': User.query.filter(User.is_active == False).count(),
            'admin_users': User.query.filter(User.role == 'admin').count()
        }
        
        return render_template('user/admin_users.html', 
                             users=users, 
                             search=search,
                             role_filter=role_filter,
                             status_filter=status_filter,
                             stats=stats)
    
    return _admin_users()


@auth_bp.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
def admin_edit_user(user_id):
    """管理员编辑用户页面"""
    from auth_decorators import admin_required
    
    @admin_required
    def _admin_edit_user():
        User = get_user_model()
        db, _, _, _, _ = get_db_and_forms()
        
        user = User.query.get_or_404(user_id)
        
        if request.method == 'POST':
            try:
                # 更新用户信息
                user.username = request.form.get('username')
                user.email = request.form.get('email')
                user.full_name = request.form.get('full_name')
                user.role = request.form.get('role')
                user.department = request.form.get('department')
                user.is_active = 'is_active' in request.form
                
                # 如果提供了新密码，则更新密码
                new_password = request.form.get('new_password')
                if new_password:
                    user.set_password(new_password)
                
                db.session.commit()
                flash(f'用户 {user.username} 信息已更新', 'success')
                return redirect(url_for('auth.admin_users'))
                
            except Exception as e:
                db.session.rollback()
                flash('更新用户信息失败，请重试', 'danger')
                current_app.logger.error(f'更新用户失败: {str(e)}')
        
        return render_template('user/admin_edit_user.html', user=user)
    
    return _admin_edit_user()


@auth_bp.route('/admin/users/<int:user_id>/toggle_status', methods=['POST'])
def admin_toggle_user_status(user_id):
    """管理员切换用户状态（启用/禁用）"""
    from auth_decorators import admin_required
    
    @admin_required
    def _admin_toggle_user_status():
        User = get_user_model()
        db, _, _, _, _ = get_db_and_forms()
        
        user = User.query.get_or_404(user_id)
        
        # 不能禁用自己
        if user.id == current_user.id:
            flash('不能禁用自己的账户', 'warning')
            return redirect(url_for('auth.admin_users'))
        
        try:
            user.is_active = not user.is_active
            db.session.commit()
            
            status = '启用' if user.is_active else '禁用'
            flash(f'用户 {user.username} 已{status}', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash('操作失败，请重试', 'danger')
            current_app.logger.error(f'切换用户状态失败: {str(e)}')
        
        return redirect(url_for('auth.admin_users'))
    
    return _admin_toggle_user_status()


@auth_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
def admin_delete_user(user_id):
    """管理员删除用户"""
    from auth_decorators import admin_required
    
    @admin_required
    def _admin_delete_user():
        User = get_user_model()
        db, _, _, _, _ = get_db_and_forms()
        
        user = User.query.get_or_404(user_id)
        
        # 不能删除自己
        if user.id == current_user.id:
            flash('不能删除自己的账户', 'warning')
            return redirect(url_for('auth.admin_users'))
        
        # 不能删除其他管理员
        if user.role == 'admin':
            flash('不能删除管理员账户', 'warning')
            return redirect(url_for('auth.admin_users'))
        
        try:
            username = user.username
            db.session.delete(user)
            db.session.commit()
            flash(f'用户 {username} 已删除', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash('删除用户失败，请重试', 'danger')
            current_app.logger.error(f'删除用户失败: {str(e)}')
        
        return redirect(url_for('auth.admin_users'))
    
    return _admin_delete_user()


@auth_bp.route('/admin/users/create', methods=['GET', 'POST'])
def admin_create_user():
    """管理员创建用户页面"""
    from auth_decorators import admin_required
    
    @admin_required
    def _admin_create_user():
        User = get_user_model()
        db, _, _, _, _ = get_db_and_forms()
        from forms import AdminCreateUserForm
        
        form = AdminCreateUserForm()
        
        if form.validate_on_submit():
            try:
                # 创建新用户
                new_user = User(
                    username=form.username.data,
                    email=form.email.data,
                    full_name=form.full_name.data,
                    role=form.role.data,
                    department=form.department.data,
                    is_active=True
                )
                new_user.set_password(form.password.data)
                
                db.session.add(new_user)
                db.session.commit()
                
                flash(f'用户 {new_user.username} 创建成功', 'success')
                return redirect(url_for('auth.admin_users'))
                
            except Exception as e:
                db.session.rollback()
                flash('创建用户失败，请重试', 'danger')
                current_app.logger.error(f'创建用户失败: {str(e)}')
        
        return render_template('user/admin_create_user.html', form=form)
    
    return _admin_create_user()
