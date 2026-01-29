from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_, and_, func
from models import (db, Requirement, RequirementHistory, RequirementStatus, 
                   Priority, User, Project, Module, Category)
import pandas as pd
from io import BytesIO
from typing import Dict, Optional

# 定义北京时区
BEIJING_TZ = timezone(timedelta(hours=8))

class RequirementService:
    """需求业务逻辑服务"""
    
    @staticmethod
    def create_requirement(data: Dict, user_id: int) -> Requirement:
        """创建需求"""
        # 生成需求编号
        data['code'] = RequirementService.generate_requirement_code(data.get('project_id'))
        data['creator_id'] = user_id
        
        requirement = Requirement(**data)
        db.session.add(requirement)
        
        # 记录历史
        RequirementService.add_history(
            requirement_id=requirement.id,
            user_id=user_id,
            action='create',
            comment='创建需求'
        )
        
        db.session.commit()
        return requirement
    
    @staticmethod
    def update_requirement(requirement_id: int, data: Dict, user_id: int) -> Requirement:
        """更新需求"""
        requirement = Requirement.query.get_or_404(requirement_id)
        
        # 记录变更
        for field, new_value in data.items():
            old_value = getattr(requirement, field)
            if old_value != new_value:
                RequirementService.add_history(
                    requirement_id=requirement_id,
                    user_id=user_id,
                    action='update',
                    field_name=field,
                    old_value=str(old_value),
                    new_value=str(new_value)
                )
                setattr(requirement, field, new_value)
        
        requirement.updated_at = datetime.now(BEIJING_TZ)
        db.session.commit()
        return requirement
    
    @staticmethod
    def change_status(requirement_id: int, new_status: str, user_id: int, comment: str = None) -> Requirement:
        """更改需求状态"""
        requirement = Requirement.query.get_or_404(requirement_id)
        old_status = requirement.status
        
        # 状态转换验证
        if not RequirementService.validate_status_transition(old_status, new_status):
            raise ValueError(f"不允许从 {old_status} 转换到 {new_status}")
        
        requirement.status = new_status
        
        # 记录状态变更
        RequirementService.add_history(
            requirement_id=requirement_id,
            user_id=user_id,
            action='status_change',
            field_name='status',
            old_value=old_status,
            new_value=new_status,
            comment=comment
        )
        
        db.session.commit()
        return requirement
    
    @staticmethod
    def validate_status_transition(old_status: str, new_status: str) -> bool:
        """验证状态转换是否合法"""
        allowed_transitions = {
            '草稿': ['已提交', 'Cancelled'],
            '已提交': ['评审中', '已拒绝', '草稿'],  # 允许回到草稿
            '评审中': ['已批准', '已拒绝', '已提交'],
            '已批准': ['In progress', 'On Hold', '评审中'],  # 允许回到评审
            'In progress': ['测试中', 'On Hold', '已批准'],  # 允许回到已批准
            '测试中': ['Completed', 'In progress'],
            'On Hold': ['In progress', 'Cancelled', '已批准'],
            'Completed': ['测试中'],  # 允许重新测试
            '已拒绝': ['草稿', '已提交', '评审中'],  # 允许重新激活
            'Cancelled': ['草稿']   # 允许重新激活为草稿
        }
        
        # 如果是相同状态，允许转换（用于更新备注）
        if old_status == new_status:
            return True
            
        return new_status in allowed_transitions.get(old_status, [])
    
    @staticmethod
    def generate_requirement_code(project_id: Optional[int] = None) -> str:
        """生成需求编号"""
        prefix = 'REQ'
        if project_id:
            project = Project.query.get(project_id)
            if project:
                prefix = project.code
        
        # 获取当前最大编号
        last_req = Requirement.query.filter(
            Requirement.code.like(f'{prefix}-%')
        ).order_by(Requirement.id.desc()).first()
        
        if last_req:
            last_num = int(last_req.code.split('-')[-1])
            new_num = last_num + 1
        else:
            new_num = 1
        
        return f"{prefix}-{datetime.now(BEIJING_TZ).strftime('%Y%m')}-{new_num:04d}"
    
    @staticmethod
    def search_requirements(filters: Dict, page: int = 1, per_page: int = 20, paginate: bool = True):
        """搜索需求
        
        Args:
            filters: 过滤条件字典
            page: 页码，从1开始
            per_page: 每页显示数量
            paginate: 是否返回分页对象，False时返回所有结果的列表
            
        Returns:
            如果paginate=True，返回Flask-SQLAlchemy的Pagination对象
            如果paginate=False，返回Requirements List
        """
        query = Requirement.query
        
        # 关键词搜索
        if filters.get('keyword'):
            keyword = f"%{filters['keyword']}%"
            query = query.filter(
                or_(
                    Requirement.title.like(keyword),
                    Requirement.description.like(keyword),
                    Requirement.code.like(keyword)
                )
            )
        
        # 其他过滤条件
        if filters.get('type'):
            query = query.filter_by(type=filters['type'])
        if filters.get('status'):
            query = query.filter_by(status=filters['status'])
        if filters.get('priority'):
            query = query.filter_by(priority=filters['priority'])
        if filters.get('project_id'):
            query = query.filter_by(project_id=filters['project_id'])
        # 新增：支持多个项目ID过滤
        if filters.get('project_ids') is not None:
            project_ids = filters['project_ids']
            if project_ids:  # 如果列表不为空
                query = query.filter(Requirement.project_id.in_(project_ids))
            else:  # 如果列表为空，不返回任何结果
                query = query.filter(Requirement.project_id.is_(None))
        if filters.get('module_id'):
            query = query.filter_by(module_id=filters['module_id'])
        if filters.get('assignee_id'):
            query = query.filter_by(assignee_id=filters['assignee_id'])
        
        # 日期范围
        if filters.get('start_date'):
            query = query.filter(Requirement.created_at >= filters['start_date'])
        if filters.get('end_date'):
            query = query.filter(Requirement.created_at <= filters['end_date'])
        
        # 添加默认排序：按创建时间倒序
        query = query.order_by(Requirement.created_at.desc())
        
        # 根据参数决定是否分页
        if paginate:
            return query.paginate(
                page=page,
                per_page=per_page,
                error_out=False  # 避免页码超出范围时抛出异常
            )
        else:
            return query.all()
    
    @staticmethod
    def calculate_statistics(project_id: Optional[int] = None) -> Dict:
        """计算需求统计信息"""
        query = Requirement.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        
        total = query.count()
        
        # 按状态统计 - 使用实际数据库中的值
        status_stats = {}
        if project_id:
            status_counts = db.session.query(
                Requirement.status,
                func.count(Requirement.id)
            ).filter_by(project_id=project_id).group_by(Requirement.status).all()
        else:
            status_counts = db.session.query(
                Requirement.status,
                func.count(Requirement.id)
            ).group_by(Requirement.status).all()
        
        for status, count in status_counts:
            status_stats[status] = count
        
        # 按优先级统计 - 使用实际数据库中的值
        priority_stats = {}
        if project_id:
            priority_counts = db.session.query(
                Requirement.priority,
                func.count(Requirement.id)
            ).filter_by(project_id=project_id).group_by(Requirement.priority).all()
        else:
            priority_counts = db.session.query(
                Requirement.priority,
                func.count(Requirement.id)
            ).group_by(Requirement.priority).all()
        
        for priority, count in priority_counts:
            priority_stats[priority] = count
        
        # 按类型统计 - 使用实际数据库中的值
        if project_id:
            type_stats = db.session.query(
                Requirement.type,
                func.count(Requirement.id)
            ).filter_by(project_id=project_id).group_by(Requirement.type).all()
        else:
            type_stats = db.session.query(
                Requirement.type,
                func.count(Requirement.id)
            ).group_by(Requirement.type).all()
        
        # 完成率 - 只使用中文状态值
        completed_statuses = [RequirementStatus.COMPLETED.value]
        completed = 0
        for status in completed_statuses:
            completed += query.filter_by(status=status).count()
        
        completion_rate = (completed / total * 100) if total > 0 else 0
        
        # Overdue需求 - 排除Completed的需求
        overdue_query = query.filter(
            and_(
                Requirement.due_date < datetime.now(BEIJING_TZ).date(),
                ~Requirement.status.in_(completed_statuses)
            )
        )
        overdue = overdue_query.count()
        
        return {
            'total': total,
            'status_stats': status_stats,
            'priority_stats': priority_stats,
            'type_stats': dict(type_stats),
            'completion_rate': round(completion_rate, 2),
            'overdue': overdue
        }
    
    @staticmethod
    def export_requirements(requirements: List[Requirement]) -> BytesIO:
        """导出需求到Excel"""
        data = []
        for req in requirements:
            data.append({
                '需求编号': req.code,
                '标题': req.title,
                '描述': req.description,
                '类型': req.type,
                '状态': req.status,
                '优先级': req.priority,
                '负责人': req.assignee.full_name if req.assignee else '',
                '创建时间': req.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                '截止日期': req.due_date.strftime('%Y-%m-%d') if req.due_date else '',
            })
        
        df = pd.DataFrame(data)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Requirements List', index=False)
        output.seek(0)
        
        return output
    
    @staticmethod
    def import_requirements(file, project_id: int, user_id: int) -> Tuple[int, List[str]]:
        """从Excel导入需求"""
        df = pd.read_excel(file)
        success_count = 0
        errors = []
        
        required_columns = ['标题', '描述', '类型', '优先级']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return 0, [f"缺少必需列: {', '.join(missing_columns)}"]
        
        for index, row in df.iterrows():
            try:
                data = {
                    'title': row['标题'],
                    'description': row['描述'],
                    'type': row.get('类型', RequirementType.FUNCTIONAL.value),
                    'priority': row.get('优先级', Priority.MEDIUM.value),
                    'project_id': project_id,
                    'creator_id': user_id
                }
                
                RequirementService.create_requirement(data, user_id)
                success_count += 1
            except Exception as e:
                errors.append(f"第{index + 2}行导入失败: {str(e)}")
        
        return success_count, errors
    
    @staticmethod
    def add_history(requirement_id: int, user_id: int, action: str, 
                   field_name: str = None, old_value: str = None, 
                   new_value: str = None, comment: str = None):
        """添加需求历史记录"""
        history = RequirementHistory(
            requirement_id=requirement_id,
            user_id=user_id,
            action=action,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            comment=comment
        )
        db.session.add(history)
    
    @staticmethod
    def create_baseline(project_id: int, name: str, version: str, user_id: int) -> 'Baseline':
        """创建基线版本"""
        from models import Baseline
        import json
        
        # 获取项目所有需求的快照
        requirements = Requirement.query.filter_by(project_id=project_id).all()
        snapshot = [req.to_dict() for req in requirements]
        
        baseline = Baseline(
            name=name,
            version=version,
            project_id=project_id,
            requirements_snapshot=json.dumps(snapshot, ensure_ascii=False),
            created_by=user_id
        )
        db.session.add(baseline)
        db.session.commit()
        
        return baseline
    
    @staticmethod
    def analyze_impact(requirement_id: int) -> Dict:
        """分析需求影响"""
        requirement = Requirement.query.get_or_404(requirement_id)
        
        # 获取依赖此需求的其他需求
        dependent_requirements = requirement.dependents.all()
        
        # 获取相关的测试用例
        test_cases = requirement.test_cases
        
        # 计算影响范围
        impact = {
            'requirement': requirement.to_dict(),
            'affected_requirements': [req.to_dict() for req in dependent_requirements],
            'affected_test_cases': len(test_cases),
            'risk_level': '高' if len(dependent_requirements) > 5 else '中' if len(dependent_requirements) > 2 else '低'
        }
        
        return impact
