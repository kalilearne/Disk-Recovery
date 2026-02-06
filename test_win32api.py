#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试win32api模块导入
"""

def test_win32api_import():
    """测试win32api模块导入"""
    try:
        import win32api
        import win32file
        print("✓ win32api模块导入成功")
        
        # 测试基本功能
        try:
            drives = win32api.GetLogicalDriveStrings()
            print(f"✓ 获取逻辑驱动器成功: {drives.split(chr(0))[:-1]}")
        except Exception as e:
            print(f"✗ 获取逻辑驱动器失败: {e}")
            
    except ImportError as e:
        print(f"✗ win32api模块导入失败: {e}")
        print("请安装pywin32模块: pip install pywin32")
        return False
    except Exception as e:
        print(f"✗ win32api测试失败: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("正在测试win32api模块...")
    success = test_win32api_import()
    
    if success:
        print("\n✓ win32api模块测试通过")
    else:
        print("\n✗ win32api模块测试失败")
        print("\n解决方案:")
        print("1. 安装pywin32模块: pip install pywin32")
        print("2. 或者使用conda安装: conda install pywin32")
        print("3. 确保Python版本与pywin32版本兼容")