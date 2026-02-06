#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G盘访问问题诊断脚本
模拟实际的文件签名恢复调用流程
"""

import os
import sys

def diagnose_g_drive_step_by_step():
    """逐步诊断G盘访问问题"""
    print("=== G盘访问问题逐步诊断 ===")
    
    # 步骤1: 基础系统检查
    print("\n步骤1: 基础系统检查")
    print(f"操作系统: {os.name}")
    print(f"当前工作目录: {os.getcwd()}")
    
    # 步骤2: 检查G盘基础访问
    print("\n步骤2: 检查G盘基础访问")
    g_paths = ["G:", "G:\\", "g:", "g:\\"]
    g_accessible = False
    
    for path in g_paths:
        try:
            exists = os.path.exists(path)
            print(f"  {path} -> os.path.exists(): {exists}")
            if exists:
                g_accessible = True
        except Exception as e:
            print(f"  {path} -> 检查失败: {e}")
    
    if not g_accessible:
        print("  ✗ G盘基础访问失败，无法继续")
        return False
    
    # 步骤3: 检查Win32模块
    print("\n步骤3: 检查Win32模块")
    try:
        import win32api
        import win32file
        print("  ✓ Win32模块导入成功")
        
        # 获取逻辑驱动器列表
        drives = win32api.GetLogicalDriveStrings()
        drive_list = drives.split('\x00')[:-1]
        print(f"  逻辑驱动器: {drive_list}")
        
        # 检查G盘是否在列表中
        g_in_list = any(d.upper().startswith('G:') for d in drive_list)
        print(f"  G盘在列表中: {g_in_list}")
        
    except ImportError as e:
        print(f"  ✗ Win32模块导入失败: {e}")
        return False
    except Exception as e:
        print(f"  ✗ Win32模块检查失败: {e}")
        return False
    
    # 步骤4: 测试磁盘镜像快照模块导入
    print("\n步骤4: 测试磁盘镜像快照模块导入")
    try:
        from disk_image_snapshot import DiskImageSnapshot, create_disk_image_snapshot
        print("  ✓ 磁盘镜像快照模块导入成功")
    except ImportError as e:
        print(f"  ✗ 磁盘镜像快照模块导入失败: {e}")
        return False
    except Exception as e:
        print(f"  ✗ 磁盘镜像快照模块导入异常: {e}")
        return False
    
    # 步骤5: 测试DiskImageSnapshot对象创建
    print("\n步骤5: 测试DiskImageSnapshot对象创建")
    try:
        snapshot = DiskImageSnapshot()
        print("  ✓ DiskImageSnapshot对象创建成功")
    except Exception as e:
        print(f"  ✗ DiskImageSnapshot对象创建失败: {e}")
        return False
    
    # 步骤6: 测试路径识别功能
    print("\n步骤6: 测试路径识别功能")
    test_paths = ["G:", "G:\\", "g:", "g:\\"]
    
    for path in test_paths:
        try:
            is_drive = snapshot._is_drive_path(path)
            print(f"  {path} -> 路径识别: {'驱动器路径' if is_drive else '非驱动器路径'}")
        except Exception as e:
            print(f"  {path} -> 路径识别失败: {e}")
    
    # 步骤7: 测试磁盘大小获取（详细模式）
    print("\n步骤7: 测试磁盘大小获取（详细模式）")
    for path in ["G:", "G:\\"]:
        print(f"\n  测试路径: {path}")
        try:
            print(f"    调用 snapshot.get_disk_size('{path}')...")
            size = snapshot.get_disk_size(path)
            if size > 0:
                print(f"    ✓ 成功获取磁盘大小: {size:,} 字节 ({size/(1024**3):.2f} GB)")
            else:
                print(f"    ✗ 磁盘大小为0或获取失败")
        except Exception as e:
            print(f"    ✗ 获取磁盘大小异常: {e}")
            import traceback
            print(f"    异常详情: {traceback.format_exc()}")
    
    # 步骤8: 测试create_disk_image_snapshot函数
    print("\n步骤8: 测试create_disk_image_snapshot函数")
    try:
        print("  调用 create_disk_image_snapshot('G:')...")
        
        def test_progress(current, total, message):
            if total > 0:
                percent = (current / total) * 100
                print(f"    进度: {percent:.1f}% - {message}")
            else:
                print(f"    {message}")
        
        result = create_disk_image_snapshot('G:', progress_callback=test_progress)
        
        if result and result.get('success'):
            print(f"  ✓ 磁盘镜像快照创建成功: {result.get('image_path')}")
            # 清理
            if 'snapshot_object' in result:
                result['snapshot_object'].cleanup()
        else:
            error_msg = result.get('error') if result else '未知错误'
            print(f"  ✗ 磁盘镜像快照创建失败: {error_msg}")
            
    except Exception as e:
        print(f"  ✗ create_disk_image_snapshot调用异常: {e}")
        import traceback
        print(f"  异常详情: {traceback.format_exc()}")
    
    print("\n=== 诊断完成 ===")
    return True

def main():
    """主函数"""
    print("G盘访问问题诊断工具")
    print("=" * 60)
    
    try:
        diagnose_g_drive_step_by_step()
    except KeyboardInterrupt:
        print("\n用户中断诊断")
    except Exception as e:
        print(f"\n诊断过程中发生异常: {e}")
        import traceback
        print(f"异常详情: {traceback.format_exc()}")
    
    print("\n诊断结束")

if __name__ == "__main__":
    main()