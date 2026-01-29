from wtforms.fields.simple import StringField
from flask_wtf import FlaskForm
from wtforms import (StringField, TextAreaField, SelectField, DateField, 
                     FloatField, IntegerField, BooleanField, SelectMultipleField,
                     FieldList, FormField)
from wtforms.validators import DataRequired, Length, Optional, NumberRange, Email
from flask_wtf.file import FileField, FileAllowed
from models import RequirementType, RequirementStatus, Priority

from wtforms.validators import EqualTo, ValidationError
from wtforms import PasswordField, HiddenField
import re

class RequirementForm(FlaskForm):
    """增强版需求表单"""
    
    # 基本信息
    title = StringField('需求标题', validators=[
        DataRequired(message='标题不能为空'),
        Length(min=2, max=200)
    ])
    
    description = TextAreaField('需求描述', validators=[
        DataRequired(message='描述不能为空')
    ])
    
    # 分类信息
    type = SelectField('需求类型', 
        choices=[(t.value, t.value) for t in RequirementType],
        default=RequirementType.FUNCTIONAL.value
    )
    
    category_id = SelectField('需求分类', validators=[Optional()])
    module_id = SelectField('所属模块', validators=[Optional()])
    project_id = SelectField('所属项目', validators=[Optional()])
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 在初始化时动态设置选择项，避免循环导入
        self._set_dynamic_choices()
    
    # 状态和优先级
    status = SelectField('状态',
        choices=[(s.value, s.value) for s in RequirementStatus],
        default=RequirementStatus.DRAFT.value
    )
    
    priority = SelectField('优先级',
        choices=[(p.value, p.value) for p in Priority],
        default=Priority.MEDIUM.value
    )
    
    # 人员信息
    assignee_id = SelectField('负责人', validators=[Optional()])
    reviewer_id = SelectField('评审人', validators=[Optional()])
    
    # 详细描述
    background = TextAreaField('背景说明', validators=[Optional()])
    objective = TextAreaField('目标', validators=[Optional()])
    scope = TextAreaField('范围', validators=[Optional()])
    acceptance_criteria = TextAreaField('验收标准', validators=[Optional()])
    assumptions = TextAreaField('假设条件', validators=[Optional()])
    constraints = TextAreaField('约束条件', validators=[Optional()])
    risks = TextAreaField('风险说明', validators=[Optional()])
    
    # 估算信息
    estimated_hours = FloatField('预估工时(小时)', validators=[
        Optional(),
        NumberRange(min=0, max=9999)
    ])
    
    story_points = IntegerField('故事点', validators=[
        Optional(),
        NumberRange(min=0, max=100)
    ])
    
    business_value = IntegerField('业务价值(1-100)', validators=[
        Optional(),
        NumberRange(min=1, max=100)
    ])
    
    # 时间信息
    due_date = DateField('截止日期', format='%Y-%m-%d', validators=[Optional()])
    start_date = DateField('开始日期', format='%Y-%m-%d', validators=[Optional()])
    
    # 其他
    version = StringField('目标版本', validators=[Optional(), Length(max=20)])
    source = StringField('需求来源', validators=[Optional(), Length(max=100)])
    tags = SelectMultipleField('标签', validators=[Optional()])
    dependencies = SelectMultipleField('依赖需求', validators=[Optional()])
    
    # 附件 - 支持多文件上传
    attachments = FileField('上传新附件', validators=[
        FileAllowed(['pdf', 'doc', 'docx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg', 'gif', 'txt'], 
                   message='不支持的文件格式。支持格式：PDF, Word, Excel, 图片, 文本文件')
    ])
    
    def _set_dynamic_choices(self):
        """动态设置选择项，避免循环导入"""
        # 设置默认选择项
        self.category_id.choices = [('', '选择分类')]
        self.module_id.choices = [('', '选择模块')]
        self.project_id.choices = [('', '选择项目')]
        self.assignee_id.choices = [('', '选择负责人')]
        self.reviewer_id.choices = [('', '选择评审人')]
        self.tags.choices = []
        self.dependencies.choices = []
    
    def populate_choices(self):
        """填充选择项数据（在视图中调用）"""
        from models import Project, User, Category, Module, Tag, Requirement
        
        # 填充项目选择项 - 显示更多状态的项目
        project_choices = [('', '选择项目')]
        for p in Project.query.filter(
            Project.status.in_(['active', 'planning', 'completed', 'on_hold'])
        ).order_by(Project.name).all():
            project_choices.append((str(p.id), f"{p.name} ({p.status})"))
        self.project_id.choices = project_choices
        
        # 填充用户选择项
        active_users = User.query.filter_by(is_active=True).order_by(User.full_name, User.username).all()
        user_choices = [('', '选择用户')]
        for u in active_users:
            user_choices.append((str(u.id), u.full_name or u.username))
        
        self.assignee_id.choices = user_choices
        self.reviewer_id.choices = user_choices
        
        # 填充其他选择项（可根据需要扩展）
        try:
            self.category_id.choices = [('', '选择分类')] + [
                (str(c.id), c.name) for c in Category.query.order_by(Category.name).all()
            ]
        except:
            pass  # 如果Category模型不存在，忽略
            
        try:
            self.module_id.choices = [('', '选择模块')] + [
                (str(m.id), m.name) for m in Module.query.order_by(Module.name).all()
            ]
        except:
            pass  # 如果Module模型不存在，忽略
            
        try:
            self.tags.choices = [
                (str(t.id), t.name) for t in Tag.query.order_by(Tag.name).all()
            ]
        except:
            pass  # 如果Tag模型不存在，忽略
            
        # 填充依赖选择项
        try:
            self.dependencies.choices = [('', 'No dependencies')] + [
                (str(r.id), f"{r.code} - {r.title}") 
                for r in Requirement.query.filter(
                    Requirement.status.in_(['已批准', 'In progress', 'Completed'])
                ).order_by(Requirement.code).all()
            ]
        except:
            self.dependencies.choices = [('', 'No dependencies')]

class RequirementFilterForm(FlaskForm):
    """需求筛选表单"""
    keyword = StringField('keyword')
    type = SelectField('Type', choices=[('', 'All')] + [(t.value, t.value) for t in RequirementType])
    status = SelectField('Status', choices=[('', 'All')] + [(s.value, s.value) for s in RequirementStatus])
    priority = SelectField('Priority', choices=[('', 'All')] + [(p.value, p.value) for p in Priority])
    project_id = SelectField('Project', validators=[Optional()])
    module_id = SelectField('Module', validators=[Optional()])
    assignee_id = SelectField('Assignee', validators=[Optional()])
    start_date = DateField('Open Date', format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField('Close Date', format='%Y-%m-%d', validators=[Optional()])
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 设置默认选择项
        self.project_id.choices = [('', '全部项目')]
        self.module_id.choices = [('', '全部模块')]
        self.assignee_id.choices = [('', '全部负责人')]

class TestCaseForm(FlaskForm):
    """测试用例表单"""
    title = StringField('用例标题', validators=[DataRequired(), Length(max=200)])
    preconditions = TextAreaField('前置条件')
    test_steps = TextAreaField('测试步骤')
    expected_result = TextAreaField('预期结果', validators=[DataRequired()])
    priority = SelectField('优先级', choices=[
        ('高', '高'),
        ('中', '中'),
        ('低', '低')
    ])

class CommentForm(FlaskForm):
    """评论表单"""
    content = TextAreaField('评论内容', validators=[
        DataRequired(message='评论内容不能为空'),
        Length(min=1, max=1000)
    ])

class StatusChangeForm(FlaskForm):
    """状态更改表单"""
    status = SelectField('新状态', validators=[DataRequired()])
    comment = TextAreaField('备注', validators=[Optional()])
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 设置状态选择项
        self.status.choices = [
            ('Draft', 'Draft'),
            ('Submitted', 'Submitted'),
            ('Under review', 'Under review'),
            ('Approved', 'Approved'),
            ('In progress', 'In progress'),
            ('Testing', 'Testing'),
            ('Completed', 'Completed'),
            ('Rejected', 'Rejected'),
            ('Cancelled', 'Cancelled'),
            ('On Hold', 'On Hold')
        ]

class BulkImportForm(FlaskForm):
    """批量导入表单"""
    file = FileField('Excel文件', validators=[
        DataRequired(),
        FileAllowed(['xls', 'xlsx'], '只允许上传Excel文件')
    ])
    project_id = SelectField('导入到项目', validators=[DataRequired()])
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 设置默认选择项
        self.project_id.choices = [('', '选择项目')]

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    captcha = StringField('验证码')
    remember_me = BooleanField('记住我')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from flask import current_app
        if current_app.config.get('ENABLE_CAPTCHA', True):
            self.captcha.validators = [DataRequired()]
        else:
            self.captcha.validators = []

def password_check(form, field):
    password = field.data
    msg = '密码必须包含大写字母/小写字母/数字/特殊字符，当前缺：'
    items = []
    good = True
    if not re.search(r'[A-Z]', password):
        items.append('大写字母')
        good = False
    if not re.search(r'[a-z]', password):
        items.append('小写字母')
        good = False
    if not re.search(r'[0-9]', password):
        items.append('数字')
        good = False
    if not re.search(r'[~!@#$%^&*(),.?":{}|<>]', password):
        items.append('特殊字符')
        good = False
    if not good:
        raise ValidationError(msg+'、'.join(items)+'。')

class RegistrationForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=3, max=20)])
    email = StringField('电子邮件', validators=[DataRequired(), Email()])
    password = PasswordField('密码', validators=[DataRequired(), Length(min=8), password_check])
    password2 = PasswordField('确认密码', validators=[DataRequired(), EqualTo('password')])
    full_name = StringField('姓名', validators=[DataRequired()])

    def validate_username(self, username):
        from models import User
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('该用户名已被使用，请选择其他用户名。')

    def validate_email(self, email):
        from models import User
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('该电子邮件已被注册，请使用其他电子邮件。')


    
class PasswordResetRequestForm(FlaskForm):
    email = StringField('电子邮件', validators=[DataRequired(), Email()])

class PasswordResetForm(FlaskForm):
    password = PasswordField('新密码', validators=[DataRequired(), Length(min=8), password_check])
    password2 = PasswordField('确认新密码', validators=[DataRequired(), EqualTo('password')])
    token = HiddenField(label='Token')


# 用户管理表单
class AdminUserForm(FlaskForm):
    """管理员用户管理表单"""
    username: StringField = StringField('用户名', validators=[
        DataRequired('用户名不能为空'),
        Length(min=3, max=20, message='用户名长度必须在3-20个字符之间')
    ])
    
    email = StringField('邮箱', validators=[
        DataRequired('邮箱不能为空'),
        Email('请输入有效的邮箱地址')
    ])
    
    full_name = StringField('姓名', validators=[
        DataRequired('姓名不能为空'),
        Length(max=200, message='姓名长度不能超过200个字符')
    ])
    
    role = SelectField('角色', choices=[
        ('viewer', '查看者'),
        ('developer', '开发人员'),
        ('tester', '测试人员'),
        ('manager', '项目经理'),
        ('admin', '管理员')
    ], validators=[DataRequired('请选择角色')])
    
    department = StringField('部门', validators=[
        Optional(),
        Length(max=100, message='部门名称长度不能超过100个字符')
    ])
    
    is_active = BooleanField('启用账户')
    
    def validate_username(self, username):
        # 用户名格式验证
        pattern = r'^[a-zA-Z0-9_]+$'
        if not re.match(pattern, username.data):
            raise ValidationError('用户名只能包含字母、数字和下划线')


class AdminCreateUserForm(AdminUserForm):
    """管理员创建用户表单"""
    password = PasswordField('密码', validators=[
        DataRequired('密码不能为空'),
        Length(min=8, message='密码至少8位'),
        password_check
    ])
    
    password2 = PasswordField('确认密码', validators=[
        DataRequired('请确认密码'),
        EqualTo('password', message='两次输入的密码不一致')
    ])
    
    def validate_username(self, username):
        # 继承父类的用户名格式验证
        super().validate_username(username)
        
        # 检查用户名是否已存在
        from models import User
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('该用户名已被使用，请选择其他用户名')
    
    def validate_email(self, email):
        # 检查邮箱是否已存在
        from models import User
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('该邮箱已被注册，请使用其他邮箱')


class AdminEditUserForm(AdminUserForm):
    """管理员编辑用户表单"""
    new_password = PasswordField('新密码', validators=[
        Optional(),
        Length(min=8, message='密码至少8位'),
        password_check
    ])
    
    def __init__(self, original_user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_user = original_user
    
    def validate_username(self, username):
        # 继承父类的用户名格式验证
        super().validate_username(username)
        
        # 如果用户名没有变化，则不需要检查
        if self.original_user and username.data == self.original_user.username:
            return
        
        # 检查用户名是否已存在
        from models import User
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('该用户名已被使用，请选择其他用户名')
    
    def validate_email(self, email):
        # 如果邮箱没有变化，则不需要检查
        if self.original_user and email.data == self.original_user.email:
            return
        
        # 检查邮箱是否已存在
        from models import User
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('该邮箱已被注册，请使用其他邮箱')


class UserSearchForm(FlaskForm):
    """用户搜索表单"""
    search = StringField('搜索用户', validators=[
        Optional(),
        Length(max=100, message='The search keyword cannot exceed 100 characters')
    ])
    
    role = SelectField('角色筛选', choices=[
        ('all', '全部角色'),
        ('admin', '管理员'),
        ('manager', '项目经理'),
        ('developer', '开发人员'),
        ('tester', '测试人员'),
        ('viewer', '查看者')
    ], default='all')
    
    status = SelectField('状态筛选', choices=[
        ('all', '全部状态'),
        ('active', '已启用'),
        ('inactive', '已禁用')
    ], default='all')


# 项目管理表单
class ProjectForm(FlaskForm):
    """项目表单（创建/编辑）"""
    name = StringField('项目名称', validators=[
        DataRequired('项目名称不能为空'),
        Length(min=2, max=200, message='项目名称长度必须在2-200个字符之间')
    ])
    
    code = StringField('项目编码', validators=[
        DataRequired('项目编码不能为空'),
        Length(min=2, max=50, message='项目编码长度必须在2-50个字符之间')
    ])
    
    description = TextAreaField('项目描述', validators=[
        Optional(),
        Length(max=1000, message='项目描述长度不能超过1000个字符')
    ])
    
    start_date = DateField('开始日期', format='%Y-%m-%d', validators=[Optional()])
    
    end_date = DateField('结束日期', format='%Y-%m-%d', validators=[Optional()])
    
    status = SelectField('项目状态', choices=[
        ('active', 'In Progress'),
        ('planning', 'In planning'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
        ('cancelled', 'Cancelled')
    ], default='planning')
    
    manager_id = SelectField('项目经理', validators=[Optional()])
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 在初始化时动态设置选择项，避免循环导入
        self.manager_id.choices = [('', '选择项目经理')]
    
    def validate_end_date(self, end_date):
        """验证结束日期必须大于开始日期"""
        if self.start_date.data and end_date.data:
            if end_date.data <= self.start_date.data:
                raise ValidationError('结束日期必须大于开始日期')
    
    def validate_code(self, code):
        """验证项目编码格式"""
        # 项目编码只允许字母、数字、下划线和短横线
        pattern = r'^[a-zA-Z0-9_-]+$'
        if not re.match(pattern, code.data):
            raise ValidationError('项目编码只能包含字母、数字、下划线和短横线')


class ProjectCreateForm(ProjectForm):
    """项目创建表单"""
    def validate_code(self, code):
        # 继承父类的编码格式验证
        super().validate_code(code)
        
        # 检查项目编码是否已存在
        from models import Project
        project = Project.query.filter_by(code=code.data).first()
        if project:
            raise ValidationError('该项目编码已存在，请使用其他编码')


class ProjectEditForm(ProjectForm):
    """项目编辑表单"""
    def __init__(self, original_project=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_project = original_project
    
    def validate_code(self, code):
        # 继承父类的编码格式验证
        super().validate_code(code)
        
        # 如果项目编码没有变化，则不需要检查
        if self.original_project and code.data == self.original_project.code:
            return
        
        # 检查项目编码是否已存在
        from models import Project
        project = Project.query.filter_by(code=code.data).first()
        if project:
            raise ValidationError('该项目编码已存在，请使用其他编码')


class ProjectFilterForm(FlaskForm):
    """项目筛选表单"""
    keyword = StringField('search keyword', validators=[
        Optional(),
        Length(max=100, message='The search keyword cannot exceed 100 characters')
    ])
    
    status = SelectField('项目状态', choices=[
        ('', '全部状态'),
        ('active', 'In Progress'),
        ('planning', 'In planning'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
        ('cancelled', 'Cancelled')
    ], default='')
    
    manager_id = SelectField('项目经理', validators=[Optional()])
    
    start_date = DateField('开始日期', format='%Y-%m-%d', validators=[Optional()])
    
    end_date = DateField('结束日期', format='%Y-%m-%d', validators=[Optional()])
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 在初始化时动态设置选择项，避免循环导入
        self.manager_id.choices = [('', '全部经理')]


class ProjectMemberForm(FlaskForm):
    """项目成员管理表单"""
    user_ids = SelectMultipleField('选择成员', validators=[
        DataRequired('请至少选择一个成员')
    ])
    
    role = SelectField('成员角色', choices=[
        ('member', '普通成员'),
        ('developer', '开发人员'),
        ('tester', '测试人员'),
        ('analyst', '需求分析师'),
        ('reviewer', '评审人员')
    ], default='member', validators=[DataRequired()])


class ProjectStatisticsForm(FlaskForm):
    """项目统计筛选表单"""
    project_ids = SelectMultipleField('选择项目', validators=[Optional()])
    
    date_range = SelectField('时间范围', choices=[
        ('7', '最近7天'),
        ('30', '最近30天'),
        ('90', '最近3个月'),
        ('180', '最近6个月'),
        ('365', '最近1年'),
        ('custom', '自定义时间')
    ], default='30')
    
    start_date = DateField('开始日期', format='%Y-%m-%d', validators=[Optional()])
    
    end_date = DateField('结束日期', format='%Y-%m-%d', validators=[Optional()])
    
    def validate(self, **kwargs):
        """自定义验证逻辑"""
        if not super().validate(**kwargs):
            return False
        
        # 如果选择自定义时间，必须提供开始和结束日期
        if self.date_range.data == 'custom':
            if not self.start_date.data or not self.end_date.data:
                self.date_range.errors.append('选择自定义时间时，必须提供开始和结束日期')
                return False
            
            if self.end_date.data <= self.start_date.data:
                self.end_date.errors.append('结束日期必须大于开始日期')
                return False
        
        return True
