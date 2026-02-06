#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试win32api和win32file模块的具体函数
"""

def test_win32_modules():
    """测试win32模块的具体函数"""
    print("正在测试win32模块...")
    
    # 测试win32api
    try:
        import win32api
        print("✓ win32api模块导入成功")
        
        # 测试GetLogicalDriveStrings
        try:
            drives = win32api.GetLogicalDriveStrings()
            print(f"✓ GetLogicalDriveStrings: {drives.split(chr(0))[:-1]}")
        except AttributeError:
            print("✗ GetLogicalDriveStrings函数不存在")
        except Exception as e:
            print(f"✗ GetLogicalDriveStrings调用失败: {e}")
        
        # 测试GetDriveType
        try:
            drive_type = win32api.GetDriveType("C:\\")
            print(f"✓ GetDriveType: {drive_type}")
        except AttributeError:
            print("✗ GetDriveType函数不存在")
        except Exception as e:
            print(f"✗ GetDriveType调用失败: {e}")
        
        # 测试GetVolumeInformation
        try:
            volume_info = win32api.GetVolumeInformation("C:\\")
            print(f"✓ GetVolumeInformation: {volume_info[0] if volume_info else 'None'}")
        except AttributeError:
            print("✗ GetVolumeInformation函数不存在")
        except Exception as e:
            print(f"✗ GetVolumeInformation调用失败: {e}")
            
    except ImportError as e:
        print(f"✗ win32api模块导入失败: {e}")
    
    print()
    
    # 测试win32file
    try:
        import win32file
        print("✓ win32file模块导入成功")
        
        # 测试GetDiskFreeSpaceEx
        try:
            free_space = win32file.GetDiskFreeSpaceEx("C:\\")
            print(f"✓ GetDiskFreeSpaceEx: {free_space[:2]}")
        except AttributeError:
            print("✗ GetDiskFreeSpaceEx函数不存在")
        except Exception as e:
            print(f"✗ GetDiskFreeSpaceEx调用失败: {e}")
        
        # 测试GetDriveType
        try:
            drive_type = win32file.GetDriveType("C:\\")
            print(f"✓ win32file.GetDriveType: {drive_type}")
        except AttributeError:
            print("✗ win32file.GetDriveType函数不存在")
        except Exception as e:
            print(f"✗ win32file.GetDriveType调用失败: {e}")
            
    except ImportError as e:
        print(f"✗ win32file模块导入失败: {e}")
    
    print()
    
    # 列出win32api的所有属性
    try:
        import win32api
        print("win32api模块的属性:")
        attrs = [attr for attr in dir(win32api) if not attr.startswith('_')]
        for attr in sorted(attrs):
            print(f"  - {attr}")
    except:
        pass

if __name__ == "__main__":
    test_win32_modules()