from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, desc, func
from datetime import datetime, timedelta, timezone
import json

# 定义北京时区
BEIJING_TZ = timezone(timedelta(hours=8))

from models import db, Project, User, Requirement, RequirementStatus
from forms import (ProjectCreateForm, ProjectEditForm, ProjectFilterForm, 
                   ProjectMemberForm, ProjectStatisticsForm)
from auth_decorators import admin_required, manager_required

# 创建蓝图
project_bp = Blueprint('project', __name__, url_prefix='/projects')

@project_bp.route('/')
@login_required
def index():
    """项目列表页"""
    # 获取筛选表单
    filter_form = ProjectFilterForm(request.args)
    
    # 基础查询
    query = Project.query
    
    # 根据用户角色限制可见项目
    if current_user.role not in ['admin', 'manager']:
        # 普通用户只能看到自己参与的项目
        query = query.filter(
            or_(
                Project.manager_id == current_user.id,
                Project.id.in_(
                    db.session.query(Requirement.project_id)
                    .filter(
                        or_(
                            Requirement.creator_id == current_user.id,
                            Requirement.assignee_id == current_user.id,
                            Requirement.reviewer_id == current_user.id
                        )
                    ).distinct()
                )
            )
        )
    
    # 应用筛选条件
    if filter_form.keyword.data:
        keyword = f"%{filter_form.keyword.data}%"
        query = query.filter(
            or_(
                Project.name.like(keyword),
                Project.code.like(keyword),
                Project.description.like(keyword)
            )
        )
    
    if filter_form.status.data:
        query = query.filter(Project.status == filter_form.status.data)
    
    if filter_form.manager_id.data and filter_form.manager_id.data != '':
        try:
            manager_id = int(filter_form.manager_id.data)
            query = query.filter(Project.manager_id == manager_id)
        except (ValueError, TypeError):
            pass  # 忽略无效的manager_id值
    
    if filter_form.start_date.data:
        query = query.filter(Project.start_date >= filter_form.start_date.data)
    
    if filter_form.end_date.data:
        query = query.filter(Project.end_date <= filter_form.end_date.data)
    
    # 分页
    page = request.args.get('page', 1, type=int)
    per_page = 10  # 每页显示数量
    projects = query.order_by(desc(Project.id)).paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    # 为筛选表单设置选择项
    filter_form.manager_id.choices = [('', '全部经理')] + [
        (str(u.id), u.full_name or u.username) for u in User.query.filter(
            User.role.in_(['admin', 'manager'])
        ).all()
    ]
    
    # 获取每个项目的需求统计信息
    project_stats = {}
    for project in projects.items:
        # 直接调用已修复的统计函数
        stats = _get_project_requirements_stats(project.id)
        
        project_stats[project.id] = {
            'total': stats['total'],
            'completed': stats['completed'],
            'in_development': stats['in_development'],
            'completion_rate': stats['completion_rate']
        }
    
    return render_template('projects/index.html',
                         projects=projects,
                         project_stats=project_stats,
                         filter_form=filter_form)


@project_bp.route('/create', methods=['GET', 'POST'])
@login_required
@manager_required  # 需要经理级别权限
def create():
    """创建项目"""
    form = ProjectCreateForm()
    
    # 设置项目经理选择项
    form.manager_id.choices = [('', '选择项目经理')] + [
        (u.id, u.full_name or u.username) for u in User.query.filter(
            User.role.in_(['admin', 'manager']), User.is_active == True
        ).all()
    ]
    
    if form.validate_on_submit():
        try:
            # 处理manager_id的类型转换
            manager_id = None
            if form.manager_id.data and form.manager_id.data != '':
                try:
                    manager_id = int(form.manager_id.data)
                except (ValueError, TypeError):
                    manager_id = None
            
            project = Project(
                name=form.name.data,
                code=form.code.data,
                description=form.description.data,
                start_date=form.start_date.data,
                end_date=form.end_date.data,
                status=form.status.data,
                manager_id=manager_id
            )
            
            db.session.add(project)
            db.session.commit()
            
            flash(f'项目 "{project.name}" 创建成功！', 'success')
            return redirect(url_for('project.detail', id=project.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'创建项目时发生错误：{str(e)}', 'error')
    
    return render_template('projects/create.html', form=form)


@project_bp.route('/<int:id>')
@login_required
def detail(id):
    """项目详情页"""
    project = Project.query.get_or_404(id)
    
    # 检查用户权限
    if not _can_access_project(project):
        flash('您没有权限访问该项目', 'error')
        return redirect(url_for('project.index'))
    
    # 获取项目需求统计
    requirements_stats = _get_project_requirements_stats(project.id)
    
    # 获取最近的需求活动
    recent_requirements = Requirement.query.filter_by(project_id=project.id)\
        .order_by(desc(Requirement.updated_at)).limit(5).all()
    
    # 获取项目团队成员（通过需求关联）
    team_members = db.session.query(User).join(Requirement, 
        or_(
            Requirement.creator_id == User.id,
            Requirement.assignee_id == User.id,
            Requirement.reviewer_id == User.id
        )
    ).filter(Requirement.project_id == project.id).distinct().all()
    
    return render_template('projects/detail.html',
                         project=project,
                         requirements_stats=requirements_stats,
                         recent_requirements=recent_requirements,
                         team_members=team_members)


@project_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """编辑项目"""
    project = Project.query.get_or_404(id)
    
    # 检查权限
    if not _can_edit_project(project):
        flash('您没有权限编辑该项目', 'error')
        return redirect(url_for('project.detail', id=id))
    
    form = ProjectEditForm(original_project=project, obj=project)
    
    # 设置项目经理选择项
    form.manager_id.choices = [('', '选择项目经理')] + [
        (u.id, u.full_name or u.username) for u in User.query.filter(
            User.role.in_(['admin', 'manager']), User.is_active == True
        ).all()
    ]
    
    if form.validate_on_submit():
        try:
            form.populate_obj(project)
            # 处理manager_id的类型转换
            if form.manager_id.data and form.manager_id.data != '':
                try:
                    project.manager_id = int(form.manager_id.data)
                except (ValueError, TypeError):
                    project.manager_id = None
            else:
                project.manager_id = None
            
            db.session.commit()
            
            flash(f'项目 "{project.name}" 更新成功！', 'success')
            return redirect(url_for('project.detail', id=project.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'更新项目时发生错误：{str(e)}', 'error')
    
    return render_template('projects/edit.html', form=form, project=project)


@project_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@admin_required  # 只有管理员可以删除项目
def delete(id):
    """删除项目"""
    project = Project.query.get_or_404(id)
    
    try:
        # 检查项目是否有关联的需求
        requirement_count = Requirement.query.filter_by(project_id=project.id).count()
        if requirement_count > 0:
            flash(f'无法删除项目：项目中还有 {requirement_count} 个需求，请先删除或转移这些需求。', 'error')
            return redirect(url_for('project.detail', id=id))
        
        project_name = project.name
        db.session.delete(project)
        db.session.commit()
        
        flash(f'项目 "{project_name}" 已删除', 'success')
        return redirect(url_for('project.index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'删除项目时发生错误：{str(e)}', 'error')
        return redirect(url_for('project.detail', id=id))


@project_bp.route('/<int:id>/statistics')
@login_required
def statistics(id):
    """项目统计页面"""
    project = Project.query.get_or_404(id)
    
    # 检查用户权限
    if not _can_access_project(project):
        flash('您没有权限访问该项目', 'error')
        return redirect(url_for('project.index'))
    
    # 获取统计数据
    stats_data = _get_comprehensive_project_stats(project.id)
    
    return render_template('projects/statistics.html',
                         project=project,
                         stats_data=stats_data)


@project_bp.route('/statistics/data')
@login_required
def statistics_data():
    """项目统计数据API"""
    # 获取所有用户可访问的项目统计数据
    projects = []
    
    if current_user.role in ['admin', 'manager']:
        projects = Project.query.all()
    else:
        # 普通用户只能看到自己参与的项目
        projects = Project.query.filter(
            or_(
                Project.manager_id == current_user.id,
                Project.id.in_(
                    db.session.query(Requirement.project_id)
                    .filter(
                        or_(
                            Requirement.creator_id == current_user.id,
                            Requirement.assignee_id == current_user.id,
                            Requirement.reviewer_id == current_user.id
                        )
                    ).distinct()
                )
            )
        ).all()
    
    stats = []
    for project in projects:
        project_stats = _get_project_requirements_stats(project.id)
        stats.append({
            'id': project.id,
            'name': project.name,
            'code': project.code,
            'status': project.status,
            'requirements_total': project_stats['total'],
            'requirements_completed': project_stats['completed'],
            'completion_rate': project_stats['completion_rate'],
            'start_date': project.start_date.isoformat() if project.start_date else None,
            'end_date': project.end_date.isoformat() if project.end_date else None
        })
    
    return jsonify({'projects': stats})


def _can_access_project(project):
    """检查用户是否可以访问项目"""
    if current_user.role in ['admin', 'manager']:
        return True
    
    if project.manager_id == current_user.id:
        return True
    
    # 检查用户是否参与了项目中的需求
    requirement_exists = Requirement.query.filter(
        Requirement.project_id == project.id,
        or_(
            Requirement.creator_id == current_user.id,
            Requirement.assignee_id == current_user.id,
            Requirement.reviewer_id == current_user.id
        )
    ).first()
    
    return requirement_exists is not None


def _can_edit_project(project):
    """检查用户是否可以编辑项目"""
    if current_user.role == 'admin':
        return True
    
    if current_user.role == 'manager' and project.manager_id == current_user.id:
        return True
    
    return False


def _get_project_requirements_stats(project_id):
    """获取项目需求统计信息"""
    from sqlalchemy import case
    
    # 先获取总数
    total = db.session.query(func.count(Requirement.id)).filter(
        Requirement.project_id == project_id
    ).scalar() or 0
    
    # 获取所有状态的统计
    status_counts = db.session.query(
        Requirement.status,
        func.count(Requirement.id).label('count')
    ).filter(Requirement.project_id == project_id).group_by(Requirement.status).all()
    
    # 初始化状态统计
    status_stats = {status.value: 0 for status in RequirementStatus}
    
    # 填充实际统计数据
    for status, count in status_counts:
        if status in status_stats:
            status_stats[status] = count
    
    # 计算完成率
    completed = status_stats.get(RequirementStatus.COMPLETED.value, 0)
    completion_rate = round((completed / total * 100), 1) if total > 0 else 0
    
    return {
        'total': total,
        'completed': completed,
        'in_development': status_stats.get(RequirementStatus.IN_DEVELOPMENT.value, 0),
        'testing': status_stats.get(RequirementStatus.TESTING.value, 0),
        'draft': status_stats.get(RequirementStatus.DRAFT.value, 0),
        'submitted': status_stats.get(RequirementStatus.SUBMITTED.value, 0),
        'reviewing': status_stats.get(RequirementStatus.REVIEWING.value, 0),
        'approved': status_stats.get(RequirementStatus.APPROVED.value, 0),
        'rejected': status_stats.get(RequirementStatus.REJECTED.value, 0),
        'cancelled': status_stats.get(RequirementStatus.CANCELLED.value, 0),
        'on_hold': status_stats.get(RequirementStatus.ON_HOLD.value, 0),
        'completion_rate': completion_rate
    }


def _get_comprehensive_project_stats(project_id):
    """获取项目综合统计信息"""
    from datetime import datetime
    
    # 基本需求统计
    requirements_stats = _get_project_requirements_stats(project_id)
    
    # 按优先级统计
    priority_stats = db.session.query(
        Requirement.priority,
        func.count(Requirement.id).label('count')
    ).filter(Requirement.project_id == project_id)\
     .group_by(Requirement.priority).all()
    
    # 按类型统计
    type_stats = db.session.query(
        Requirement.type,
        func.count(Requirement.id).label('count')
    ).filter(Requirement.project_id == project_id)\
     .group_by(Requirement.type).all()
    
    # 最近30天的需求创建趋势
    thirty_days_ago = datetime.now(BEIJING_TZ) - timedelta(days=30)
    trend_stats = db.session.query(
        func.date(Requirement.created_at).label('date'),
        func.count(Requirement.id).label('count')
    ).filter(
        Requirement.project_id == project_id,
        Requirement.created_at >= thirty_days_ago
    ).group_by(func.date(Requirement.created_at)).all()
    
    # 处理趋势数据，确保日期格式正确
    trend_data = []
    for stat in trend_stats:
        # 处理 SQLite 中 func.date() 返回字符串的情况
        date_str = stat.date
        if isinstance(date_str, str):
            # 已经是字符串格式，直接使用
            trend_data.append({'date': date_str, 'count': stat.count})
        else:
            # 如果是日期对象，转换为字符串
            trend_data.append({'date': date_str.isoformat(), 'count': stat.count})
    
    # 处理优先级统计，提供默认值
    priority_dict = {stat.priority: stat.count for stat in priority_stats}
    if not priority_dict:  # 如果没有数据，提供默认值
        priority_dict = {'中': 0}  # 提供一个默认的优先级
    
    # 处理类型统计，提供默认值
    type_dict = {stat.type: stat.count for stat in type_stats}
    if not type_dict:  # 如果没有数据，提供默认值
        type_dict = {'功能': 0}  # 提供一个默认的类型
    
    return {
        'requirements': requirements_stats,
        'priority': priority_dict,
        'type': type_dict,
        'trend': trend_data if trend_data else [{'date': datetime.now(BEIJING_TZ).strftime('%Y-%m-%d'), 'count': 0}]  # 提供默认的趋势数据
    }