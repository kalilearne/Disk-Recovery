import os
import sys
import struct
from PyQt5.QtCore import QObject, pyqtSignal

class DiskManager(QObject):
    """磁盘管理器"""
    
    def __init__(self):
        super().__init__()
    
    def get_physical_disks(self):
        """获取物理磁盘列表"""
        disks = []
        
        if sys.platform == 'win32':
            # Windows系统
            try:
                try:
                    import win32file
                    import win32api
                except ImportError as e:
                    print(f"win32api模块导入失败: {e}")
                    # 使用备用方法
                    return self._get_disks_fallback()
                
                # 获取逻辑驱动器
                drives = win32api.GetLogicalDriveStrings()
                drive_list = drives.split('\x00')[:-1]
                
                for drive in drive_list:
                    try:
                        # 检查驱动器是否可访问
                        if not os.path.exists(drive):
                            continue
                        
                        # 额外检查：尝试访问驱动器根目录
                        try:
                            os.listdir(drive)
                        except (OSError, PermissionError):
                            # 驱动器存在但无法访问（如未插入的可移动驱动器）
                            continue
                            
                        drive_type = win32file.GetDriveType(drive)
                        if drive_type in [win32file.DRIVE_FIXED, win32file.DRIVE_REMOVABLE]:
                            size = self._get_drive_size(drive)
                            if size > 0:  # 只添加有效大小的驱动器
                                disks.append({
                                    'name': f'驱动器 {drive}',
                                    'path': drive,
                                    'size': size,
                                    'size_human': self._format_size(size),
                                    'type': 'logical'
                                })
                    except Exception as e:
                        # 跳过无法访问的逻辑驱动器
                        continue
                
                # 获取物理磁盘
                for i in range(10):
                    try:
                        disk_path = f'\\\\.\\PhysicalDrive{i}'
                        handle = win32file.CreateFile(
                            disk_path,
                            0,
                            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                            None,
                            win32file.OPEN_EXISTING,
                            0,
                            None
                        )
                        if handle != win32file.INVALID_HANDLE_VALUE:
                            win32file.CloseHandle(handle)
                            size = self._get_physical_disk_size(disk_path)
                            disks.append({
                                'name': f'物理磁盘 {i}',
                                'path': disk_path,
                                'size': size,
                                'size_human': self._format_size(size),
                                'type': 'physical'
                            })
                    except Exception as e:
                        # 跳过无法访问的物理磁盘
                        continue
            except ImportError:
                # 如果没有win32api，使用基本方法
                import string
                for letter in string.ascii_uppercase:
                    drive = f'{letter}:\\'
                    if os.path.exists(drive):
                        try:
                            size = self._get_drive_size_basic(drive)
                            if size > 0:  # 只添加有效大小的驱动器
                                disks.append({
                                    'name': f'驱动器 {letter}:',
                                    'path': drive,
                                    'size': size,
                                    'size_human': self._format_size(size),
                                'type': 'logical'
                            })
                        except:
                            continue
        else:
            # Linux/Unix系统
            import glob
            
            # 获取块设备
            block_devices = glob.glob('/dev/sd*') + glob.glob('/dev/hd*') + glob.glob('/dev/nvme*')
            for device in block_devices:
                if not device[-1].isdigit():  # 排除分区
                    try:
                        size = self._get_linux_disk_size(device)
                        disks.append({
                            'name': os.path.basename(device),
                            'path': device,
                            'size': size,
                            'size_human': self._format_size(size),
                            'type': 'physical'
                        })
                    except:
                        continue
        
        return disks
    
    def _get_disks_fallback(self):
        """获取磁盘列表的备用方法"""
        disks = []
        
        try:
            import os
            import shutil
            
            # Windows系统，检查A-Z盘符
            for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                drive_path = f'{letter}:\\'
                if os.path.exists(drive_path):
                    try:
                        # 尝试访问驱动器
                        os.listdir(drive_path)
                        
                        # 获取磁盘使用情况
                        total, used, free = shutil.disk_usage(drive_path)
                        
                        disk_info = {
                            'path': drive_path,
                            'name': f'{drive_path} 本地磁盘',
                            'size': total,
                            'free': free,
                            'type': 'fixed',
                            'letter': letter
                        }
                        disks.append(disk_info)
                        
                    except (OSError, PermissionError):
                        # 驱动器存在但无法访问
                        continue
                        
        except Exception as e:
            print(f"备用磁盘检测失败: {e}")
        
        return disks
    
    def get_disk_info(self, disk_path):
        """获取磁盘详细信息"""
        info = {}
        
        try:
            # 检查是否是逻辑驱动器（如 E:\）
            if len(disk_path) == 3 and disk_path[1:] == ':\\':
                # 逻辑驱动器
                info['path'] = disk_path
                info['name'] = f'驱动器 {disk_path}'
                info['type'] = 'Logical Drive'
                
                try:
                    size = self._get_drive_size(disk_path)
                    info['size'] = size
                    info['size_human'] = self._format_size(size)
                except:
                    pass
                
                # 对于逻辑驱动器，尝试获取其对应的物理磁盘分区信息
                try:
                    physical_info = self._get_logical_drive_partition_info(disk_path)
                    if physical_info:
                        info.update(physical_info)
                except Exception as e:
                    info['partition_error'] = f'无法获取分区信息: {str(e)}'
                
            elif os.path.exists(disk_path):
                # 基本信息
                info['path'] = disk_path
                info['name'] = os.path.basename(disk_path)
                
                if os.path.isfile(disk_path):
                    # 文件（虚拟磁盘）
                    size = os.path.getsize(disk_path)
                    info['size'] = size
                    info['size_human'] = self._format_size(size)
                    info['type'] = 'Virtual Disk'
                    
                    # 尝试读取文件头
                    with open(disk_path, 'rb') as f:
                        header = f.read(512)
                        info['header_preview'] = header[:64].hex()
                        
                        # 检查MBR签名
                        if len(header) >= 512 and header[510:512] == b'\x55\xaa':
                            info['mbr_signature'] = 'Valid (0x55AA)'
                            
                            # 解析分区表
                            partitions = []
                            for i in range(4):
                                offset = 446 + i * 16
                                if offset + 16 <= len(header):
                                    partition_data = header[offset:offset + 16]
                                    if partition_data[4] != 0:  # 分区类型不为0
                                        start_lba = struct.unpack('<L', partition_data[8:12])[0]
                                        sectors = struct.unpack('<L', partition_data[12:16])[0]
                                        partition = {
                                            'index': i + 1,
                                            'status': 'Active' if partition_data[0] == 0x80 else 'Inactive',
                                            'type': partition_data[4],
                                            'type_name': self._get_partition_type_name(partition_data[4]),
                                            'start_lba': start_lba,
                                            'start_sector': start_lba,  # 添加兼容性字段
                                            'sectors': sectors
                                        }
                                        partition['size_human'] = self._format_size(partition['sectors'] * 512)
                                        partitions.append(partition)
                            
                            if partitions:
                                info['partitions'] = partitions
                        else:
                            info['mbr_signature'] = 'Invalid or Missing'
                else:
                    # 目录或设备
                    info['type'] = 'Directory or Device'
            else:
                # 设备文件（Windows物理磁盘等）
                info['type'] = 'Physical Device'
                info['path'] = disk_path
                
                # 尝试获取设备信息
                if sys.platform == 'win32' and disk_path.startswith('\\\\.\\'):
                    try:
                        size = self._get_physical_disk_size(disk_path)
                        info['size'] = size
                        info['size_human'] = self._format_size(size)
                    except:
                        pass
        
        except Exception as e:
            info['error'] = f'获取磁盘信息失败: {str(e)}'
        
        return info
    
    def _get_drive_size(self, drive):
        """获取驱动器大小（Windows）"""
        try:
            import win32file
            free_bytes, total_bytes, _ = win32file.GetDiskFreeSpaceEx(drive)
            return total_bytes
        except:
            return 0
    
    def _get_drive_size_basic(self, drive):
        """获取驱动器大小（基本方法）"""
        try:
            import shutil
            total, used, free = shutil.disk_usage(drive)
            return total
        except:
            return 0
    
    def _get_physical_disk_size(self, disk_path):
        """获取物理磁盘大小"""
        try:
            if sys.platform == 'win32':
                import win32file
                import winioctlcon
                import struct
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
                    try:
                        # 使用IOCTL_DISK_GET_LENGTH_INFO获取磁盘大小
                        disk_size = win32file.DeviceIoControl(
                            handle,
                            winioctlcon.IOCTL_DISK_GET_LENGTH_INFO,
                            None,
                            8
                        )
                        size = struct.unpack('Q', disk_size)[0]
                        win32file.CloseHandle(handle)
                        return size
                    except:
                        win32file.CloseHandle(handle)
            return 0
        except:
            return 0
    
    def _get_linux_disk_size(self, device):
        """获取Linux磁盘大小"""
        try:
            with open(f'/sys/block/{os.path.basename(device)}/size', 'r') as f:
                sectors = int(f.read().strip())
                return sectors * 512
        except:
            return 0
    
    def _format_size(self, size):
        """格式化文件大小"""
        if size == 0:
            return '0 B'
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f'{size:.1f} {unit}'
            size /= 1024.0
        return f'{size:.1f} PB'
    
    def _get_partition_type_name(self, type_code):
        """获取分区类型名称"""
        partition_types = {
            0x00: 'Empty',
            0x01: 'FAT12',
            0x04: 'FAT16 <32M',
            0x05: 'Extended',
            0x06: 'FAT16',
            0x07: 'NTFS/HPFS',
            0x0B: 'FAT32',
            0x0C: 'FAT32 LBA',
            0x0E: 'FAT16 LBA',
            0x0F: 'Extended LBA',
            0x82: 'Linux Swap',
            0x83: 'Linux',
            0x8E: 'Linux LVM',
            0xEE: 'GPT Protective'
        }
        return partition_types.get(type_code, f'Unknown (0x{type_code:02X})')
    
    def _get_logical_drive_partition_info(self, drive_path):
        """获取逻辑驱动器的分区信息"""
        try:
            if sys.platform != 'win32':
                return None
            
            try:
                import win32file
                import win32api
            except ImportError as e:
                print(f"win32api模块导入失败: {e}")
                return None
            
            # 获取驱动器号
            drive_letter = drive_path[0].upper()
            
            # 尝试通过WMI获取分区信息
            try:
                import wmi
                c = wmi.WMI()
                
                # 查找对应的逻辑磁盘
                for logical_disk in c.Win32_LogicalDisk():
                    if logical_disk.DeviceID == f'{drive_letter}:':
                        # 查找对应的分区
                        for partition in c.Win32_DiskPartition():
                            for logical_disk_to_partition in c.Win32_LogicalDiskToPartition():
                                if (logical_disk_to_partition.Dependent.DeviceID == logical_disk.DeviceID and
                                    logical_disk_to_partition.Antecedent.DeviceID == partition.DeviceID):
                                    
                                    # 创建分区信息
                                    start_lba = int(partition.StartingOffset) // 512 if partition.StartingOffset else 0
                                    sectors = int(partition.Size) // 512 if partition.Size else 0
                                    # 判断分区状态：检查是否为系统分区或包含启动文件
                                    is_active = False
                                    try:
                                        # 检查是否为系统分区（包含bootmgr或Windows文件夹）
                                        drive_root = f"{drive_letter}:\\"
                                        if os.path.exists(os.path.join(drive_root, "bootmgr")) or \
                                           os.path.exists(os.path.join(drive_root, "Windows")):
                                            is_active = True
                                        # 或者检查WMI中的BootPartition属性
                                        elif partition.BootPartition:
                                            is_active = True
                                    except:
                                        # 如果检查失败，使用BootPartition属性
                                        is_active = partition.BootPartition
                                    
                                    partition_info = {
                                        'index': partition.Index,
                                        'status': 'Active' if is_active else 'Inactive',
                                        'type': 0x07 if logical_disk.FileSystem == 'NTFS' else 0x0C,  # 假设类型
                                        'type_name': logical_disk.FileSystem or 'Unknown',
                                        'start_lba': start_lba,
                                        'start_sector': start_lba,  # 添加兼容性字段
                                        'sectors': sectors,
                                        'size_human': self._format_size(int(partition.Size)) if partition.Size else '0 B'
                                    }
                                    
                                    return {
                                        'partitions': [partition_info],
                                        'filesystem': logical_disk.FileSystem,
                                        'volume_label': logical_disk.VolumeName or '',
                                        'volume_serial': logical_disk.VolumeSerialNumber or ''
                                    }
            except ImportError:
                # 如果没有wmi模块，使用基本方法
                pass
            
            # 基本方法：创建一个虚拟分区信息
            try:
                size = self._get_drive_size(drive_path)
                sectors = size // 512 if size > 0 else 0
                
                # 判断分区状态：检查是否为系统分区
                is_active = False
                try:
                    drive_root = f"{drive_letter}:\\"
                    if os.path.exists(os.path.join(drive_root, "bootmgr")) or \
                       os.path.exists(os.path.join(drive_root, "Windows")):
                        is_active = True
                except:
                    # 如果检查失败，默认为Active（兼容性）
                    is_active = True
                
                partition_info = {
                    'index': 1,
                    'status': 'Active' if is_active else 'Inactive',
                    'type': 0x07,  # 假设为NTFS
                    'type_name': 'NTFS/FAT32',
                    'start_lba': 0,  # 对于逻辑驱动器，从扇区0开始（相对于分区）
                    'start_sector': 0,  # 添加兼容性字段
                    'sectors': sectors,
                    'size_human': self._format_size(size) if size > 0 else '0 B'
                }
                
                return {
                    'partitions': [partition_info],
                    'filesystem': 'Unknown',
                    'note': '逻辑驱动器分区信息（估算）',
                    'is_logical_drive': True  # 标记为逻辑驱动器
                }
            except:
                return None
                
        except Exception as e:
            return None
    
    def read_sectors(self, disk_path, start_sector, sector_count):
        """读取磁盘扇区"""
        try:
            if sys.platform == 'win32':
                # 检查是否是逻辑驱动器（如 C:\）
                if len(disk_path) == 3 and disk_path[1:] == ':\\':
                    # 逻辑驱动器，需要转换为逻辑驱动器设备路径
                    drive_letter = disk_path[0].upper()
                    logical_drive_path = f'\\\\.\\{drive_letter}:'
                    
                    import win32file
                    handle = win32file.CreateFile(
                        logical_drive_path,
                        win32file.GENERIC_READ,
                        win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                        None,
                        win32file.OPEN_EXISTING,
                        0,
                        None
                    )
                    if handle != win32file.INVALID_HANDLE_VALUE:
                        try:
                            win32file.SetFilePointer(handle, start_sector * 512, win32file.FILE_BEGIN)
                            _, data = win32file.ReadFile(handle, sector_count * 512)
                            win32file.CloseHandle(handle)
                            return data
                        except Exception as e:
                            win32file.CloseHandle(handle)
                            raise e
                    else:
                        raise Exception(f'无法打开逻辑驱动器: {logical_drive_path}')
                        
                elif disk_path.startswith('\\.\\'): 
                    # Windows物理磁盘
                    import win32file
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
                        try:
                            win32file.SetFilePointer(handle, start_sector * 512, win32file.FILE_BEGIN)
                            _, data = win32file.ReadFile(handle, sector_count * 512)
                            win32file.CloseHandle(handle)
                            return data
                        except Exception as e:
                            win32file.CloseHandle(handle)
                            raise e
                    else:
                        raise Exception(f'无法打开磁盘设备: {disk_path}')
                else:
                    # 文件（虚拟磁盘）
                    with open(disk_path, 'rb') as f:
                        f.seek(start_sector * 512)
                        return f.read(sector_count * 512)
            else:
                # Linux设备或文件
                with open(disk_path, 'rb') as f:
                    f.seek(start_sector * 512)
                    return f.read(sector_count * 512)
        except Exception as e:
            raise Exception(f'读取扇区失败: {str(e)}')
    
    def write_sectors(self, disk_path, start_sector, data):
        """写入磁盘扇区"""
        try:
            if sys.platform == 'win32' and disk_path.startswith('\\\\.\\'):
                # Windows物理磁盘
                import win32file
                handle = win32file.CreateFile(
                    disk_path,
                    win32file.GENERIC_WRITE,
                    win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None
                )
                if handle != win32file.INVALID_HANDLE_VALUE:
                    try:
                        win32file.SetFilePointer(handle, start_sector * 512, win32file.FILE_BEGIN)
                        win32file.WriteFile(handle, data)
                        win32file.CloseHandle(handle)
                    except Exception as e:
                        win32file.CloseHandle(handle)
                        raise e
            else:
                # 文件或Linux设备
                with open(disk_path, 'r+b') as f:
                    f.seek(start_sector * 512)
                    f.write(data)
        except Exception as e:
            raise Exception(f'写入扇区失败: {str(e)}')

# 便捷函数
def get_physical_disks():
    """获取物理磁盘列表的便捷函数"""
    manager = DiskManager()
    return manager.get_physical_disks()