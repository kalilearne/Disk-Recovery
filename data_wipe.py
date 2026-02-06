import os
import random
from PyQt5.QtCore import QObject, pyqtSignal

class DataWipe(QObject):
    """数据擦除类"""
    
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
    
    def wipe_disk(self, disk_path, method='zeros', passes=1):
        """擦除磁盘数据"""
        try:
            self.status_updated.emit(f"开始擦除磁盘: {disk_path}")
            self.status_updated.emit(f"擦除方法: {method}, 遍数: {passes}")
            
            # 获取磁盘大小
            disk_size = self._get_disk_size(disk_path)
            if disk_size == 0:
                self.status_updated.emit("磁盘擦除操作取消")
                return False
            
            self.status_updated.emit(f"磁盘大小: {disk_size // (1024*1024)} MB")
            
            # 执行擦除
            for pass_num in range(passes):
                self.status_updated.emit(f"正在执行第 {pass_num + 1}/{passes} 遍擦除...")
                self._wipe_pass(disk_path, disk_size, method, pass_num)
            
            # 验证擦除效果
            self.status_updated.emit("正在验证擦除效果...")
            if self._verify_wipe_completion(disk_path, disk_size, method, passes-1):
                self.status_updated.emit("磁盘擦除完成并验证成功")
            else:
                self.status_updated.emit("警告: 擦除验证失败，部分数据可能未被完全擦除")
            
            return True
        
        except Exception as e:
            self.status_updated.emit(f"磁盘擦除失败: {str(e)}")
            raise e
    
    def wipe_file(self, file_path, method='zeros', passes=3):
        """擦除文件数据"""
        try:
            if not os.path.exists(file_path):
                raise Exception(f"文件不存在: {file_path}")
            
            self.status_updated.emit(f"开始擦除文件: {file_path}")
            
            file_size = os.path.getsize(file_path)
            self.status_updated.emit(f"文件大小: {file_size} 字节")
            
            # 执行擦除
            for pass_num in range(passes):
                self.status_updated.emit(f"正在执行第 {pass_num + 1}/{passes} 遍擦除...")
                self._wipe_file_pass(file_path, file_size, method, pass_num)
            
            # 删除文件
            os.remove(file_path)
            
            self.status_updated.emit("文件擦除完成")
            return True
        
        except Exception as e:
            self.status_updated.emit(f"文件擦除失败: {str(e)}")
            raise e
    
    def wipe_free_space(self, drive_path, method='zeros'):
        """擦除驱动器空闲空间"""
        try:
            self.status_updated.emit(f"开始擦除空闲空间: {drive_path}")
            
            # 创建临时文件填充空闲空间
            temp_files = []
            file_counter = 0
            
            try:
                while True:
                    temp_file_path = os.path.join(drive_path, f"wipe_temp_{file_counter}.tmp")
                    
                    try:
                        with open(temp_file_path, 'wb') as f:
                            chunk_size = 1024 * 1024  # 1MB
                            written = 0
                            
                            while True:
                                data = self._generate_wipe_data(chunk_size, method)
                                f.write(data)
                                written += len(data)
                                
                                if written % (10 * 1024 * 1024) == 0:  # 每10MB更新一次进度
                                    self.status_updated.emit(f"已写入: {written // (1024*1024)} MB")
                        
                        temp_files.append(temp_file_path)
                        file_counter += 1
                        
                    except OSError:
                        # 磁盘空间已满
                        break
            
            finally:
                # 删除临时文件
                self.status_updated.emit("正在清理临时文件...")
                for temp_file in temp_files:
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                    except (OSError, PermissionError) as e:
                        # 临时文件删除失败，继续处理其他文件
                        pass
            
            self.status_updated.emit("空闲空间擦除完成")
            return True
        
        except Exception as e:
            self.status_updated.emit(f"空闲空间擦除失败: {str(e)}")
            raise e
    
    def _get_disk_size(self, disk_path):
        """获取磁盘大小"""
        try:
            # Windows物理磁盘设备特殊处理
            if disk_path.startswith('\\\\.\\PhysicalDrive'):
                return self._get_physical_disk_size(disk_path)
            
            # 检查路径是否存在
            if not os.path.exists(disk_path):
                self.status_updated.emit(f"磁盘路径不存在: {disk_path}")
                return 0
            
            # 对于普通文件或虚拟磁盘文件
            with open(disk_path, 'rb') as f:
                f.seek(0, 2)  # 移动到文件末尾
                size = f.tell()
                if size == 0:
                    self.status_updated.emit(f"警告: 磁盘大小为0，可能是设备文件")
                return size
        except FileNotFoundError:
            self.status_updated.emit(f"磁盘路径错误: {disk_path}")
            return 0
        except PermissionError:
            self.status_updated.emit(f"没有访问权限: {disk_path}")
            return 0
        except Exception as e:
            self.status_updated.emit(f"获取磁盘大小失败: {str(e)}")
            return 0
    
    def _get_physical_disk_size(self, disk_path):
        """获取Windows物理磁盘大小"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # Windows API常量
            GENERIC_READ = 0x80000000
            FILE_SHARE_READ = 0x00000001
            FILE_SHARE_WRITE = 0x00000002
            OPEN_EXISTING = 3
            IOCTL_DISK_GET_DRIVE_GEOMETRY_EX = 0x000700A0
            
            # 打开磁盘设备
            handle = ctypes.windll.kernel32.CreateFileW(
                disk_path,
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                0,
                None
            )
            
            if handle == -1:
                self.status_updated.emit(f"无法打开磁盘设备: {disk_path}")
                return 0
            
            try:
                # 定义结构体
                class DISK_GEOMETRY_EX(ctypes.Structure):
                    _fields_ = [
                        ('Geometry', ctypes.c_byte * 24),  # DISK_GEOMETRY结构
                        ('DiskSize', ctypes.c_int64),      # 磁盘大小
                        ('Data', ctypes.c_byte * 1)        # 附加数据
                    ]
                
                geometry = DISK_GEOMETRY_EX()
                bytes_returned = wintypes.DWORD()
                
                # 调用DeviceIoControl获取磁盘几何信息
                result = ctypes.windll.kernel32.DeviceIoControlW(
                    handle,
                    IOCTL_DISK_GET_DRIVE_GEOMETRY_EX,
                    None,
                    0,
                    ctypes.byref(geometry),
                    ctypes.sizeof(geometry),
                    ctypes.byref(bytes_returned),
                    None
                )
                
                if result:
                    disk_size = geometry.DiskSize
                    self.status_updated.emit(f"检测到物理磁盘大小: {disk_size // (1024*1024)} MB")
                    return disk_size
                else:
                    self.status_updated.emit(f"无法获取磁盘几何信息")
                    return 0
                    
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
                
        except Exception as e:
            self.status_updated.emit(f"获取物理磁盘大小失败: {str(e)}")
            # 回退到文件大小方法
            try:
                with open(disk_path, 'rb') as f:
                    f.seek(0, 2)
                    return f.tell()
            except:
                return 0
    
    def _wipe_pass(self, disk_path, disk_size, method, pass_num):
        """执行一遍磁盘擦除"""
        try:
            chunk_size = 1024 * 1024  # 1MB chunks
            written = 0
            
            # 检查是否为Windows物理磁盘
            if disk_path.startswith('\\\\.\\PhysicalDrive'):
                self._wipe_physical_disk(disk_path, disk_size, method, pass_num)
                return
            
            # 对于普通文件或虚拟磁盘
            self.status_updated.emit(f"开始擦除: {disk_path} (方法: {method}, 第{pass_num+1}遍)")
            
            # 使用二进制写入模式，确保直接写入磁盘
            with open(disk_path, 'r+b', buffering=0) as f:  # 无缓冲模式
                # 确保从磁盘开始位置写入
                f.seek(0)
                
                while written < disk_size:
                    remaining = disk_size - written
                    current_chunk_size = min(chunk_size, remaining)
                    
                    # 生成擦除数据
                    wipe_data = self._generate_wipe_data(current_chunk_size, method, pass_num)
                    
                    # 确保当前位置正确
                    f.seek(written)
                    
                    # 写入数据
                    bytes_written = f.write(wipe_data)
                    if bytes_written != len(wipe_data):
                        raise Exception(f"写入数据不完整: 期望{len(wipe_data)}字节，实际写入{bytes_written}字节")
                    
                    written += bytes_written
                    
                    # 强制刷新到磁盘（无缓冲模式下仍然需要）
                    f.flush()
                    os.fsync(f.fileno())
                    
                    # 更新进度
                    progress = min(100, (written * 100) // disk_size)
                    self.progress_updated.emit(progress)
                    
                    # 每写入10MB输出一次状态
                    if written % (chunk_size * 10) == 0:
                        self.status_updated.emit(f"已写入: {written // (1024*1024)} MB / {disk_size // (1024*1024)} MB")
                        # 验证写入（可选，但会影响性能）
                        if pass_num == 0:
                            self._verify_write(f, written - bytes_written, wipe_data[:min(1024, len(wipe_data))])
                
                # 最终同步确保所有数据写入磁盘
                f.flush()
                os.fsync(f.fileno())
                
                self.status_updated.emit(f"第{pass_num+1}遍擦除完成: {written // (1024*1024)} MB")
                
        except FileNotFoundError:
            self.status_updated.emit(f"磁盘路径错误，无法执行擦除: {disk_path}")
            raise
        except PermissionError:
            self.status_updated.emit(f"没有写入权限，无法执行擦除: {disk_path}")
            raise
        except Exception as e:
            self.status_updated.emit(f"磁盘擦除过程中发生错误: {str(e)}")
            raise
    
    def _wipe_physical_disk(self, disk_path, disk_size, method, pass_num):
        """专门处理Windows物理磁盘的擦除"""
        import ctypes
        from ctypes import wintypes
        
        try:
            self.status_updated.emit(f"开始擦除物理磁盘: {disk_path} (方法: {method}, 第{pass_num+1}遍)")
            
            # Windows API常量
            GENERIC_WRITE = 0x40000000
            OPEN_EXISTING = 3
            FILE_ATTRIBUTE_NORMAL = 0x80
            FILE_FLAG_NO_BUFFERING = 0x20000000
            FILE_FLAG_WRITE_THROUGH = 0x80000000
            
            # 打开物理磁盘
            handle = ctypes.windll.kernel32.CreateFileW(
                disk_path,
                GENERIC_WRITE,
                0,  # 不共享
                None,
                OPEN_EXISTING,
                FILE_FLAG_NO_BUFFERING | FILE_FLAG_WRITE_THROUGH,
                None
            )
            
            if handle == -1:
                error_code = ctypes.windll.kernel32.GetLastError()
                raise Exception(f"无法打开物理磁盘 {disk_path}，错误代码: {error_code}")
            
            try:
                chunk_size = 512 * 1024  # 512KB chunks (必须是512的倍数)
                written = 0
                
                while written < disk_size:
                    remaining = disk_size - written
                    current_chunk_size = min(chunk_size, remaining)
                    
                    # 确保块大小是512的倍数
                    current_chunk_size = (current_chunk_size // 512) * 512
                    if current_chunk_size == 0:
                        break
                    
                    # 生成擦除数据
                    wipe_data = self._generate_wipe_data(current_chunk_size, method, pass_num)
                    
                    # 写入数据
                    bytes_written = wintypes.DWORD()
                    success = ctypes.windll.kernel32.WriteFile(
                        handle,
                        wipe_data,
                        len(wipe_data),
                        ctypes.byref(bytes_written),
                        None
                    )
                    
                    if not success or bytes_written.value != len(wipe_data):
                        error_code = ctypes.windll.kernel32.GetLastError()
                        raise Exception(f"写入失败，错误代码: {error_code}")
                    
                    written += bytes_written.value
                    
                    # 更新进度
                    progress = min(100, (written * 100) // disk_size)
                    self.progress_updated.emit(progress)
                    
                    # 每写入10MB输出一次状态
                    if written % (chunk_size * 20) == 0:
                        self.status_updated.emit(f"已写入: {written // (1024*1024)} MB / {disk_size // (1024*1024)} MB")
                
                self.status_updated.emit(f"第{pass_num+1}遍物理磁盘擦除完成: {written // (1024*1024)} MB")
                
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
                
        except Exception as e:
            self.status_updated.emit(f"物理磁盘擦除失败: {str(e)}")
            raise
    
    def _verify_write(self, file_handle, offset, expected_data):
        """验证写入的数据是否正确"""
        try:
            current_pos = file_handle.tell()
            file_handle.seek(offset)
            read_data = file_handle.read(len(expected_data))
            file_handle.seek(current_pos)
            
            if read_data != expected_data:
                raise Exception(f"数据验证失败: 写入的数据与读取的数据不匹配")
        except Exception as e:
            self.status_updated.emit(f"数据验证警告: {str(e)}")
            # 不抛出异常，只是警告
    
    def _verify_wipe_completion(self, disk_path, disk_size, method, last_pass_num):
         """验证擦除完成情况"""
         try:
             # 生成期望的数据模式
             expected_pattern = self._generate_wipe_data(1024, method, last_pass_num)
             
             # 检查多个位置的数据
             check_positions = [
                 0,  # 开始位置
                 disk_size // 4,  # 1/4位置
                 disk_size // 2,  # 中间位置
                 disk_size * 3 // 4,  # 3/4位置
                 max(0, disk_size - 1024)  # 结束位置
             ]
             
             verification_passed = 0
             total_checks = len(check_positions)
             
             with open(disk_path, 'rb', buffering=0) as f:
                 for pos in check_positions:
                     try:
                         f.seek(pos)
                         read_data = f.read(min(1024, disk_size - pos))
                         
                         # 检查数据是否符合期望模式
                         expected_chunk = expected_pattern[:len(read_data)]
                         
                         if method == 'random':
                             # 对于随机数据，检查是否不全为0或全为1
                             if not (all(b == 0 for b in read_data) or all(b == 255 for b in read_data)):
                                 verification_passed += 1
                         else:
                             # 对于固定模式，检查是否匹配
                             if read_data == expected_chunk:
                                 verification_passed += 1
                                 
                     except Exception as e:
                         self.status_updated.emit(f"验证位置 {pos} 时出错: {str(e)}")
             
             success_rate = (verification_passed / total_checks) * 100
             self.status_updated.emit(f"擦除验证: {verification_passed}/{total_checks} 个检查点通过 ({success_rate:.1f}%)")
             
             # 如果80%以上的检查点通过，认为擦除成功
             return success_rate >= 80.0
             
         except Exception as e:
             self.status_updated.emit(f"擦除验证过程出错: {str(e)}")
             return False
     
    def _wipe_file_pass(self, file_path, file_size, method, pass_num):
         """执行一遍文件擦除"""
         chunk_size = 64 * 1024  # 64KB chunks
         written = 0
         
         # 使用无缓冲模式确保直接写入磁盘
         with open(file_path, 'r+b', buffering=0) as f:
             f.seek(0)  # 确保从文件开始位置写入
             
             while written < file_size:
                 remaining = file_size - written
                 current_chunk_size = min(chunk_size, remaining)
                 
                 # 生成擦除数据
                 wipe_data = self._generate_wipe_data(current_chunk_size, method, pass_num)
                 
                 # 确保当前位置正确
                 f.seek(written)
                 
                 # 写入数据
                 bytes_written = f.write(wipe_data)
                 if bytes_written != len(wipe_data):
                     raise Exception(f"文件写入数据不完整: 期望{len(wipe_data)}字节，实际写入{bytes_written}字节")
                 
                 written += bytes_written
                 
                 # 强制刷新到磁盘
                 f.flush()
                 os.fsync(f.fileno())
                 
                 # 更新进度
                 progress = min(100, (written * 100) // file_size)
                 self.progress_updated.emit(progress)
                 
                 # 验证写入（每1MB验证一次）
                 if pass_num == 0 and written % (1024 * 1024) == 0:
                     self._verify_write(f, written - bytes_written, wipe_data[:min(1024, len(wipe_data))])
             
             # 最终同步确保所有数据写入磁盘
             f.flush()
             os.fsync(f.fileno())
    
    def _generate_wipe_data(self, size, method, pass_num=0):
        """生成擦除数据"""
        if method == 'zeros':
            return b'\x00' * size
        
        elif method == 'ones':
            return b'\xFF' * size
        
        elif method == 'random':
            return bytes([random.randint(0, 255) for _ in range(size)])
        
        elif method == 'dod' or method == 'dod_5220_22_m':
            # DoD 5220.22-M 3遍方法
            if pass_num == 0:
                return b'\x00' * size  # 第一遍：全0
            elif pass_num == 1:
                return b'\xFF' * size  # 第二遍：全1
            else:
                return bytes([random.randint(0, 255) for _ in range(size)])  # 第三遍：随机
        
        elif method == 'dod_3pass':
            # DoD 5220.22-M 3遍方法
            if pass_num == 0:
                return b'\x00' * size  # 第一遍：全0
            elif pass_num == 1:
                return b'\xFF' * size  # 第二遍：全1
            else:
                return bytes([random.randint(0, 255) for _ in range(size)])  # 第三遍：随机
        
        elif method == 'dod_7pass':
            # DoD 5220.22-M 7遍方法
            patterns = [
                b'\x00',  # 全0
                b'\xFF',  # 全1
                b'\x00',  # 全0
                b'\xFF',  # 全1
                b'\x00',  # 全0
                b'\xFF',  # 全1
                None      # 随机
            ]
            
            if pass_num < len(patterns) - 1:
                return patterns[pass_num] * size
            else:
                return bytes([random.randint(0, 255) for _ in range(size)])
        
        elif method == 'gutmann':
            # Gutmann 35遍方法的简化版本
            patterns = [
                b'\x00', b'\xFF', b'\x55', b'\xAA',
                b'\x92', b'\x49', b'\x24', b'\x6D',
                b'\xB6', b'\xDB', b'\x36', b'\x9B',
                b'\x4D', b'\xA6', b'\x53', b'\x29',
                b'\x94', b'\xCA', b'\x65', b'\x32',
                b'\x99', b'\xCC', b'\x66', b'\x33'
            ]
           
            if pass_num < len(patterns):
                return patterns[pass_num] * size
            else:
                return bytes([random.randint(0, 255) for _ in range(size)])
        
        else:
            # 默认使用全0
            return b'\x00' * size
     
    def get_wipe_methods(self):
         """获取可用的擦除方法"""
         return {
             'zeros': '全零擦除 (1遍)',
             'ones': '全一擦除 (1遍)',
             'random': '随机数据擦除 (1遍)',
             'dod_3pass': 'DoD 5220.22-M (3遍)',
             'dod_7pass': 'DoD 5220.22-M (7遍)',
             'gutmann': 'Gutmann方法 (35遍)'
         }
     
    def estimate_wipe_time(self, size_bytes, method):
         """估算擦除时间"""
         # 假设写入速度为50MB/s
         write_speed = 50 * 1024 * 1024  # 50MB/s
         
         passes = 1
         if method == 'dod_3pass':
             passes = 3
         elif method == 'dod_7pass':
             passes = 7
         elif method == 'gutmann':
             passes = 35
         
         total_bytes = size_bytes * passes
         estimated_seconds = total_bytes / write_speed
         
         return {
             'seconds': estimated_seconds,
             'minutes': estimated_seconds / 60,
             'hours': estimated_seconds / 3600,
             'passes': passes
         }