/**
 * 表单验证脚本 - 解决登录按钮无响应问题
 */
document.addEventListener('DOMContentLoaded', function() {
    try {
        initFormValidations();
        console.log('表单验证初始化成功');
    } catch (error) {
        console.error('表单验证初始化失败:', error);
        // 容错处理：解除所有表单的提交阻止
        document.querySelectorAll('form').forEach(form => {
            form.removeAttribute('data-validate');
        });
    }
});

/**
 * 初始化所有需要验证的表单
 */
function initFormValidations() {
    const forms = document.querySelectorAll('form[data-validate]');
    forms.forEach(form => {
        form.addEventListener('submit', handleFormSubmit);
    });
}

/**
 * 处理表单提交
 * @param {Event} e - 提交事件
 */
function handleFormSubmit(e) {
    const form = e.target;
    let isValid = true;
    
    // 清除之前的错误
    clearValidationErrors(form);
    
    // 验证所有必填字段
    const requiredInputs = form.querySelectorAll('input[required]');
    requiredInputs.forEach(input => {
        if (!validateInput(input)) {
            isValid = false;
        }
    });
    
    // 验证失败阻止提交
    if (!isValid) {
        e.preventDefault();
        e.stopPropagation();
        return false;
    }
    
    // 验证通过允许提交
    return true;
}

/**
 * 验证单个输入框
 * @param {HTMLInputElement} input - 输入框元素
 * @returns {boolean} - 验证是否通过
 */
function validateInput(input) {
    const value = input.value.trim();
    let isValid = true;
    
    // 非空验证
    if (value === '') {
        showError(input, input.dataset.msgRequired || '此字段为必填项');
        isValid = false;
    }
    // 最小长度验证
    else if (input.dataset.minLength) {
        const minLength = parseInt(input.dataset.minLength, 10);
        if (!isNaN(minLength) && value.length < minLength) {
            showError(input, input.dataset.msgMinLength || 
                `至少需要${minLength}个字符`);
            isValid = false;
        }
    }
    
    return isValid;
}

/**
 * 显示错误提示
 * @param {HTMLInputElement} input - 输入框
 * @param {string} message - 错误信息
 */
function showError(input, message) {
    // 查找或创建错误提示元素
    let errorElement = input.nextElementSibling;
    if (!errorElement || !errorElement.classList.contains('error-message')) {
        errorElement = document.createElement('span');
        errorElement.className = 'error-message';
        input.parentNode.insertBefore(errorElement, input.nextSibling);
    }
    
    // 显示错误
    errorElement.textContent = message;
    errorElement.classList.add('active');
    input.classList.add('border-danger');
}

/**
 * 清除表单所有错误提示
 * @param {HTMLFormElement} form - 表单元素
 */
function clearValidationErrors(form) {
    // 清除错误文本
    form.querySelectorAll('.error-message').forEach(el => {
        el.textContent = '';
        el.classList.remove('active');
    });
    // 清除输入框错误样式
    form.querySelectorAll('.form-control').forEach(el => {
        el.classList.remove('border-danger');
    });
}
