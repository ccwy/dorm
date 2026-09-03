
import os
import time
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, jsonify, send_file
from flask_login import login_required, current_user
from utils.auth import require_permission
import logging
import sys
import shutil

# 定义蓝图
file_sharing_bp = Blueprint(
    'file_sharing', 
    __name__, 
    url_prefix='/file_sharing'
)


# 根据环境获取基础目录
if os.environ.get('DOCKER_ENV', 'false').lower() == 'true':  # 优先检查Docker环境
    BASE_DATA_PATH = '/data'  # Docker环境 - 使用外部数据卷路径
elif getattr(sys, 'frozen', False):
    # 打包环境 - 文件存储在应用程序所在目录的data下
    app_dir = os.path.dirname(sys.executable)
    BASE_DATA_PATH = os.path.join(app_dir, 'data')
else:
    # 开发环境 - 文件存储在项目根目录的data下
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    BASE_DATA_PATH = os.path.join(base_dir, 'data')

# 定义支持的根目录配置
supported_roots = {
    'file_sharing': {
        'name': '文件共享',
        'path': os.path.join(BASE_DATA_PATH, 'file_sharing')
    },
    'photo': {
        'name': '图片管理',
        'path': os.path.join(BASE_DATA_PATH, 'photo')
    },
    'backups': {
        'name': '数据库备份',
        'path': os.path.join(BASE_DATA_PATH, 'backups')
    },
    'logs': {
        'name': '日志文件',
        'path': os.path.join(BASE_DATA_PATH, 'logs')
    }
}

# 获取当前选择的根目录
def get_current_root(root_type=None):
    # 调试日志
    logging.info(f'get_current_root调用: 传入的root_type={root_type}')
    
    # 如果提供了root_type参数，就使用它
    if root_type is None:
        # 否则从请求参数中获取根目录类型
        root_type = request.args.get('root', 'file_sharing')
        logging.info(f'从请求参数获取root_type: {root_type}')
    
    # 检查用户是否已登录并有权限访问非file_sharing目录
    if root_type != 'file_sharing':
        # 检查用户是否登录且是管理员
        if not (current_user.is_authenticated and current_user.has_permission('file_sharing.manage')):
            logging.warning(f'用户{current_user.id}尝试访问需要管理员权限的目录: {root_type}')
            # 非管理员只能访问file_sharing目录
            root_type = 'file_sharing'
    
    # 确保根目录类型有效
    if root_type not in supported_roots:
        logging.warning(f'无效的root_type: {root_type}, 默认为file_sharing')
        root_type = 'file_sharing'
    
    logging.info(f'最终使用的root_type: {root_type}, 对应路径: {supported_roots[root_type]["path"]}')
    return root_type, supported_roots[root_type]['path']

# 确保所有根目录都存在
for root in supported_roots.values():
    if not os.path.exists(root['path']):
        logging.info(f'创建目录: {root["path"]}')
        os.makedirs(root['path'])

# 获取文件大小的人类可读形式
def get_human_readable_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

# 获取指定路径下的文件和文件夹列表，支持搜索
def get_files_and_folders(path, root_path, search_query=None):
    items = []
    if not os.path.exists(path):
        return items
    
    # 先添加文件夹
    for item in os.listdir(path):
        # 过滤隐藏文件夹
        if item.startswith('.git') or item == '__pycache__' or item.startswith('.temp'):
            continue
            
        item_path = os.path.join(path, item)
        if os.path.isdir(item_path):
            # 如果有搜索查询，检查文件夹名是否匹配
            if search_query and search_query.lower() not in item.lower():
                continue
            
            # 计算相对路径（从根目录开始）
            rel_path = os.path.relpath(item_path, root_path).replace('\\', '/')
            
            items.append({
                'name': item,
                'path': item_path,
                'rel_path': rel_path,
                'is_folder': True,
                'size': '',
                'modified_time': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M:%S')
            })
    
    # 再添加文件
    for item in os.listdir(path):
        # 过滤以.开头的隐藏文件
        if item.startswith('.'):
            continue
            
        item_path = os.path.join(path, item)
        if os.path.isfile(item_path):
            # 如果有搜索查询，检查文件名是否匹配
            if search_query and search_query.lower() not in item.lower():
                continue
            
            # 计算相对路径（从根目录开始）
            rel_path = os.path.relpath(item_path, root_path).replace('\\', '/')
            
            items.append({
                'name': item,
                'path': item_path,
                'rel_path': rel_path,
                'is_folder': False,
                'size': get_human_readable_size(os.path.getsize(item_path)),
                'modified_time': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M:%S')
            })
    
    # 按名称排序，文件夹优先
    items.sort(key=lambda x: (not x['is_folder'], x['name'].lower()))
    
    return items

# 分页处理函数
def paginate_items(items, page, per_page):
    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    paginated_items = items[start_index:end_index]
    
    total_items = len(items)
    total_pages = (total_items + per_page - 1) // per_page
    
    return {
        'items': paginated_items,
        'total_items': total_items,
        'total_pages': total_pages,
        'current_page': page,
        'per_page': per_page,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_page': page - 1 if page > 1 else None,
        'next_page': page + 1 if page < total_pages else None
    }

# 文件管理主页
@file_sharing_bp.route('/', methods=['GET'])
@login_required
@require_permission('file_sharing.view')
def file_sharing():
    # 获取当前选择的根目录
    root_type = request.args.get('root', 'file_sharing')
    _, current_root_path = get_current_root(root_type)
    current_path = request.args.get('path', '')
    abs_path = os.path.join(current_root_path, current_path)
    
    # 安全检查：确保路径在当前根目录内
    if not os.path.abspath(abs_path).startswith(os.path.abspath(current_root_path)):
        flash('访问路径无效', 'error')
        logging.warning(f'用户 {current_user.id} 尝试访问无效路径: {abs_path}')
        return redirect(url_for('file_sharing.file_sharing', root=root_type))
    
    # 检查路径是否存在
    if not os.path.exists(abs_path):
        flash('当前路径不存在', 'error')
        logging.warning(f'用户 {current_user.id} 尝试访问不存在的路径: {abs_path}')
        return redirect(url_for('file_sharing.file_sharing', root=root_type))
    
    # 获取当前路径下的文件和文件夹
    items = get_files_and_folders(abs_path, current_root_path)
    
    # 生成面包屑导航
    breadcrumbs = []
    if current_path:
        # 统一使用正斜杠分割路径
        parts = current_path.replace('\\', '/').split('/')
        # 过滤空字符串（处理连续的斜杠或开头/结尾的斜杠）
        parts = [p for p in parts if p]
        
        current = ''
        for part in parts:
            if current:
                current = f"{current}/{part}"
            else:
                current = part
            breadcrumbs.append({
                'name': part,
                'path': current
            })
    
    # 搜索功能
    search_query = request.args.get('search', '')
    if search_query:
        # 递归搜索整个根目录下的所有文件和文件夹
        def recursive_search(root_dir, query):
            results = []
            try:
                for item in os.listdir(root_dir):
                    item_path = os.path.join(root_dir, item)
                    # 过滤隐藏文件和目录
                    if item.startswith('.') or item == '.git' or item == '__pycache__' or item.startswith('.temp'):
                        continue
                    
                    # 检查文件名是否匹配搜索查询
                    if query.lower() in item.lower():
                        # 计算相对路径（从根目录开始）
                        rel_path = os.path.relpath(item_path, current_root_path).replace('\\', '/')
                        is_folder = os.path.isdir(item_path)
                        
                        results.append({
                            'name': item,
                            'path': item_path,
                            'rel_path': rel_path,
                            'is_folder': is_folder,
                            'size': get_human_readable_size(os.path.getsize(item_path)) if not is_folder else '',
                            'modified_time': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M:%S')
                        })
                    
                    # 如果是目录，递归搜索
                    if os.path.isdir(item_path):
                        results.extend(recursive_search(item_path, query))
            except PermissionError:
                # 处理没有权限访问的目录
                pass
            
            # 按名称排序，文件夹优先
            results.sort(key=lambda x: (not x['is_folder'], x['name'].lower()))
            
            return results
        
        # 执行递归搜索
        items = recursive_search(current_root_path, search_query)
    
    # 分页功能
    try:
        page = int(request.args.get('page', 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1
    
    try:
        per_page = int(request.args.get('per_page', 20))
        if per_page not in [10, 20, 50, 100]:
            per_page = 20
    except ValueError:
        per_page = 20
    
    pagination = paginate_items(items, page, per_page)
    
    # 确保root_type有效，防止KeyError
    if root_type not in supported_roots:
        root_type = 'file_sharing'
    
    # 根据用户权限过滤显示的根目录选项
    if current_user.is_authenticated and current_user.has_permission('file_sharing.manage'):
        # 管理员可以看到所有根目录
        display_roots = supported_roots
    else:
        # 非管理员只能看到文件共享目录
        display_roots = {'file_sharing': supported_roots['file_sharing']}
        # 确保非管理员用户总是使用file_sharing目录
        if root_type != 'file_sharing':
            root_type = 'file_sharing'
            current_root_type = 'file_sharing'
    logging.info(f'用户 {current_user.id} 访问路径: {abs_path}')
    return render_template('file_sharing/file_sharing.html', 
                          title=supported_roots[root_type]['name'],
                          items=pagination['items'], 
                          pagination=pagination,
                          current_path=current_path, 
                          breadcrumbs=breadcrumbs, 
                          search_query=search_query, 
                          os=os, 
                          current_root_type=root_type,
                          supported_roots=display_roots)

# 创建新文件夹
@file_sharing_bp.route('/create_folder', methods=['POST'])
@login_required
@require_permission('file_sharing.manage')
def create_folder():
    current_path = request.form.get('current_path', '')
    folder_name = request.form.get('folder_name', '').strip()
    # 从表单或URL参数获取root_type，不设置默认值
    root_type = request.form.get('root_type') or request.args.get('root')
    
    # 确保root_type有效
    if not root_type or root_type not in supported_roots:
        logging.error(f'无效或缺失的root_type: {root_type}，创建文件夹操作被拒绝')
        flash('操作失败：无效或缺失的根目录类型', 'error')
        return redirect(url_for('file_sharing.file_sharing', path=current_path))
    
    if not folder_name:
        flash('文件夹名称不能为空', 'error')
        logging.warning(f'用户 {current_user.id} 尝试创建空文件夹')
        return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))
    
    # 检查文件夹名称是否合法
    invalid_chars = '<>:"/\\|?*'
    if any(char in folder_name for char in invalid_chars):
        flash('文件夹名称包含非法字符', 'error')
        logging.warning(f'用户 {current_user.id} 尝试创建包含非法字符的文件夹: {folder_name}')
        return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))
    
    # 获取当前选择的根目录
    _, current_root_path = get_current_root(root_type)
    new_folder_path = os.path.join(current_root_path, current_path, folder_name)
    
    # 检查文件夹是否已存在
    if os.path.exists(new_folder_path):
        flash('文件夹已存在', 'error')
        logging.warning(f'用户 {current_user.id} 尝试创建已存在的文件夹: {os.path.join(current_path, folder_name)}')
        return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))
    
    try:
        os.makedirs(new_folder_path)
        flash(f'文件夹 "{folder_name}" 创建成功', 'success')
        logging.info(f'用户 {current_user.id} 创建文件夹: {os.path.join(current_path, folder_name)}')
    except Exception as e:
        flash(f'创建文件夹失败: {str(e)}', 'error')
        logging.error(f'用户 {current_user.id} 创建文件夹失败: {str(e)}')
    
    return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))

# 上传文件或文件夹
@file_sharing_bp.route('/upload', methods=['POST'])
@login_required
@require_permission('file_sharing.manage')
def upload_file():
    current_path = request.form.get('current_path', '')
    # 从表单或URL参数获取root_type，不设置默认值
    root_type = request.form.get('root_type') or request.args.get('root')
    
    # 检查用户是否有上传权限
    if not current_user.has_permission('file_sharing.manage'):
        flash('操作失败：需要上传权限', 'error')
        logging.warning(f'用户 {current_user.id} 尝试执行需要上传权限的操作')
        return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))
    
    # 确保root_type有效
    if not root_type or root_type not in supported_roots:
        logging.error(f'无效或缺失的root_type: {root_type}，上传操作被拒绝')
        flash('操作失败：无效或缺失的根目录类型', 'error')
        return redirect(url_for('file_sharing.file_sharing', path=current_path))
    
    # 获取当前选择的根目录
    _, current_root_path = get_current_root(root_type)
    target_path = os.path.join(current_root_path, current_path)
    
    # 确保目标路径存在
    if not os.path.exists(target_path):
        logging.info(f'用户 {current_user.id} 创建目录: {target_path}')
        os.makedirs(target_path)
    
    # 检查是否有文件上传
    has_files = False
    success_count = 0
    error_count = 0
    
    # 首先检查是否有文件夹上传
    if 'folder' in request.files and request.files['folder'].filename != '':
        folder_file = request.files['folder']
        # 对于文件夹上传，浏览器会发送多个文件，每个文件包含webkitRelativePath属性
        # 但是在Flask中，我们需要通过getlist来获取所有文件
        # 注意：这里的处理逻辑需要与前端配合，前端需要使用FormData正确发送文件夹中的所有文件
        # 由于前端使用了FormData直接提交，这里我们需要检查是否有多个文件包含路径信息
        files = request.files.getlist('folder')
        if files:
            has_files = True
            for file in files:
                try:
                    # 获取相对路径
                    relative_path = getattr(file, 'webkitRelativePath', file.filename)
                    # 构建完整的目标文件路径
                    file_target_path = os.path.join(target_path, relative_path)
                    # 确保目录存在
                    file_dir = os.path.dirname(file_target_path)
                    if not os.path.exists(file_dir):
                        os.makedirs(file_dir)
                    # 保存文件
                    file.save(file_target_path)
                    success_count += 1
                    logging.info(f'用户 {current_user.id} 上传文件: {os.path.join(current_path, relative_path)}')
                except Exception as e:
                    error_count += 1
                    logging.error(f'用户 {current_user.id} 上传文件 {getattr(file, "webkitRelativePath", file.filename)} 失败: {str(e)}')
    
    # 如果没有文件夹上传，检查普通文件上传
    if not has_files and 'files' in request.files:
        files = request.files.getlist('files')
        if files and files[0].filename != '':
            has_files = True
            for file in files:
                if file:
                    filename = file.filename
                    try:
                        file.save(os.path.join(target_path, filename))
                        success_count += 1
                        logging.info(f'用户 {current_user.id} 上传文件: {os.path.join(current_path, filename)}')
                    except Exception as e:
                        error_count += 1
                        logging.error(f'用户 {current_user.id} 上传文件 {filename} 失败: {str(e)}')
    
    # 检查是否有文件被上传
    if not has_files:
        flash('未选择文件', 'error')
        logging.info(f'用户 {current_user.id} 未选择文件')
    else:
        if success_count > 0:
            flash(f'成功上传 {success_count} 个文件', 'success')
            logging.info(f'用户 {current_user.id} 成功上传 {success_count} 个文件')
        if error_count > 0:
            flash(f'有 {error_count} 个文件上传失败', 'error')
            logging.error(f'用户 {current_user.id} 有 {error_count} 个文件上传失败')
    
    return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))

# 下载文件
@file_sharing_bp.route('/download/<path:file_path>')
@login_required
@require_permission('file_sharing.view')
def download_file(file_path):
    # 从URL参数获取root_type，不设置默认值
    root_type = request.args.get('root')
    
    # 确保root_type有效
    if not root_type or root_type not in supported_roots:
        logging.error(f'无效或缺失的root_type: {root_type}，下载操作被拒绝')
        flash('操作失败：无效或缺失的根目录类型', 'error')
        return redirect(url_for('file_sharing.file_sharing'))
    
    # 获取当前选择的根目录
    _, current_root_path = get_current_root(root_type)
    abs_path = os.path.join(current_root_path, file_path)
    
    # 安全检查
    if not os.path.abspath(abs_path).startswith(os.path.abspath(current_root_path)) or not os.path.isfile(abs_path):
        flash('文件不存在或访问受限', 'error')
        logging.error(f'用户 {current_user.id} 尝试下载不存在或受限的文件: {file_path}')
        return redirect(url_for('file_sharing.file_sharing', root=root_type))
    
    directory = os.path.dirname(abs_path)
    filename = os.path.basename(abs_path)
    
    logging.info(f'用户 {current_user.id} 下载文件: {file_path}')
    
    return send_from_directory(directory, filename, as_attachment=True)

# 删除文件或文件夹
@file_sharing_bp.route('/delete', methods=['POST'])
@login_required
@require_permission('file_sharing.delete')
def delete_file():
    file_paths = request.form.getlist('file_paths[]')
    current_path = request.form.get('current_path', '')
    
    # 从表单或URL参数获取root_type，不设置默认值
    root_type = request.form.get('root_type') or request.args.get('root')
    
    # 检查用户是否有删除权限
    if not current_user.has_permission('file_sharing.delete'):
        flash('操作失败：需要删除权限', 'error')
        logging.warning(f'用户 {current_user.id} 尝试执行需要删除权限的操作')
        return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))
    
    # 调试日志，记录接收到的参数
    logging.info(f'删除操作请求参数: root_type={root_type}, file_paths={file_paths}, current_path={current_path}')
    
    # 确保root_type有效
    if not root_type or root_type not in supported_roots:
        logging.error(f'无效或缺失的root_type: {root_type}，删除操作被拒绝')
        flash('操作失败：无效或缺失的根目录类型', 'error')
        return redirect(url_for('file_sharing.file_sharing', path=current_path))
    
    # 获取当前选择的根目录
    _, current_root_path = get_current_root(root_type)
    logging.info(f'删除操作使用的根目录路径: {current_root_path}')
    
    if not file_paths:
        flash('未选择要删除的项', 'error')
        logging.info(f'用户 {current_user.id} 未选择要删除的项')
        return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))
    
    success_count = 0
    error_count = 0
    
    for file_path in file_paths:
        abs_path = os.path.join(current_root_path, file_path)
        
        # 安全检查
        if not os.path.abspath(abs_path).startswith(os.path.abspath(current_root_path)):
            error_count += 1
            logging.warning(f'路径安全检查失败: {abs_path}不在根目录{current_root_path}内')
            continue
        
        # 检查文件是否存在
        if not os.path.exists(abs_path):
            error_count += 1
            logging.warning(f'文件或文件夹不存在: {abs_path}')
            continue
        
        try:
            # 检查文件权限
            if not os.access(abs_path, os.W_OK):
                logging.warning(f'没有写权限删除: {abs_path}')
                
            if os.path.isfile(abs_path):
                os.remove(abs_path)
                # 验证删除是否成功
                if not os.path.exists(abs_path):
                    success_count += 1
                    logging.info(f'用户 {current_user.id} 成功删除文件: {abs_path}')
                else:
                    error_count += 1
                    logging.error(f'用户 {current_user.id} 文件删除标记为成功，但实际仍存在: {abs_path}')
            elif os.path.isdir(abs_path):

                shutil.rmtree(abs_path)
                # 验证删除是否成功
                if not os.path.exists(abs_path):
                    success_count += 1
                    logging.info(f'用户 {current_user.id} 成功删除文件夹: {abs_path}')
                else:
                    error_count += 1
                    logging.error(f'用户 {current_user.id} 文件夹删除标记为成功，但实际仍存在: {abs_path}')
        except PermissionError as pe:
            error_count += 1
            logging.error(f'删除权限错误 {abs_path}: {str(pe)}')
        except OSError as oe:
            error_count += 1
            logging.error(f'删除操作系统错误 {abs_path}: {str(oe)}')
        except Exception as e:
            error_count += 1
            logging.error(f'删除未知错误 {abs_path}: {str(e)}')
    
    if success_count > 0:
        flash(f'成功删除 {success_count} 项', 'success')
        logging.info(f'用户 {current_user.id} 删除操作完成: 成功 {success_count} 项, 失败 {error_count} 项')
    if error_count > 0:
        flash(f'有 {error_count} 个项删除失败，请查看日志了解详情', 'error')
        logging.error(f'用户 {current_user.id} 删除操作完成: 成功 {success_count} 项, 失败 {error_count} 项')
    
    # 重定向回文件列表页面，确保刷新当前视图
    return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type, _=int(time.time())))

# 分块上传文件
@file_sharing_bp.route('/upload_chunk', methods=['POST'])
@login_required
@require_permission('file_sharing.manage')
def upload_chunk():
    # 从URL参数获取root_type
    root_type = request.args.get('root')
    
    # 检查用户是否有上传权限
    if not current_user.has_permission('file_sharing.manage'):
        logging.warning(f'用户 {current_user.id} 尝试执行需要上传权限的分块上传操作')
        return jsonify({'success': False, 'message': '操作失败：需要上传权限'}), 403
    
    # 确保root_type有效
    if not root_type or root_type not in supported_roots:
        logging.error(f'无效或缺失的root_type: {root_type}，分块上传操作被拒绝')
        return jsonify({'success': False, 'message': '无效或缺失的根目录类型'}), 400
    
    # 获取文件信息
    file_id = request.form.get('fileId')
    chunk_index = request.form.get('chunkIndex')
    current_path = request.form.get('current_path', '')
    
    # 验证必要参数
    if not file_id or not chunk_index or 'file' not in request.files:
        logging.error(f'分块上传缺少必要参数: fileId={file_id}, chunkIndex={chunk_index}')
        return jsonify({'success': False, 'message': '缺少必要参数'}), 400
    
    # 获取当前选择的根目录
    _, current_root_path = get_current_root(root_type)
    logging.info(f'用户 {current_user.id} 开始分块上传文件: {file_id} 块 {chunk_index}')
    # 创建临时目录存储分块
    temp_dir = os.path.join(current_root_path, '.temp', file_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    # 保存文件块
    chunk_file = request.files['file']
    chunk_path = os.path.join(temp_dir, f'chunk_{chunk_index}')
    
    try:
        chunk_file.save(chunk_path)
        logging.info(f'用户 {current_user.id} 成功上传文件块: {file_id} 块 {chunk_index} 到 {chunk_path}')
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f'用户 {current_user.id} 上传文件块失败: {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 500

# 合并文件块
@file_sharing_bp.route('/merge_chunks', methods=['POST'])
@login_required
@require_permission('file_sharing.manage')
def merge_chunks():
    # 从URL参数获取root_type
    root_type = request.args.get('root')
    
    # 检查用户是否有上传权限
    if not current_user.has_permission('file_sharing.manage'):
        logging.warning(f'用户 {current_user.id} 尝试执行需要上传权限的合并文件块操作')
        return jsonify({'success': False, 'message': '操作失败：需要上传权限'}), 403
    
    # 确保root_type有效
    if not root_type or root_type not in supported_roots:
        logging.error(f'无效或缺失的root_type: {root_type}，合并文件块操作被拒绝')
        return jsonify({'success': False, 'message': '无效或缺失的根目录类型'}), 400
    
    # 获取文件信息
    file_id = request.form.get('fileId')
    file_name = request.form.get('fileName')
    current_path = request.form.get('current_path', '')
    
    # 验证必要参数
    if not file_id or not file_name:
        logging.error(f'合并文件块缺少必要参数: fileId={file_id}, fileName={file_name}')
        return jsonify({'success': False, 'message': '缺少必要参数'}), 400
    
    # 获取当前选择的根目录
    _, current_root_path = get_current_root(root_type)
    logging.info(f'用户 {current_user.id} 合并文件块: {file_id} 到 {os.path.join(current_path, file_name)}')
    # 构建目标路径
    target_path = os.path.join(current_root_path, current_path)
    os.makedirs(target_path, exist_ok=True)
    
    # 检查是否有相对路径信息
    is_folder = request.form.get('is_folder', 'false').lower() == 'true'
    webkit_relative_path = request.form.get('webkit_relative_path', '')
    
    # 构建完整文件路径
    if is_folder and webkit_relative_path:
        # 对于文件夹内的文件，使用相对路径
        full_file_path = os.path.join(target_path, webkit_relative_path)
        # 确保目录存在
        os.makedirs(os.path.dirname(full_file_path), exist_ok=True)
    else:
        full_file_path = os.path.join(target_path, file_name)
    
    # 构建临时目录路径
    temp_dir = os.path.join(current_root_path, '.temp', file_id)
    
    try:
        # 确保临时目录存在
        if not os.path.exists(temp_dir):
            logging.error(f'临时目录不存在: {temp_dir}')
            return jsonify({'success': False, 'message': '临时目录不存在'}), 404
        
        # 获取所有文件块并按索引排序
        chunk_files = sorted(os.listdir(temp_dir), key=lambda x: int(x.split('_')[1]))
        logging.info(f'用户 {current_user.id} 开始合并文件块: {file_id} 共 {len(chunk_files)} 个块')
        
        # 合并文件块
        with open(full_file_path, 'wb') as outfile:
            for chunk_file in chunk_files:
                chunk_path = os.path.join(temp_dir, chunk_file)
                with open(chunk_path, 'rb') as infile:
                    outfile.write(infile.read())

        logging.info(f'用户 {current_user.id} 成功合并文件: {os.path.join(current_path, file_name)}')
        # 删除临时目录和文件块
        shutil.rmtree(temp_dir)
        logging.info(f'用户 {current_user.id} 成功删除临时目录: {temp_dir}')
        
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f'用户 {current_user.id} 合并文件失败: {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 500

# 重命名文件或文件夹
@file_sharing_bp.route('/rename', methods=['POST'])
@login_required
@require_permission('file_sharing.manage')
def rename_file():
    current_path = request.form.get('current_path', '')
    old_name = request.form.get('old_name', '')
    new_name = request.form.get('new_name', '').strip()
    # 从表单或URL参数获取root_type，不设置默认值
    root_type = request.form.get('root_type') or request.args.get('root')
    
    # 检查用户是否有管理权限
    if not current_user.has_permission('file_sharing.manage'):
        flash('操作失败：需要管理权限', 'error')
        logging.warning(f'用户 {current_user.id} 尝试执行需要管理权限的重命名操作')
        return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))
    
    # 确保root_type有效
    if not root_type or root_type not in supported_roots:
        logging.error(f'无效或缺失的root_type: {root_type}，重命名操作被拒绝')
        flash('操作失败：无效或缺失的根目录类型', 'error')
        return redirect(url_for('file_sharing.file_sharing', path=current_path))
    
    # 获取当前选择的根目录
    _, current_root_path = get_current_root(root_type)
    
    if not old_name or not new_name:
        flash('名称不能为空', 'error')
        logging.error(f'用户 {current_user.id} 重命名操作失败: 名称不能为空')
        return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))
    
    if old_name == new_name:
        return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))
    
    # 检查新名称是否合法
    invalid_chars = '<>:"/\\|?*'
    if any(char in new_name for char in invalid_chars):
        flash('名称包含非法字符', 'error')
        logging.error(f'用户 {current_user.id} 重命名操作失败: 名称包含非法字符 {new_name}')
        return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))
    
    old_path = os.path.join(current_root_path, current_path, old_name)
    new_path = os.path.join(current_root_path, current_path, new_name)
    
    # 安全检查
    if not os.path.abspath(old_path).startswith(os.path.abspath(current_root_path)) or not os.path.exists(old_path):
        flash('文件或文件夹不存在', 'error')
        logging.error(f'用户 {current_user.id} 重命名操作失败: 文件或文件夹不存在 {old_path}')
        return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))
    
    # 检查新名称是否已存在
    if os.path.exists(new_path):
        flash('名称已存在', 'error')
        logging.error(f'用户 {current_user.id} 重命名操作失败: 名称已存在 {new_path}')
        return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))
    
    try:
        os.rename(old_path, new_path)
        flash(f'重命名成功: {os.path.join(current_path, old_name)} -> {os.path.join(current_path, new_name)}', 'success')
        logging.info(f'用户 {current_user.id} 重命名: {os.path.join(current_path, old_name)} -> {os.path.join(current_path, new_name)}')
    except Exception as e:
        flash(f'重命名失败: {str(e)}', 'error')
        logging.error(f'用户 {current_user.id} 重命名 {old_path} 失败: {str(e)}')
    
    return redirect(url_for('file_sharing.file_sharing', path=current_path, root=root_type))
