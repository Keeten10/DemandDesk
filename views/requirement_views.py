from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, extract
from sqlalchemy import or_

# 定义北京时区
BEIJING_TZ = timezone(timedelta(hours=8))
from models import db, Requirement, Project, Module, Category, User, Tag, RequirementHistory, Comment, Attachment
from forms import RequirementForm, RequirementFilterForm, TestCaseForm, CommentForm, BulkImportForm, StatusChangeForm
from services.requirement_service import RequirementService
import json
import os
import uuid
from werkzeug.utils import secure_filename

requirement_bp = Blueprint('requirement', __name__, url_prefix='/requirements')

def allowed_file(filename):
    """检查文件扩展名是否被允许"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def save_uploaded_file(file, requirement_id):
    """保存上传的文件并返回附件对象"""
    if file and file.filename and allowed_file(file.filename):
        # 生成安全的文件名
        original_filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
        
        # 确保上传目录存在
        upload_folder = current_app.config['UPLOAD_FOLDER']
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        
        # 保存文件
        file_path = os.path.join(upload_folder, unique_filename)
        file.save(file_path)
        
        # 获取文件大小
        file_size = os.path.getsize(file_path)
        
        # 创建附件记录
        attachment = Attachment(
            requirement_id=requirement_id,
            filename=original_filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=file.content_type,
            uploaded_by=current_user.id
        )
        
        return attachment
    return None

@requirement_bp.route('/')
@login_required
def index():
    """Requirements List视图"""
    filter_form = RequirementFilterForm(request.args)
    
    # 填充选择框选项
    filter_form.project_id.choices = [('', 'All')] + [(str(p.id), p.name) for p in Project.query.all()]
    filter_form.module_id.choices = [('', 'All')] + [(str(m.id), m.name) for m in Module.query.all()]
    filter_form.assignee_id.choices = [('', 'All')] + [(str(u.id), u.full_name) for u in User.query.filter_by(is_active=True).all()]
    
    # 构建过滤条件
    filters = {
        'keyword': filter_form.keyword.data,
        'type': filter_form.type.data,
        'status': filter_form.status.data,
        'priority': filter_form.priority.data,
        'project_id': filter_form.project_id.data if filter_form.project_id.data else None,
        'module_id': filter_form.module_id.data if filter_form.module_id.data else None,
        'assignee_id': filter_form.assignee_id.data if filter_form.assignee_id.data else None,
        'start_date': filter_form.start_date.data,
        'end_date': filter_form.end_date.data
    }
    
    # 获取分页参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)  # 默认20条每页
    
    # 搜索需求（返回分页对象）
    # 对于查看者角色和开发者等非管理员角色，只显示其参与的项目需求
    if current_user.role in ['viewer', 'developer', 'tester']:
        # 获取用户参与的项目ID列表（创建者、负责人或评审人）
        participant_project_ids = db.session.query(Requirement.project_id).filter(
            or_(
                Requirement.creator_id == current_user.id,
                Requirement.assignee_id == current_user.id,
                Requirement.reviewer_id == current_user.id
            )
        ).distinct().all()
        
        # 将结果转换为ID列表
        project_ids = [pid[0] for pid in participant_project_ids if pid[0] is not None]
        
        # 添加项目ID过滤条件
        if project_ids:
            # 如果有过滤条件中的项目ID，则只保留用户参与的项目
            if filters.get('project_id'):
                # 如果用户选择了特定项目，检查该项目是否在参与项目中
                selected_project_id = int(filters['project_id'])
                if selected_project_id in project_ids:
                    # 保留选择的项目
                    pass
                else:
                    # 如果选择的项目不在参与项目中，设置为空（不显示任何需求）
                    filters['project_id'] = None
                    # 添加一个提示信息
                    flash('您只能查看自己参与的项目需求', 'info')
            else:
                # 如果没有选择特定项目，添加参与项目过滤
                filters['project_ids'] = project_ids
        else:
            # 如果用户没有参与任何项目，设置一个空的项目ID列表以确保不显示任何需求
            filters['project_ids'] = []
    elif current_user.role == 'manager':
        # 项目经理可以看到自己管理的项目需求
        managed_project_ids = [p.id for p in current_user.managed_projects]
        if managed_project_ids:
            if filters.get('project_id'):
                # 如果用户选择了特定项目，检查该项目是否在其管理的项目中
                selected_project_id = int(filters['project_id'])
                if selected_project_id not in managed_project_ids:
                    # 如果选择的项目不在管理的项目中，设置为空
                    filters['project_id'] = None
                    flash('您只能查看自己管理的项目需求', 'info')
            else:
                # 如果没有选择特定项目，添加管理项目过滤
                filters['project_ids'] = managed_project_ids
        else:
            # 如果用户没有管理任何项目，设置一个空的项目ID列表
            filters['project_ids'] = []
    
    requirements = RequirementService.search_requirements(
        filters, 
        page=page, 
        per_page=per_page, 
        paginate=True
    )
    
    # 获取统计信息（不分页，用于显示总统计）
    stats = RequirementService.calculate_statistics(filters.get('project_id'))
    
    return render_template('requirements/index.html',
                         requirements=requirements,
                         filter_form=filter_form,
                         stats=stats)

@requirement_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """创建需求"""
    # 权限检查：只有管理员、经理、开发人员和测试人员可以创建需求
    # 查看者（viewer）只能查看，不能创建
    if current_user.role == 'viewer':
        flash('您没有权限创建需求，只能查看', 'warning')
        return redirect(url_for('requirement.index'))
    
    form = RequirementForm()
    
    # 使用统一的选择项填充方法
    form.populate_choices()
    
    # 检查是否有项目ID参数，如果有则设置为默认值
    project_id = request.args.get('project_id')
    if project_id:
        # 验证项目ID是否有效
        project = Project.query.get(project_id)
        if project and project_id in [choice[0] for choice in form.project_id.choices]:
            form.project_id.data = project_id
    
    if form.validate_on_submit():
        # 处理表单数据的类型转换
        data = {
            'title': form.title.data,
            'description': form.description.data,
            'type': form.type.data,
            'category_id': int(form.category_id.data) if form.category_id.data and form.category_id.data != '' else None,
            'module_id': int(form.module_id.data) if form.module_id.data and form.module_id.data != '' else None,
            'project_id': int(form.project_id.data) if form.project_id.data and form.project_id.data != '' else None,
            'status': form.status.data,
            'priority': form.priority.data,
            'assignee_id': int(form.assignee_id.data) if form.assignee_id.data and form.assignee_id.data != '' else None,
            'reviewer_id': int(form.reviewer_id.data) if form.reviewer_id.data and form.reviewer_id.data != '' else None,
            'background': form.background.data,
            'objective': form.objective.data,
            'scope': form.scope.data,
            'acceptance_criteria': form.acceptance_criteria.data,
            'assumptions': form.assumptions.data,
            'constraints': form.constraints.data,
            'risks': form.risks.data,
            'estimated_hours': form.estimated_hours.data,
            'story_points': form.story_points.data,
            'business_value': form.business_value.data,
            'due_date': form.due_date.data,
            'start_date': form.start_date.data,
            'version': form.version.data,
            'source': form.source.data
        }
        
        try:
            requirement = RequirementService.create_requirement(data, current_user.id)
            
            # 处理标签
            if form.tags.data:
                tags = Tag.query.filter(Tag.id.in_(form.tags.data)).all()
                requirement.tags = tags
            
            # 处理依赖
            if form.dependencies.data:
                dependencies = Requirement.query.filter(Requirement.id.in_(form.dependencies.data)).all()
                requirement.dependencies = dependencies
            
            db.session.commit()
            flash('需求创建成功！', 'success')
            return redirect(url_for('requirement.view', id=requirement.id))
        except Exception as e:
            flash(f'创建失败: {str(e)}', 'danger')
            db.session.rollback()
    
    return render_template('requirements/create.html', form=form)

@requirement_bp.route('/<int:id>')
@login_required
def view(id):
    """查看需求详情"""
    requirement = Requirement.query.get_or_404(id)
    
    # 获取影响分析
    impact = RequirementService.analyze_impact(id)
    
    # 获取历史记录
    history = requirement.history.order_by(RequirementHistory.created_at.desc()).limit(10).all()
    
    # 评论表单
    comment_form = CommentForm()
    
    # 测试用例表单
    test_case_form = TestCaseForm()
    
    # 状态更改表单
    status_form = StatusChangeForm()
    
    return render_template('requirements/view.html',
                         requirement=requirement,
                         impact=impact,
                         history=history,
                         comment_form=comment_form,
                         test_case_form=test_case_form,
                         status_form=status_form)

@requirement_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """编辑需求"""
    requirement = Requirement.query.get_or_404(id)
    
    # 权限检查：只有管理员、经理、开发人员和测试人员可以编辑需求
    # 查看者（viewer）只能查看，不能编辑
    if current_user.role == 'viewer':
        flash('您没有权限编辑需求，只能查看', 'warning')
        return redirect(url_for('requirement.view', id=id))
    form = RequirementForm(obj=requirement)
    
    # 填充表单选择项
    form.populate_choices()
    
    # 设置当前值（需要转换为字符串）
    if requirement.category_id:
        form.category_id.data = str(requirement.category_id)
    if requirement.module_id:
        form.module_id.data = str(requirement.module_id)
    if requirement.project_id:
        form.project_id.data = str(requirement.project_id)
    if requirement.assignee_id:
        form.assignee_id.data = str(requirement.assignee_id)
    if requirement.reviewer_id:
        form.reviewer_id.data = str(requirement.reviewer_id)
    
    if form.validate_on_submit():
        try:
            # 准备更新数据字典
            update_data = {
                'title': form.title.data,
                'description': form.description.data,
                'type': form.type.data,
                'status': form.status.data,
                'priority': form.priority.data,
                'background': form.background.data,
                'objective': form.objective.data,
                'scope': form.scope.data,
                'acceptance_criteria': form.acceptance_criteria.data,
                'assumptions': form.assumptions.data,
                'constraints': form.constraints.data,
                'risks': form.risks.data,
                'estimated_hours': form.estimated_hours.data,
                'story_points': form.story_points.data,
                'business_value': form.business_value.data,
                'due_date': form.due_date.data,
                'start_date': form.start_date.data,
                'version': form.version.data,
                'source': form.source.data
            }
            
            # 处理外键字段的类型转换
            update_data['category_id'] = int(form.category_id.data) if form.category_id.data and form.category_id.data != '' else None
            update_data['module_id'] = int(form.module_id.data) if form.module_id.data and form.module_id.data != '' else None
            update_data['project_id'] = int(form.project_id.data) if form.project_id.data and form.project_id.data != '' else None
            update_data['assignee_id'] = int(form.assignee_id.data) if form.assignee_id.data and form.assignee_id.data != '' else None
            update_data['reviewer_id'] = int(form.reviewer_id.data) if form.reviewer_id.data and form.reviewer_id.data != '' else None
            
            # 使用服务方法更新需求（会自动记录历史）
            RequirementService.update_requirement(requirement.id, update_data, current_user.id)
            
            # 处理文件上传
            if form.attachments.data:
                attachment = save_uploaded_file(form.attachments.data, requirement.id)
                if attachment:
                    db.session.add(attachment)
                    flash('文件上传成功！', 'success')
                else:
                    flash('文件上传失败，请检查文件格式。', 'warning')
            
            # 提交文件上传相关的数据库更改
            db.session.commit()
            flash('需求更新成功！', 'success')
            return redirect(url_for('requirement.view', id=id))
        except Exception as e:
            flash(f'更新失败: {str(e)}', 'danger')
            db.session.rollback()
    
    # 预处理历史记录，使用正确的SQLAlchemy语法
    recent_history = requirement.history.order_by(RequirementHistory.created_at.desc()).limit(5).all()
    
    return render_template('edit.html', form=form, requirement=requirement, recent_history=recent_history)

@requirement_bp.route('/<int:id>/change-status', methods=['POST'])
@login_required
def change_status(id):
    """更改需求状态"""
    # 权限检查：只有管理员、经理、开发人员和测试人员可以更改需求状态
    if current_user.role == 'viewer':
        flash('您没有权限更改需求状态，只能查看', 'warning')
        return redirect(url_for('requirement.view', id=id))
    
    new_status = request.form.get('status')
    comment = request.form.get('comment')
    
    try:
        RequirementService.change_status(id, new_status, current_user.id, comment)
        flash('状态更新成功！', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    except Exception as e:
        flash(f'操作失败: {str(e)}', 'danger')
    
    return redirect(url_for('requirement.view', id=id))

@requirement_bp.route('/<int:id>/add_comment', methods=['POST'])
@login_required
def add_comment(id):
    """添加评论"""
    # 权限检查：只有非查看者可以添加评论
    if current_user.role == 'viewer':
        flash('您没有权限添加评论，只能查看', 'warning')
        return redirect(url_for('requirement.view', id=id))
    
    requirement = Requirement.query.get_or_404(id)
    form = CommentForm()
    
    if form.validate_on_submit():
        comment = Comment(
            requirement_id=id,
            user_id=current_user.id,
            content=form.content.data
        )
        
        try:
            db.session.add(comment)
            db.session.commit()
            flash('评论添加成功！', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'添加评论失败: {str(e)}', 'danger')
    else:
        flash('评论内容不能为空', 'danger')
    
    return redirect(url_for('requirement.view', id=id))

@requirement_bp.route('/attachments/<int:id>/download')
@login_required
def download_attachment(id):
    """下载附件"""
    attachment = Attachment.query.get_or_404(id)
    
    try:
        return send_file(
            attachment.file_path,
            as_attachment=True,
            download_name=attachment.filename
        )
    except FileNotFoundError:
        flash('附件文件不存在', 'danger')
        return redirect(url_for('requirement.view', id=attachment.requirement_id))
    except Exception as e:
        flash(f'下载失败: {str(e)}', 'danger')
        return redirect(url_for('requirement.view', id=attachment.requirement_id))

@requirement_bp.route('/attachments/<int:id>/delete', methods=['DELETE'])
@login_required
def delete_attachment(id):
    """删除附件"""
    attachment = Attachment.query.get_or_404(id)
    
    try:
        # 删除物理文件
        if os.path.exists(attachment.file_path):
            os.remove(attachment.file_path)
        
        # 删除数据库记录
        db.session.delete(attachment)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '附件删除成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})

@requirement_bp.route('/<int:id>/upload_attachment', methods=['POST'])
@login_required
def upload_attachment(id):
    """上传附件到指定需求"""
    # 权限检查：只有非查看者可以上传附件
    if current_user.role == 'viewer':
        return jsonify({'success': False, 'message': '您没有权限上传附件，只能查看'})
    
    requirement = Requirement.query.get_or_404(id)
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有选择文件'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'})
    
    if file and allowed_file(file.filename):
        try:
            attachment = save_uploaded_file(file, id)
            if attachment:
                db.session.add(attachment)
                db.session.commit()
                return jsonify({
                    'success': True, 
                    'message': '文件上传成功',
                    'attachment': {
                        'id': attachment.id,
                        'filename': attachment.filename,
                        'size': attachment.file_size
                    }
                })
            else:
                return jsonify({'success': False, 'message': '文件上传失败'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'上传失败: {str(e)}'})
    else:
        return jsonify({'success': False, 'message': '不支持的文件格式'})

@requirement_bp.route('/export')
@login_required
def export():
    """导出需求"""
    # 获取过滤条件
    filters = request.args.to_dict()
    requirements = RequirementService.search_requirements(filters, paginate=False)
    
    # 生成Excel文件
    output = RequirementService.export_requirements(requirements)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'requirements_{datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")}.xlsx'
    )

@requirement_bp.route('/import', methods=['GET', 'POST'])
@login_required
def bulk_import():
    """批量导入需求"""
    form = BulkImportForm()
    form.project_id.choices = [(str(p.id), p.name) for p in Project.query.filter_by(status='active').all()]
    
    if form.validate_on_submit():
        file = form.file.data
        project_id = form.project_id.data
        
        success_count, errors = RequirementService.import_requirements(
            file, project_id, current_user.id
        )
        
        if success_count > 0:
            flash(f'成功导入 {success_count} 条需求', 'success')
        
        if errors:
            for error in errors:
                flash(error, 'warning')
        
        return redirect(url_for('requirement.index'))
    
    return render_template('requirements/import.html', form=form)

@requirement_bp.route('/statistics')
@login_required
def statistics():
    """需求统计页面"""
    project_id = request.args.get('project_id', type=int)
    stats = RequirementService.calculate_statistics(project_id)
    
    # 获取项目列表
    projects = Project.query.filter_by(status='active').all()
    
    # 计算月度趋势数据（过6个月）
    
    current_date = datetime.now(BEIJING_TZ)
    trend_data = {
        'labels': [],
        'created_data': [],
        'completed_data': []
    }
    
    for i in range(6):
        # 计算月份
        target_date = current_date - timedelta(days=30 * i)
        month_label = f"{target_date.month}月"
        trend_data['labels'].insert(0, month_label)
        
        # 计算该月创建的需求数
        created_query = Requirement.query.filter(
            extract('year', Requirement.created_at) == target_date.year,
            extract('month', Requirement.created_at) == target_date.month
        )
        if project_id:
            created_query = created_query.filter_by(project_id=project_id)
        created_count = created_query.count()
        trend_data['created_data'].insert(0, created_count)
        
        # 计算该月完成的需求数
        completed_query = Requirement.query.filter(
            extract('year', Requirement.updated_at) == target_date.year,
            extract('month', Requirement.updated_at) == target_date.month,
            Requirement.status.in_(['Completed', 'completed'])
        )
        if project_id:
            completed_query = completed_query.filter_by(project_id=project_id)
        completed_count = completed_query.count()
        trend_data['completed_data'].insert(0, completed_count)
    
    # 计算项目需求分布数据
    project_distribution = []
    for project in Project.query.filter_by(status='active').all():
        req_query = Requirement.query.filter_by(project_id=project.id)
        
        pending = req_query.filter(Requirement.status.in_(['草稿', '已提交', '评审中'])).count()
        in_progress = req_query.filter(Requirement.status.in_(['In progress', '测试中'])).count()
        completed = req_query.filter(Requirement.status.in_(['Completed'])).count()
        
        project_distribution.append({
            'name': project.name,
            'pending': pending,
            'in_progress': in_progress,
            'completed': completed
        })
    
    # 准备图表数据
    charts_data = {
        'status_chart': {
            'labels': list(stats['status_stats'].keys()),
            'data': list(stats['status_stats'].values())
        },
        'priority_chart': {
            'labels': list(stats['priority_stats'].keys()),
            'data': list(stats['priority_stats'].values())
        },
        'type_chart': {
            'labels': list(stats['type_stats'].keys()),
            'data': list(stats['type_stats'].values())
        },
        'trend_chart': trend_data,
        'project_chart': {
            'labels': [p['name'] for p in project_distribution],
            'pending_data': [p['pending'] for p in project_distribution],
            'in_progress_data': [p['in_progress'] for p in project_distribution],
            'completed_data': [p['completed'] for p in project_distribution]
        }
    }
    
    # 获取团队工作量统计（简化版）
    team_stats = []
    users = User.query.filter_by(is_active=True).all()
    for user in users:
        user_requirements = Requirement.query.filter_by(assignee_id=user.id)
        if project_id:
            user_requirements = user_requirements.filter_by(project_id=project_id)
        
        pending = user_requirements.filter(Requirement.status.in_(['草稿', '已提交', '评审中'])).count()
        in_progress = user_requirements.filter(Requirement.status.in_(['已批准', 'In progress', '测试中'])).count() 
        completed = user_requirements.filter_by(status='Completed').count()
        total = pending + in_progress + completed
        
        if total > 0:  # 只显示有需求的用户
            completion_rate = round((completed / total) * 100, 1) if total > 0 else 0
            estimated_hours = user_requirements.with_entities(func.sum(Requirement.estimated_hours)).scalar() or 0
            
            team_stats.append({
                'name': user.full_name or user.username,
                'avatar': getattr(user, 'avatar', None),
                'pending': pending,
                'in_progress': in_progress,
                'completed': completed,
                'total': total,
                'estimated_hours': round(estimated_hours, 1),
                'completion_rate': completion_rate
            })
    
    return render_template('requirements/statistics.html',
                         stats=stats,
                         charts_data=charts_data,
                         projects=projects,
                         team_stats=team_stats)

# API端点
@requirement_bp.route('/api/requirements')
@login_required
def api_list():
    """API: 获取Requirements List"""
    requirements = Requirement.query.all()
    return jsonify([req.to_dict() for req in requirements])

@requirement_bp.route('/api/requirements/<int:id>')
@login_required
def api_get(id):
    """API: 获取单个需求"""
    requirement = Requirement.query.get_or_404(id)
    return jsonify(requirement.to_dict())

@requirement_bp.route('/api/requirements/<int:id>/impact')
@login_required
def api_impact(id):
    """API: 获取需求影响分析"""
    impact = RequirementService.analyze_impact(id)
    return jsonify(impact)

@requirement_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete_requirement(id):
    """删除需求"""
    # 权限检查：只有管理员、经理、开发人员和测试人员可以删除需求
    # 查看者（viewer）只能查看，不能删除
    if current_user.role == 'viewer':
        flash('您没有权限删除需求，只能查看', 'warning')
        return redirect(url_for('requirement.index'))
    
    requirement = Requirement.query.get_or_404(id)
    
    try:
        # 记录删除历史
        RequirementService.add_history(
            requirement_id=id,
            user_id=current_user.id,
            action='delete',
            comment='删除需求'
        )
        
        # 删除需求（由于设置了cascade='all, delete-orphan'，相关附件、评论等会自动删除）
        db.session.delete(requirement)
        db.session.commit()
        flash('需求删除成功！', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'删除失败: {str(e)}', 'danger')
    
    # 对于AJAX请求，返回JSON响应
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    
    return redirect(url_for('requirement.index'))
