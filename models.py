from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone, timedelta
from enum import Enum
from werkzeug.security import generate_password_hash, check_password_hash
import json

db = SQLAlchemy()

# 定义北京时区
BEIJING_TZ = timezone(timedelta(hours=8))

def beijing_now():
    """返回当前北京时间"""
    return datetime.now(BEIJING_TZ)

def init_db(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()
        
        # 创建默认管理员用户
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                email='admin@reqman.com',
                full_name='系统管理员',
                role='admin',
                department='IT部门'
            )
            admin_user.set_password('123456')
            db.session.add(admin_user)
            db.session.commit()
            print(f'默认管理员用户已创建: {admin_user.username}')
        else:
            print(f'管理员用户已存在: {admin_user.username}')
        
# 关联表
requirement_dependencies = db.Table('requirement_dependencies',
    db.Column('parent_id', db.Integer, db.ForeignKey('requirement.id'), primary_key=True),
    db.Column('child_id', db.Integer, db.ForeignKey('requirement.id'), primary_key=True)
)

requirement_tags = db.Table('requirement_tags',
    db.Column('requirement_id', db.Integer, db.ForeignKey('requirement.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

class RequirementType(Enum):
    """需求类型枚举"""
    FUNCTIONAL = '功能需求'               # 功能需求
    NON_FUNCTIONAL = '非功能需求'         # 非功能需求
    BUSINESS = '业务需求'                # 业务需求
    USER = '用户需求'                    # 用户需求
    SYSTEM = '系统需求'                  # 系统需求
    INTERFACE = '接口需求'               # 接口需求
    PERFORMANCE = '性能需求'             # 性能需求
    SECURITY = '安全需求'                # 安全需求

class RequirementStatus(Enum):
    """需求状态枚举"""
    DRAFT = '草稿'                     # 草稿
    SUBMITTED = '已提交'               # 已提交
    REVIEWING = '评审中'               # 评审中
    APPROVED = '已批准'                # 已批准
    IN_DEVELOPMENT = 'In progress'          # In progress
    TESTING = '测试中'                 # 测试中
    COMPLETED = 'Completed'               # Completed
    REJECTED = '已拒绝'                # 已拒绝
    CANCELLED = 'Cancelled'               # Cancelled
    ON_HOLD = 'On Hold'                   # On Hold

class Priority(Enum):
    """优先级枚举"""
    CRITICAL = '关键'  # 关键
    HIGH = '高'         # 高
    MEDIUM = '中'     # 中
    LOW = '低'          # 低

class Requirement(db.Model):
    """增强版需求模型"""
    __tablename__ = 'requirement'
    
    # 基本信息
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)  # 需求编号
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    
    # 分类信息
    type = db.Column(db.String(20), default=RequirementType.FUNCTIONAL.value)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    module_id = db.Column(db.Integer, db.ForeignKey('module.id'))
    
    # 状态和优先级
    status = db.Column(db.String(20), default=RequirementStatus.DRAFT.value)
    priority = db.Column(db.String(20), default=Priority.MEDIUM.value)
    
    # 人员信息
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # 项目和版本
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    version = db.Column(db.String(20))  # 目标版本
    
    # 详细描述
    background = db.Column(db.Text)  # 背景说明
    objective = db.Column(db.Text)   # 目标
    scope = db.Column(db.Text)       # 范围
    acceptance_criteria = db.Column(db.Text)  # 验收标准
    assumptions = db.Column(db.Text)  # 假设条件
    constraints = db.Column(db.Text)  # 约束条件
    risks = db.Column(db.Text)        # 风险说明
    
    # 估算信息
    estimated_hours = db.Column(db.Float)  # 预估工时
    actual_hours = db.Column(db.Float)     # 实际工时
    story_points = db.Column(db.Integer)   # 故事点
    business_value = db.Column(db.Integer) # 业务价值 (1-100)
    
    # 时间信息
    due_date = db.Column(db.Date)
    start_date = db.Column(db.Date)
    completion_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=beijing_now)
    updated_at = db.Column(db.DateTime, default=beijing_now, onupdate=beijing_now)
    
    # 附加信息
    source = db.Column(db.String(100))  # 需求来源
    is_template = db.Column(db.Boolean, default=False)  # 是否为模板
    
    # 关系
    category = db.relationship('Category', backref='requirements')
    module = db.relationship('Module', backref='requirements')
    project = db.relationship('Project', backref='requirements')
    creator = db.relationship('User', foreign_keys=[creator_id], backref='created_requirements')
    assignee = db.relationship('User', foreign_keys=[assignee_id], backref='assigned_requirements')
    reviewer = db.relationship('User', foreign_keys=[reviewer_id], backref='reviewed_requirements')
    
    # 多对多关系
    dependencies = db.relationship(
        'Requirement',
        secondary=requirement_dependencies,
        primaryjoin=(requirement_dependencies.c.parent_id == id),
        secondaryjoin=(requirement_dependencies.c.child_id == id),
        backref=db.backref('dependents', lazy='dynamic'),
        lazy='dynamic'
    )
    
    tags = db.relationship('Tag', secondary=requirement_tags, backref='requirements')
    attachments = db.relationship('Attachment', backref='requirement', cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='requirement', cascade='all, delete-orphan')
    history = db.relationship('RequirementHistory', backref='requirement', cascade='all, delete-orphan', lazy='dynamic')
    test_cases = db.relationship('TestCase', backref='requirement', cascade='all, delete-orphan')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'code': self.code,
            'title': self.title,
            'description': self.description,
            'type': self.type,
            'status': self.status,
            'priority': self.priority,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'due_date': self.due_date.isoformat() if self.due_date else None
        }
    
    def calculate_completeness(self):
        """计算需求完整度"""
        fields = [
            self.title, self.description, self.type, self.priority,
            self.objective, self.scope, self.acceptance_criteria
        ]
        filled = sum(1 for f in fields if f)
        return (filled / len(fields)) * 100
    
    def get_priority_score(self):
        """获取优先级分数"""
        scores = {
            Priority.CRITICAL.value: 4,
            Priority.HIGH.value: 3,
            Priority.MEDIUM.value: 2,
            Priority.LOW.value: 1
        }
        return scores.get(self.priority, 0)
    
    def get_priority_badge_class(self):
        """获取优先级徽章CSS类"""
        badge_classes = {
            Priority.CRITICAL.value: 'badge-danger',
            Priority.HIGH.value: 'badge-warning',
            Priority.MEDIUM.value: 'badge-info',
            Priority.LOW.value: 'badge-secondary'
        }
        return badge_classes.get(self.priority, 'badge-secondary')
    
    def get_status_badge_class(self):
        """获取状态徽章CSS类"""
        badge_classes = {
            RequirementStatus.DRAFT.value: 'badge-secondary',
            RequirementStatus.SUBMITTED.value: 'badge-primary',
            RequirementStatus.REVIEWING.value: 'badge-warning',
            RequirementStatus.APPROVED.value: 'badge-info',
            RequirementStatus.IN_DEVELOPMENT.value: 'badge-warning',
            RequirementStatus.TESTING.value: 'badge-primary',
            RequirementStatus.COMPLETED.value: 'badge-success',
            RequirementStatus.REJECTED.value: 'badge-danger',
            RequirementStatus.CANCELLED.value: 'badge-dark',
            RequirementStatus.ON_HOLD.value: 'badge-secondary'
        }
        return badge_classes.get(self.status, 'badge-secondary')
    
    def get_priority_bg_class(self):
        """获取优先级徽章Bootstrap 5格式CSS类"""
        bg_classes = {
            Priority.CRITICAL.value: 'danger',
            Priority.HIGH.value: 'warning',
            Priority.MEDIUM.value: 'info',
            Priority.LOW.value: 'secondary'
        }
        return bg_classes.get(self.priority, 'secondary')
    
    def get_status_bg_class(self):
        """获取状态徽章Bootstrap 5格式CSS类"""
        bg_classes = {
            RequirementStatus.DRAFT.value: 'secondary',
            RequirementStatus.SUBMITTED.value: 'primary',
            RequirementStatus.REVIEWING.value: 'warning',
            RequirementStatus.APPROVED.value: 'info',
            RequirementStatus.IN_DEVELOPMENT.value: 'warning',
            RequirementStatus.TESTING.value: 'primary',
            RequirementStatus.COMPLETED.value: 'success',
            RequirementStatus.REJECTED.value: 'danger',
            RequirementStatus.CANCELLED.value: 'dark',
            RequirementStatus.ON_HOLD.value: 'secondary'
        }
        return bg_classes.get(self.status, 'secondary')

class Category(db.Model):
    """需求分类"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    parent_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    icon = db.Column(db.String(50))
    color = db.Column(db.String(20))
    
    parent = db.relationship('Category', remote_side=[id], backref='children')

class Module(db.Model):
    """系统模块"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    code = db.Column(db.String(50), unique=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    owner = db.relationship('User', backref='owned_modules')

class Project(db.Model):
    """项目"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='active')
    manager_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    manager = db.relationship('User', backref='managed_projects')

class User(UserMixin, db.Model):
    """用户"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(200))
    role = db.Column(db.String(50), default='viewer')  # admin, manager, developer, tester, viewer
    department = db.Column(db.String(100))
    avatar = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=beijing_now)
    last_login = db.Column(db.DateTime)  # 最后登录时间
    
    def set_password(self, password):
        """设置密码"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """检查密码"""
        return check_password_hash(self.password_hash, password)
    
    def get_id(self):
        """返回用户ID，Flask-Login所需"""
        return str(self.id)
    
    @property
    def is_authenticated(self):
        """返回用户是否已认证"""
        return True
    
    @property
    def is_anonymous(self):
        """返回用户是否为匿名用户"""
        return False
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    # Note: is_active已经是数据库字段，UserMixin会自动使用它

class Tag(db.Model):
    """标签"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(20))

class Attachment(db.Model):
    """附件"""
    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'))
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500))
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    uploaded_at = db.Column(db.DateTime, default=beijing_now)
    
    uploader = db.relationship('User')

class Comment(db.Model):
    """评论"""
    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=beijing_now)
    updated_at = db.Column(db.DateTime, default=beijing_now, onupdate=beijing_now)
    
    user = db.relationship('User', backref='comments')

class RequirementHistory(db.Model):
    """需求变更历史"""
    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(50))  # create, update, delete, status_change
    field_name = db.Column(db.String(100))
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=beijing_now)
    
    user = db.relationship('User')

class TestCase(db.Model):
    """测试用例"""
    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id'))
    title = db.Column(db.String(200), nullable=False)
    preconditions = db.Column(db.Text)
    test_steps = db.Column(db.Text)  # JSON格式存储步骤
    expected_result = db.Column(db.Text)
    priority = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending')  # pending, passed, failed
    tester_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    test_date = db.Column(db.DateTime)
    
    tester = db.relationship('User')

class RequirementTemplate(db.Model):
    """需求模板"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(20))
    template_content = db.Column(db.Text)  # JSON格式存储模板内容
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=beijing_now)
    
    creator = db.relationship('User')

class Baseline(db.Model):
    """基线版本"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    version = db.Column(db.String(20), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    description = db.Column(db.Text)
    requirements_snapshot = db.Column(db.Text)  # JSON格式存储需求快照
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=beijing_now)
    
    project = db.relationship('Project')
    creator = db.relationship('User')
