from flask import Blueprint, render_template, request, flash, redirect, url_for
from utils.db import db
from models.department.department import Department
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
from utils.pagination import get_pagination_params
import logging

# 定义蓝图
department_bp = Blueprint(
    'department',
    __name__,
    url_prefix='/department',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/department/static'
)

# 导入操作模块
from . import department_operations


# 部门列表页（含筛选+分页）
@department_bp.route('/', methods=['GET'])
@login_required
@require_permission('department.view')
def index():
    try:
        # 获取筛选参数
        company = request.args.get('company', '').strip()
        keyword = request.args.get('keyword', '').strip()
        status = request.args.get('status', '').strip()

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # 参数校验
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 从部门主表去重获取公司列表
        companies = Department.get_all_companies()
        statuses = Department.get_all_statuses()

        # 构建查询
        query = Department.query.order_by(Department.id.desc())

        if company:
            if company == '__none__':
                query = query.filter(Department.company.is_(None))
            else:
                query = query.filter(Department.company == company)
        if status:
            query = query.filter(Department.status == status)
        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    Department.name.ilike(search_filter),
                    Department.description.ilike(search_filter)
                )
            )

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        departments = pagination.items

        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='records',
            action="访问部门管理页面",
            result="成功"
        )
        logging.info(f"加载部门管理页面，当前用户ID: {current_user.id}")

        return render_template(
            'department_manage/department_manage.html',
            title="部门管理",
            # 部门数据
            departments=departments,
            # 分页参数
            **get_pagination_params(pagination),
            # 筛选配置
            companies=companies,
            statuses=statuses,
            # 当前筛选条件（回显）
            current_company=company,
            current_status=status,
            keyword=keyword
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='records',
            action=f"加载部门管理页面失败: {str(e)}",
            result="失败"
        )
        flash('加载部门数据失败，请联系管理员', 'danger')
        logging.error(f"加载部门管理页面失败: {str(e)}")
        return render_template(
            'department_manage/department_manage.html',
            title="部门管理",
            departments=[],
            total=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            companies=[],
            statuses=['正常', '停用'],
            current_company='',
            current_status='',
            keyword=''
        )


# 新增部门页面
@department_bp.route('/add', methods=['GET'])
@login_required
@require_permission('department.create')
def add_page():
    try:
        companies = Department.get_all_companies()
        return render_template(
            'department_manage/department_add.html',
            title="新增部门",
            companies=companies
        )
    except Exception as e:
        logging.error(f"加载新增部门页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('department.index'))


# 编辑部门页面
@department_bp.route('/edit/<int:id>', methods=['GET'])
@login_required
@require_permission('department.edit')
def edit_page(id):
    try:
        department = Department.query.get_or_404(id)
        companies = Department.get_all_companies()
        return render_template(
            'department_manage/department_edit.html',
            title=f"编辑部门 - {department.name}",
            department=department,
            companies=companies
        )
    except Exception as e:
        logging.error(f"加载编辑部门页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('department.index'))