#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
需求管理系统 - 快速设置脚本
"""

import os
import sys

def create_project_structure():
    """创建项目目录结构"""
    
    # 创建目录
    directories = ['templates', 'static']
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✓ 创建目录: {directory}")
    
    # 创建requirements.txt
    requirements_content = """Flask==2.3.2
Flask-SQLAlchemy==3.0.5
Flask-WTF==1.1.1
WTForms==3.0.1"""
    
    with open('requirements.txt', 'w', encoding='utf-8') as f:
        f.write(requirements_content)
    print("✓ 创建文件: requirements.txt")
    
    print("\n项目结构创建完成！")
    print("\n下一步:")
    print("1. 安装依赖: pip install -r requirements.txt")
    print("2. 运行应用: python app.py")
    print("3. 访问系统: http://localhost:5000")

if __name__ == '__main__':
    create_project_structure()
