/**
 * 统一分页组件 PaginationManager
 * 
 * 支持两种模式：
 * - server模式：服务端渲染分页（Jinja2变量 + URL跳转），用于使用 page_range 循环的模板
 * - client模式：客户端JS分页（API调用 + DOM动态渲染），用于含内联 updatePagination 函数的模板
 * 
 * 使用示例：
 * 
 * // server模式 - 服务端渲染分页
 * var pager = new PaginationManager({
 *   container: '#paginationContainer',
 *   mode: 'server',
 *   total: {{ total_count }},
 *   currentPage: {{ current_page }},
 *   totalPages: {{ total_pages }},
 *   pageSize: {{ per_page }},
 *   urlTemplate: '{{ url_for("some.route", page=0, per_page=0) }}',
 *   // urlTemplate 中的占位符会被替换：{page} -> 页码, {pageSize} -> 每页条数
 *   showPages: 5
 * });
 * pager.render();
 * 
 * // client模式 - 客户端JS分页
 * var pager = new PaginationManager({
 *   container: '#paginationContainer',
 *   mode: 'client',
 *   total: 0,
 *   currentPage: 1,
 *   totalPages: 1,
 *   pageSize: 10,
 *   onPageChange: function(page, pageSize) {
 *     // 调用API获取数据，然后调用 pager.update() 更新状态
 *     fetchData(page, pageSize);
 *   },
 *   onPageSizeChange: function(pageSize) {
 *     // 每页条数变化回调
 *   },
 *   showPages: 5
 * });
 * 
 * // API返回数据后更新分页状态
 * pager.update({ total: data.total, currentPage: data.page, totalPages: data.pages, pageSize: data.per_page });
 */
(function(global) {
  'use strict';

  /**
   * 分页管理器构造函数
   * @param {Object} options 配置选项
   * @param {string|HTMLElement} options.container - 分页容器DOM元素或选择器
   * @param {string} [options.mode='client'] - 模式：'server' 或 'client'
   * @param {Function} [options.onPageChange] - client模式下页码变化回调 function(page, pageSize)
   * @param {Function} [options.onPageSizeChange] - 每页条数变化回调 function(pageSize)
   * @param {number} [options.showPages=5] - 显示的页码数量
   * @param {number} [options.total=0] - 总记录数
   * @param {number} [options.currentPage=1] - 当前页码
   * @param {number} [options.totalPages=0] - 总页数
   * @param {number} [options.pageSize=10] - 每页条数
   * @param {Array} [options.pageSizeOptions=[10,20,50,100]] - 每页条数选项
   * @param {boolean} [options.showPageSize=true] - 是否显示每页条数选择器
   * @param {boolean} [options.showTotal=true] - 是否显示总数信息
   * @param {string} [options.urlTemplate] - server模式的URL模板，支持 {page} 和 {pageSize} 占位符
   * @param {string} [options.pageParam='page'] - URL中页码参数名（用于构建URL）
   * @param {Object} [options.labels] - 自定义标签文本
   * @param {string} [options.activeClass] - 当前页按钮的自定义CSS类
   * @param {string} [options.containerClass] - 容器的自定义CSS类
   */
  function PaginationManager(containerOrOptions, options) {
    // 兼容两种调用方式:
    // 1. new PaginationManager('container-id', {mode: 'server', ...})
    // 2. new PaginationManager({container: '#container-id', mode: 'server', ...})
    if (typeof containerOrOptions === 'string') {
      // 方式1: 第一个参数是容器ID字符串
      var containerId = containerOrOptions;
      options = options || {};
      options.container = containerId.startsWith('#') ? containerId : '#' + containerId;
    } else {
      // 方式2: 第一个参数是配置对象
      options = containerOrOptions || {};
    }

    if (!options) {
      throw new Error('PaginationManager: options 参数不能为空');
    }

    // 解析容器
    if (typeof options.container === 'string') {
      var selector = options.container.startsWith('#') ? options.container : '#' + options.container;
      this.container = document.querySelector(selector);
    } else {
      this.container = options.container;
    }

    if (!this.container) {
      throw new Error('PaginationManager: 找不到分页容器元素');
    }

    // 基本配置
    this.mode = options.mode || 'client';
    this.onPageChange = options.onPageChange || null;
    this.onPageSizeChange = options.onPageSizeChange || null;
    this.showPages = options.showPages || 5;
    this.total = options.total || 0;
    this.currentPage = options.currentPage || 1;
    this.totalPages = options.totalPages || 0;
    this.pageSize = options.pageSize || 10;
    this.pageSizeOptions = options.pageSizeOptions || [10, 20, 50, 100];
    this.showPageSize = options.showPageSize !== false;
    this.showTotal = options.showTotal !== false;
    this.urlTemplate = options.urlTemplate || '';
    this.pageParam = options.pageParam || 'page';
    this.activeClass = options.activeClass || '';
    this.containerClass = options.containerClass || '';

    // 自定义标签
    this.labels = {
      prev: '上一页',
      next: '下一页',
      total: '共 {total} 条',
      pageSize: '每页 {size} 条',
      range: '显示 {from}-{to} 条',
      pageInfo: '第 {page}/{pages} 页',
      first: '首页',
      last: '末页'
    };
    if (options.labels) {
      for (var key in options.labels) {
        if (options.labels.hasOwnProperty(key)) {
          this.labels[key] = options.labels[key];
        }
      }
    }

    // 内部状态
    this._rendered = false;

    // 自动渲染
    this.render();
  }

  /**
   * 生成页码范围（与后端 generate_page_range 一致的算法）
   * 始终显示首页和末页，中间用省略号连接
   * 
   * @param {number} currentPage 当前页码
   * @param {number} totalPages 总页数
   * @returns {Array} 页码数组，包含数字和 '...' 省略号
   */
  PaginationManager.prototype.generatePageRange = function(currentPage, totalPages) {
    var showPages = this.showPages;

    // 总页数小于等于显示数量时，显示全部
    if (totalPages <= showPages) {
      var result = [];
      for (var i = 1; i <= totalPages; i++) {
        result.push(i);
      }
      return result;
    }

    // 计算中间页码范围
    var half = Math.floor(showPages / 2);
    var start = Math.max(1, currentPage - half);
    var end = Math.min(totalPages, start + showPages - 1);

    // 如果末尾不够，向前调整
    if (end - start < showPages - 1) {
      start = Math.max(1, end - showPages + 1);
    }

    var pageRange = [];

    // 添加首页和省略号
    if (start > 1) {
      pageRange.push(1);
      if (start > 2) {
        pageRange.push('...');
      }
    }

    // 添加中间页码
    for (var j = start; j <= end; j++) {
      pageRange.push(j);
    }

    // 添加省略号和末页
    if (end < totalPages) {
      if (end < totalPages - 1) {
        pageRange.push('...');
      }
      pageRange.push(totalPages);
    }

    return pageRange;
  };

  /**
   * 构建server模式的URL
   * @param {number} page 目标页码
   * @param {number} [pageSize] 每页条数
   * @returns {string} 完整URL
   */
  PaginationManager.prototype._buildUrl = function(page, pageSize) {
    var ps = pageSize || this.pageSize;
    var url = this.urlTemplate;

    // 替换占位符 {page} 和 {pageSize}
    url = url.replace(/\{page\}/g, page);
    url = url.replace(/\{pageSize\}/g, ps);

    return url;
  };

  /**
   * 渲染分页UI
   * 根据mode选择不同的渲染方式
   */
  PaginationManager.prototype.render = function() {
    var container = this.container;

    // 清空容器
    container.innerHTML = '';

    // 如果没有数据或总页数为0，隐藏容器
    if (this.totalPages <= 0 && this.total <= 0) {
      container.style.display = 'none';
      return;
    }

    container.style.display = '';

    // 构建外层容器
    var wrapper = document.createElement('div');
    wrapper.className = 'flex flex-col sm:flex-row items-center justify-between gap-3 mt-4';
    if (this.containerClass) {
      wrapper.className += ' ' + this.containerClass;
    }

    // 左侧信息区域
    var infoDiv = document.createElement('div');
    infoDiv.className = 'flex items-center flex-wrap gap-2 text-sm text-gray-700';

    // 显示总数和范围信息
    if (this.showTotal) {
      var from = this.total > 0 ? (this.currentPage - 1) * this.pageSize + 1 : 0;
      var to = Math.min(this.currentPage * this.pageSize, this.total);

      var rangeText = this.labels.range
        .replace('{from}', from)
        .replace('{to}', to);
      var totalText = this.labels.total.replace('{total}', this.total);

      var rangeSpan = document.createElement('span');
      rangeSpan.className = 'pm-range';
      rangeSpan.textContent = rangeText;

      var totalSpan = document.createElement('span');
      totalSpan.className = 'pm-total';
      totalSpan.textContent = totalText;

      infoDiv.appendChild(rangeSpan);
      infoDiv.appendChild(totalSpan);
    }

    // 显示页码信息
    var pageInfoSpan = document.createElement('span');
    pageInfoSpan.className = 'pm-page-info text-gray-500';
    pageInfoSpan.textContent = this.labels.pageInfo
      .replace('{page}', this.currentPage)
      .replace('{pages}', this.totalPages);
    infoDiv.appendChild(pageInfoSpan);

    // 每页条数选择器
    if (this.showPageSize) {
      var pageSizeWrapper = document.createElement('div');
      pageSizeWrapper.className = 'flex items-center';

      var pageSizeLabel = document.createElement('span');
      pageSizeLabel.className = 'text-sm text-gray-700 mr-1';
      pageSizeLabel.textContent = '每页显示：';

      var pageSizeSelect = document.createElement('select');
      pageSizeSelect.className = 'px-2 py-1 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 pm-page-size-select';

      for (var k = 0; k < this.pageSizeOptions.length; k++) {
        var opt = document.createElement('option');
        opt.value = this.pageSizeOptions[k];
        opt.textContent = this.pageSizeOptions[k] + '条/页';
        if (this.pageSizeOptions[k] === this.pageSize) {
          opt.selected = true;
        }
        pageSizeSelect.appendChild(opt);
      }

      // 绑定每页条数变化事件
      this._bindPageSizeChange(pageSizeSelect);

      pageSizeWrapper.appendChild(pageSizeLabel);
      pageSizeWrapper.appendChild(pageSizeSelect);
      infoDiv.appendChild(pageSizeWrapper);
    }

    wrapper.appendChild(infoDiv);

    // 右侧页码区域
    var pageNav = document.createElement('div');
    pageNav.className = 'flex space-x-1';

    if (this.mode === 'server') {
      this._renderServerPages(pageNav);
    } else {
      this._renderClientPages(pageNav);
    }

    wrapper.appendChild(pageNav);
    container.appendChild(wrapper);

    this._rendered = true;
  };

  /**
   * 渲染server模式页码按钮
   * @param {HTMLElement} container 页码容器
   */
  PaginationManager.prototype._renderServerPages = function(container) {
    var self = this;
    var pageRange = this.generatePageRange(this.currentPage, this.totalPages);

    // 上一页按钮
    var prevBtn = document.createElement('a');
    prevBtn.className = 'px-3 py-1 border border-gray-300 rounded bg-white text-sm text-gray-500 hover:bg-gray-50';
    if (this.currentPage <= 1) {
      prevBtn.className += ' opacity-50 cursor-not-allowed';
      prevBtn.href = 'javascript:void(0)';
    } else {
      prevBtn.href = this._buildUrl(this.currentPage - 1);
    }
    prevBtn.innerHTML = '<i class="fa fa-chevron-left"></i>';
    container.appendChild(prevBtn);

    // 页码按钮
    for (var i = 0; i < pageRange.length; i++) {
      var p = pageRange[i];
      if (p === '...') {
        var ellipsis = document.createElement('span');
        ellipsis.className = 'px-3 py-1 border border-gray-300 rounded bg-white text-sm text-gray-400';
        ellipsis.textContent = '...';
        container.appendChild(ellipsis);
      } else {
        var pageLink = document.createElement('a');
        if (p === this.currentPage) {
          pageLink.className = 'px-3 py-1 border rounded text-sm font-medium border-primary bg-primary text-white';
          if (this.activeClass) {
            pageLink.className += ' ' + this.activeClass;
          }
        } else {
          pageLink.className = 'px-3 py-1 border border-gray-300 rounded bg-white text-sm text-gray-700 hover:bg-gray-50';
        }
        pageLink.href = this._buildUrl(p);
        pageLink.textContent = p;
        container.appendChild(pageLink);
      }
    }

    // 下一页按钮
    var nextBtn = document.createElement('a');
    nextBtn.className = 'px-3 py-1 border border-gray-300 rounded bg-white text-sm text-gray-500 hover:bg-gray-50';
    if (this.currentPage >= this.totalPages) {
      nextBtn.className += ' opacity-50 cursor-not-allowed';
      nextBtn.href = 'javascript:void(0)';
    } else {
      nextBtn.href = this._buildUrl(this.currentPage + 1);
    }
    nextBtn.innerHTML = '<i class="fa fa-chevron-right"></i>';
    container.appendChild(nextBtn);
  };

  /**
   * 渲染client模式页码按钮
   * @param {HTMLElement} container 页码容器
   */
  PaginationManager.prototype._renderClientPages = function(container) {
    var self = this;
    var pageRange = this.generatePageRange(this.currentPage, this.totalPages);

    // 上一页按钮
    var prevBtn = document.createElement('button');
    prevBtn.type = 'button';
    prevBtn.className = 'px-3 py-1 border border-gray-300 rounded bg-white text-sm text-gray-500 hover:bg-gray-50';
    if (this.currentPage <= 1) {
      prevBtn.disabled = true;
      prevBtn.className += ' opacity-50 cursor-not-allowed';
    }
    prevBtn.innerHTML = '<i class="fa fa-chevron-left"></i>';
    prevBtn.addEventListener('click', function() {
      if (self.currentPage > 1) {
        self.goToPage(self.currentPage - 1);
      }
    });
    container.appendChild(prevBtn);

    // 页码按钮
    for (var i = 0; i < pageRange.length; i++) {
      var p = pageRange[i];
      if (p === '...') {
        var ellipsis = document.createElement('button');
        ellipsis.type = 'button';
        ellipsis.className = 'px-3 py-1 border border-gray-300 rounded bg-white text-sm text-gray-400';
        ellipsis.disabled = true;
        ellipsis.textContent = '...';
        container.appendChild(ellipsis);
      } else {
        var pageBtn = document.createElement('button');
        pageBtn.type = 'button';
        if (p === this.currentPage) {
          pageBtn.className = 'px-3 py-1 border rounded text-sm font-medium border-primary bg-primary text-white';
          if (this.activeClass) {
            pageBtn.className += ' ' + this.activeClass;
          }
        } else {
          pageBtn.className = 'px-3 py-1 border border-gray-300 rounded bg-white text-sm text-gray-700 hover:bg-gray-50';
        }
        pageBtn.textContent = p;
        // 使用闭包捕获页码值
        (function(pageNum) {
          pageBtn.addEventListener('click', function() {
            self.goToPage(pageNum);
          });
        })(p);
        container.appendChild(pageBtn);
      }
    }

    // 下一页按钮
    var nextBtn = document.createElement('button');
    nextBtn.type = 'button';
    nextBtn.className = 'px-3 py-1 border border-gray-300 rounded bg-white text-sm text-gray-500 hover:bg-gray-50';
    if (this.currentPage >= this.totalPages) {
      nextBtn.disabled = true;
      nextBtn.className += ' opacity-50 cursor-not-allowed';
    }
    nextBtn.innerHTML = '<i class="fa fa-chevron-right"></i>';
    nextBtn.addEventListener('click', function() {
      if (self.currentPage < self.totalPages) {
        self.goToPage(self.currentPage + 1);
      }
    });
    container.appendChild(nextBtn);
  };

  /**
   * 绑定每页条数选择器变化事件
   * @param {HTMLSelectElement} select 选择器元素
   */
  PaginationManager.prototype._bindPageSizeChange = function(select) {
    var self = this;
    select.addEventListener('change', function() {
      var newPageSize = parseInt(this.value, 10);
      if (newPageSize !== self.pageSize) {
        self.pageSize = newPageSize;
        // 重新计算总页数
        if (self.total > 0) {
          self.totalPages = Math.ceil(self.total / self.pageSize);
        }
        // 重置到第一页
        self.currentPage = 1;

        // 触发每页条数变化回调
        if (self.onPageSizeChange) {
          self.onPageSizeChange(newPageSize);
        }

        // client模式下也触发页码变化回调
        if (self.mode === 'client' && self.onPageChange) {
          self.onPageChange(1, newPageSize);
        }

        // server模式下跳转到第一页
        if (self.mode === 'server') {
          window.location.href = self._buildUrl(1, newPageSize);
          return;
        }

        // 重新渲染
        self.render();
      }
    });
  };

  /**
   * 更新分页状态并重新渲染
   * @param {Object} state 新的分页状态
   * @param {number} [state.total] 总记录数
   * @param {number} [state.currentPage] 当前页码
   * @param {number} [state.totalPages] 总页数
   * @param {number} [state.pageSize] 每页条数
   */
  PaginationManager.prototype.update = function(state) {
    if (!state) return;

    if (typeof state.total === 'number') {
      this.total = state.total;
    }
    if (typeof state.currentPage === 'number') {
      this.currentPage = state.currentPage;
    }
    if (typeof state.totalPages === 'number') {
      this.totalPages = state.totalPages;
    }
    if (typeof state.pageSize === 'number') {
      this.pageSize = state.pageSize;
    }

    // 如果没有提供totalPages但有total，自动计算
    if (typeof state.totalPages !== 'number' && typeof state.total === 'number' && this.pageSize > 0) {
      this.totalPages = Math.ceil(this.total / this.pageSize);
    }

    // 确保总页数至少为1
    if (this.totalPages < 1) {
      this.totalPages = 1;
    }

    // 确保当前页在有效范围内
    if (this.currentPage > this.totalPages) {
      this.currentPage = this.totalPages;
    }
    if (this.currentPage < 1) {
      this.currentPage = 1;
    }

    this.render();
  };

  /**
   * 跳转到指定页
   * @param {number} page 目标页码
   */
  PaginationManager.prototype.goToPage = function(page) {
    // 边界检查
    if (page < 1 || page > this.totalPages) {
      return;
    }

    this.currentPage = page;

    if (this.mode === 'server') {
      // server模式：通过URL跳转
      window.location.href = this._buildUrl(page);
    } else if (this.mode === 'client') {
      // client模式：触发回调
      if (this.onPageChange) {
        this.onPageChange(page, this.pageSize);
      }
      // 重新渲染分页UI
      this.render();
    }
  };

  /**
   * 获取当前分页状态
   * @returns {Object} 当前分页状态
   */
  PaginationManager.prototype.getState = function() {
    return {
      total: this.total,
      currentPage: this.currentPage,
      totalPages: this.totalPages,
      pageSize: this.pageSize
    };
  };

  /**
   * 销毁分页组件，清理DOM和事件
   */
  PaginationManager.prototype.destroy = function() {
    if (this.container) {
      this.container.innerHTML = '';
    }
    this._rendered = false;
  };

  /**
   * 从当前页面URL构建分页URL模板
   * 保留所有现有查询参数，将page和per_page替换为占位符
   * @returns {string} URL模板，包含 {page} 和 {pageSize} 占位符
   */
  PaginationManager.buildUrlTemplate = function() {
    var search = window.location.search.substring(1);
    var params = [];
    if (search) {
      var pairs = search.split('&');
      for (var i = 0; i < pairs.length; i++) {
        if (pairs[i] && !pairs[i].startsWith('page=') && !pairs[i].startsWith('per_page=')) {
          params.push(pairs[i]);
        }
      }
    }
    params.push('page={page}');
    params.push('per_page={pageSize}');
    return window.location.pathname + '?' + params.join('&');
  };

  // 暴露为全局变量
  global.PaginationManager = PaginationManager;

})(window);