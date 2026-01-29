from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from datetime import datetime, timezone, timedelta
import os
from config import Config
from views.requirement_views import requirement_bp
from views.project_views import project_bp  # 导入项目管理蓝图
from flask_login import login_user, logout_user, login_required, current_user

# 导入模型和表单
from models import db, init_db, Requirement, User
from forms import RequirementForm
from flask_login import LoginManager

def create_app(config=None):
    app = Flask(__name__)
    
    # 加载配置
    app.config.from_object(Config)
    
    # 应用自定义配置
    if config:
        app.config.update(config)
    
    # 确保上传目录存在
    upload_folder = app.config['UPLOAD_FOLDER']
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
        print(f'创建上传目录: {upload_folder}')
    
    # 初始化CSRF保护
    csrf = CSRFProtect(app)
    
    # 添加自定义过滤器
    @app.template_filter('reject_page')
    def reject_page_filter(args_dict):
        """从URL参数中移除page参数"""
        if isinstance(args_dict, dict):
            filtered = {k: v for k, v in args_dict.items() if k != 'page'}
            return filtered
        return {}
    
    # 添加全局模板函数
    @app.template_global()
    def now():
        """返回当前时间（+8时区），用于模板中的时间比较"""
        beijing_tz = timezone(timedelta(hours=8))
        return datetime.now(beijing_tz)
    
    # 初始化数据库和创建默认用户
    init_db(app)
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    from views.auth_views import auth_bp
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    app.register_blueprint(requirement_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(project_bp)  # 注册项目管理蓝图
    
    return app

app = create_app()

@app.route('/')
# @login_required
def index():
    """首页 - 重定向到Requirements List页面"""
    return redirect(url_for('requirement.index'))


@app.route('/delete/<int:id>')
def delete(id):
    """删除需求"""
    requirement = Requirement.query.get_or_404(id)
    db.session.delete(requirement)
    db.session.commit()
    flash('需求删除成功！', 'success')
    return redirect(url_for('index'))


if __name__ == '__main__':    
    app.run(debug=True,host='0.0.0.0',port=5001)
