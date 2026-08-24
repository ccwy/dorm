"""
延迟导入工具模块
提供重型库（pandas、openpyxl等）的延迟加载代理，
使模块级导入不会触发实际库加载，仅在首次使用时才导入。
"""
import importlib


class _LazyModule:
    """延迟导入代理模块，仅在首次属性访问时才真正导入目标模块"""
    
    def __init__(self, name):
        self._name = name
        self._module = None
    
    def _load(self):
        if self._module is None:
            self._module = importlib.import_module(self._name)
        return self._module
    
    def __getattr__(self, name):
        return getattr(self._load(), name)
    
    def __repr__(self):
        if self._module is None:
            return f"<LazyModule '{self._name}' (not loaded)>"
        return repr(self._module)


class _LazyAttr:
    """延迟导入代理属性，仅在首次调用时才真正导入目标模块属性"""
    
    def __init__(self, module_path, attr_name):
        self._module_path = module_path
        self._attr_name = attr_name
        self._resolved = None
    
    def _resolve(self):
        if self._resolved is None:
            module = importlib.import_module(self._module_path)
            self._resolved = getattr(module, self._attr_name)
        return self._resolved
    
    def __call__(self, *args, **kwargs):
        return self._resolve()(*args, **kwargs)
    
    def __getattr__(self, name):
        return getattr(self._resolve(), name)
    
    def __repr__(self):
        if self._resolved is None:
            return f"<LazyAttr '{self._module_path}.{self._attr_name}' (not loaded)>"
        return repr(self._resolved)


# 预定义常用重型库的延迟导入
pd = _LazyModule('pandas')
openpyxl = _LazyModule('openpyxl')

# openpyxl 常用类/函数的延迟导入（支持 from ... import 风格）
Font = _LazyAttr('openpyxl.styles', 'Font')
Alignment = _LazyAttr('openpyxl.styles', 'Alignment')
PatternFill = _LazyAttr('openpyxl.styles', 'PatternFill')
Workbook = _LazyAttr('openpyxl', 'Workbook')
load_workbook = _LazyAttr('openpyxl', 'load_workbook')
get_column_letter = _LazyAttr('openpyxl.utils', 'get_column_letter')