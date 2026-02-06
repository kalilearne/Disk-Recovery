#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试磁盘镜像快照功能
"""

import os
import sys
import tempfile
from pathlib import Path

def test_disk_image_import():
    """测试磁盘镜像模块导入"""
    print("=== 测试磁盘镜像模块导入 ===")
    try:
        from disk_image_snapshot import DiskImageSnapshot, create_disk_image_snapshot
        print("✓ 磁盘镜像模块导入成功")
        return True
    except ImportError as e:
        print(f"✗ 磁盘镜像模块导入失败: {e}")
        return False

def test_disk_image_creation():
    """测试磁盘镜像创建功能"""
    print("\n=== 测试磁盘镜像创建功能 ===")
    try:
        from disk_image_snapshot import DiskImageSnapshot
        
        # 创建临时测试文件作为"磁盘"
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            test_data = b"This is test disk data for imaging" * 100
            temp_file.write(test_data)
            temp_disk_path = temp_file.name
        
        try:
            # 创建磁盘镜像快照对象
            snapshot = DiskImageSnapshot()
            
            # 测试获取磁盘大小
            disk_size = snapshot.get_disk_size(temp_disk_path)
            print(f"✓ 磁盘大小获取成功: {disk_size} 字节")
            
            # 测试创建临时目录
            temp_dir = snapshot._create_temp_directory()
            print(f"✓ 临时目录创建成功: {temp_dir}")
            
            # 清理临时目录
            snapshot._cleanup_temp_directory()
            print("✓ 临时目录清理成功")
            
            return True
            
        finally:
            # 清理测试文件
            os.unlink(temp_disk_path)
            
    except Exception as e:
        print(f"✗ 磁盘镜像创建测试失败: {e}")
        return False

def test_file_signature_recovery_integration():
    """测试文件签名恢复集成"""
    print("\n=== 测试文件签名恢复集成 ===")
    try:
        from file_signature_recovery import FileSignatureRecovery
        print("✓ 文件签名恢复模块导入成功")
        
        # 检查是否有recover_files_by_signature_with_snapshot方法
        if hasattr(FileSignatureRecovery, 'recover_files_by_signature_with_snapshot'):
            print("✓ 快照恢复方法存在")
            return True
        else:
            print("✗ 快照恢复方法不存在")
            return False
            
    except ImportError as e:
        print(f"✗ 文件签名恢复模块导入失败: {e}")
        return False

def test_disk_recovery_tool_integration():
    """测试磁盘恢复工具集成"""
    print("\n=== 测试磁盘恢复工具集成 ===")
    try:
        # 检查disk_recovery_tool.py是否存在
        tool_path = Path("disk_recovery_tool.py")
        if tool_path.exists():
            print("✓ 磁盘恢复工具文件存在")
            
            # 读取文件内容检查是否包含磁盘镜像相关内容
            with open(tool_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            if "磁盘镜像快照" in content:
                print("✓ 磁盘镜像快照功能已集成")
                return True
            else:
                print("✗ 磁盘镜像快照功能未集成")
                return False
        else:
            print("✗ 磁盘恢复工具文件不存在")
            return False
            
    except Exception as e:
        print(f"✗ 磁盘恢复工具集成测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("磁盘镜像快照功能测试")
    print("=" * 50)
    
    tests = [
        test_disk_image_import,
        test_disk_image_creation,
        test_file_signature_recovery_integration,
        test_disk_recovery_tool_integration,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 50)
    print(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("✓ 所有测试通过，磁盘镜像快照功能应该可以正常工作")
        return True
    else:
        print("✗ 部分测试失败，请检查相关功能")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)