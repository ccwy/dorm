# -*- coding: utf-8 -*-
"""Agent Blueprint包 - 导出两个Blueprint"""
from .agent_api import agent_api_bp
from .agent_manage import agent_manage_bp

__all__ = ['agent_api_bp', 'agent_manage_bp']