#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import struct
import platform

# Windows特定导入
if platform.system() == 'Windows':
    try:
        import win32api
        import win32file
        import winioctlcon
    except ImportError as e:
        print(f"Windows API模块导入失败: {e}")
        win32api = None
        win32file = None
        winioctlcon = None

class DiskReader:
    """磁盘读取类，提供读取物理磁盘、分区和扇区的功能"""
    
    @staticmethod
    def read_physical_disks():
        """读取物理磁盘列表"""
        disks = []
        
        if platform.system() == 'Windows':
            # Windows系统下使用win32api获取物理磁盘
            try:
                if win32api is None:
                    print("win32api模块未安装，无法获取磁盘信息")
                    return disks
                drives = win32api.GetLogicalDriveStrings().split('\x00')[:-1]
                for drive in drives:
                    try:
                        try:
                            drive_type = win32file.GetDriveType(drive)
                        except AttributeError:
                            # win32file没有GetDriveType函数，假设是固定磁盘
                            drive_type = 3  # DRIVE_FIXED
                        
                        if drive_type == 3 or drive_type == 2:  # DRIVE_FIXED or DRIVE_REMOVABLE
                            # 获取磁盘信息
                            volume_name = ''
                            try:
                                volume_name = win32api.GetVolumeInformation(drive)[0]
                            except AttributeError:
                                # win32api没有GetVolumeInformation函数
                                volume_name = '本地磁盘'
                            except Exception:
                                pass
                            
                            # 获取磁盘大小
                            try:
                                sectors_per_cluster, bytes_per_sector, free_clusters, total_clusters = win32file.GetDiskFreeSpace(drive)
                                total_size = total_clusters * sectors_per_cluster * bytes_per_sector
                                free_size = free_clusters * sectors_per_cluster * bytes_per_sector
                            except AttributeError:
                                # win32file没有GetDiskFreeSpace函数
                                total_size = 0
                                free_size = 0
                            except Exception:
                                total_size = 0
                                free_size = 0
                            
                            disk_info = {
                                'path': drive,
                                'name': f'{drive} {volume_name}',
                                'size': total_size,
                                'free': free_size,
                                'type': 'fixed' if drive_type == 3 else 'removable',  # 3 = DRIVE_FIXED
                                'letter': drive[0]
                            }
                            disks.append(disk_info)
                    except Exception as e:
                        print(f"Error reading drive {drive}: {e}")
                
                # 添加物理磁盘
                for i in range(10):  # 最多检查10个物理磁盘
                    try:
                        disk_path = f'\\\\.\\PhysicalDrive{i}'
                        handle = win32file.CreateFile(
                            disk_path,
                            win32file.GENERIC_READ,
                            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                            None,
                            win32file.OPEN_EXISTING,
                            0,
                            None
                        )
                        
                        if handle != win32file.INVALID_HANDLE_VALUE:
                            # 获取磁盘大小
                            try:
                                disk_size = win32file.DeviceIoControl(
                                    handle,
                                    winioctlcon.IOCTL_DISK_GET_LENGTH_INFO,
                                    None,
                                    8
                                )
                                disk_size = struct.unpack('Q', disk_size)[0]
                            except:
                                disk_size = 0
                            
                            disk_info = {
                                'path': disk_path,
                                'name': f'物理磁盘 {i}',
                                'size': disk_size,
                                'free': 0,
                                'type': 'physical'
                            }
                            disks.append(disk_info)
                            win32file.CloseHandle(handle)
                    except Exception as e:
                        # 如果无法打开磁盘，则跳过
                        pass
            except Exception as e:
                print(f"Error reading Windows disks: {e}")
        else:
            # Linux系统下使用lsblk命令获取物理磁盘
            try:
                import subprocess
                output = subprocess.check_output(['lsblk', '-b', '-o', 'NAME,SIZE,TYPE,MOUNTPOINT', '-J']).decode('utf-8')
                import json
                blk_data = json.loads(output)
                
                for device in blk_data.get('blockdevices', []):
                    if device.get('type') == 'disk':
                        disk_path = f"/dev/{device['name']}"
                        disk_size = int(device.get('size', 0))
                        
                        disk_info = {
                            'path': disk_path,
                            'name': f"物理磁盘 {device['name']}",
                            'size': disk_size,
                            'free': 0,
                            'type': 'physical'
                        }
                        disks.append(disk_info)
                        
                        # 添加分区
                        for child in device.get('children', []):
                            if child.get('type') == 'part':
                                part_path = f"/dev/{child['name']}"
                                part_size = int(child.get('size', 0))
                                mountpoint = child.get('mountpoint', '')
                                
                                part_info = {
                                    'path': part_path,
                                    'name': f"分区 {child['name']} {mountpoint}",
                                    'size': part_size,
                                    'free': 0,
                                    'type': 'partition',
                                    'parent': disk_path
                                }
                                disks.append(part_info)
            except Exception as e:
                print(f"Error reading Linux disks: {e}")
        
        return disks
    
    @staticmethod
    def read_disk_sector(disk_path, sector_offset, num_sectors=1):
        """读取指定磁盘的扇区数据"""
        try:
            if platform.system() == 'Windows':
                # 在Windows上，我们需要使用原始设备访问
                # 这需要管理员权限，并且可能需要更复杂的处理
                raw_path = disk_path
                if disk_path.endswith('\\'):
                    # 转换为原始设备路径
                    raw_path = f"\\\\.\\{disk_path[0]}:"
                
                try:
                    handle = win32file.CreateFile(
                        raw_path,
                        win32file.GENERIC_READ,
                        win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                        None,
                        win32file.OPEN_EXISTING,
                        0,
                        None
                    )
                    
                    try:
                        # 移动到指定扇区
                        sector_size = 512  # 假设扇区大小为512字节
                        win32file.SetFilePointer(handle, sector_offset * sector_size, win32file.FILE_BEGIN)
                        
                        # 读取数据
                        error_code, data = win32file.ReadFile(handle, num_sectors * sector_size)
                        return data
                    finally:
                        win32file.CloseHandle(handle)
                except Exception as e:
                    print(f"Error reading disk sector: {e}")
                    return b''
            else:
                # 在Linux上，我们可以直接读取设备文件
                with open(disk_path, 'rb') as f:
                    f.seek(sector_offset * 512)  # 假设扇区大小为512字节
                    return f.read(num_sectors * 512)
        except Exception as e:
            print(f"Error reading disk sector: {e}")
            return b''
    
    @staticmethod
    def read_virtual_disk(file_path):
        """读取虚拟磁盘文件"""
        try:
            # 获取文件大小
            file_size = os.path.getsize(file_path)
            
            # 读取文件内容
            with open(file_path, 'rb') as f:
                data = f.read(min(file_size, 10 * 1024 * 1024))  # 最多读取10MB
                return data
        except Exception as e:
            print(f"Error reading virtual disk: {e}")
            return b''