"""
分页工具模块
提供统一的分页参数提取和模板变量构建函数，确保前后端分页参数命名一致。

使用方式：
    # 方式1：从SQLAlchemy分页对象提取（最常用）
    from utils.pagination import get_pagination_params

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    pagination_vars = get_pagination_params(pagination)

    return render_template(
        'your_template.html',
        your_data=data,
        **pagination_vars,          # 展开: total, current_page, per_page, total_pages
        # 其他业务参数...
    )

    # 方式2：手动构建分页参数（用于手动分页场景，如列表切片）
    from utils.pagination import build_pagination_params

    pagination_vars = build_pagination_params(
        total=total_count,
        current_page=page,
        per_page=per_page,
        total_pages=total_pages
    )

    return render_template(
        'your_template.html',
        your_data=data,
        **pagination_vars,
        # 其他业务参数...
    )
"""


def get_pagination_params(pagination, per_page_override=None):
    """
    从SQLAlchemy分页对象提取统一的分页参数字典。

    Args:
        pagination: SQLAlchemy Pagination对象（query.paginate()的返回值）
        per_page_override: 可选，覆盖per_page值（用于room模块使用page_size变量的场景）

    Returns:
        dict: 包含以下键的字典，可直接通过 **pagination_vars 展开到render_template：
            - total (int): 总记录数
            - current_page (int): 当前页码
            - per_page (int): 每页记录数
            - total_pages (int): 总页数

    前端PaginationManager对应的参数映射：
        total       → options.total
        current_page → options.currentPage
        per_page    → options.pageSize
        total_pages → options.totalPages
    """
    return {
        'total': pagination.total,
        'current_page': pagination.page,
        'per_page': per_page_override if per_page_override is not None else pagination.per_page,
        'total_pages': pagination.pages,
    }


def build_pagination_params(total, current_page, per_page, total_pages=None):
    """
    手动构建统一的分页参数字典（用于非SQLAlchemy分页场景）。

    Args:
        total (int): 总记录数
        current_page (int): 当前页码
        per_page (int): 每页记录数
        total_pages (int, optional): 总页数。如果不提供，则自动计算。

    Returns:
        dict: 包含以下键的字典，可直接通过 **pagination_vars 展开到render_template：
            - total (int): 总记录数
            - current_page (int): 当前页码
            - per_page (int): 每页记录数
            - total_pages (int): 总页数
    """
    if total_pages is None:
        total_pages = (total + per_page - 1) // per_page if total > 0 else 0
    return {
        'total': total,
        'current_page': current_page,
        'per_page': per_page,
        'total_pages': total_pages,
    }