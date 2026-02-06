import os
import struct
from PyQt5.QtCore import QObject, pyqtSignal

class FileRecovery(QObject):
    """文件恢复类"""
    
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        
        # 文件签名定义
        self.file_signatures = {
            'jpg': {
                'header': [b'\xff\xd8\xff'],
                'footer': [b'\xff\xd9'],
                'extension': '.jpg'
            },
            'png': {
                'header': [b'\x89PNG\r\n\x1a\n'],
                'footer': [b'IEND\xaeB`\x82'],
                'extension': '.png'
            },
            'pdf': {
                'header': [b'%PDF'],
                'footer': [b'%%EOF'],
                'extension': '.pdf'
            },
            'zip': {
                'header': [b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'],
                'footer': [b'PK\x05\x06'],
                'extension': '.zip'
            },
            'rar': {
                'header': [b'Rar!\x1a\x07\x00', b'Rar!\x1a\x07\x01\x00'],
                'footer': [],
                'extension': '.rar'
            },
            'doc': {
                'header': [b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'],
                'footer': [],
                'extension': '.doc'
            },
            'docx': {
                'header': [b'PK\x03\x04'],
                'footer': [b'PK\x05\x06'],
                'extension': '.docx'
            },
            'xls': {
                'header': [b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'],
                'footer': [],
                'extension': '.xls'
            },
            'xlsx': {
                'header': [b'PK\x03\x04'],
                'footer': [b'PK\x05\x06'],
                'extension': '.xlsx'
            }
        }
    
    def recover_by_signature(self, disk_path, output_dir, file_types=None, chunk_size=1024*1024):
        """通过文件签名恢复文件"""
        if file_types is None:
            file_types = list(self.file_signatures.keys())
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        recovered_files = []
        
        try:
            # 检查磁盘路径是否存在
            if not os.path.exists(disk_path):
                error_msg = f"磁盘路径不存在: {disk_path}"
                self.status_updated.emit(error_msg)
                raise FileNotFoundError(error_msg)
            
            # 获取磁盘大小
            try:
                if os.path.isfile(disk_path):
                    disk_size = os.path.getsize(disk_path)
                else:
                    # 对于设备文件，尝试获取大小
                    disk_size = self._get_device_size(disk_path)
                
                if disk_size == 0:
                    self.status_updated.emit("无法获取磁盘大小")
                    return []
            except Exception as e:
                self.status_updated.emit(f"获取磁盘大小失败: {str(e)}")
                return []
            
            self.status_updated.emit(f"开始扫描磁盘，大小: {self._format_size(disk_size)}")
            
            with open(disk_path, 'rb') as disk_file:
                offset = 0
                file_counter = {}
                
                while offset < disk_size:
                    # 读取数据块
                    chunk = disk_file.read(chunk_size)
                    if not chunk:
                        break
                    
                    # 更新进度
                    progress = int((offset / disk_size) * 100)
                    self.progress_updated.emit(progress)
                    self.status_updated.emit(f"扫描进度: {progress}%, 偏移: 0x{offset:08X}")
                    
                    # 在数据块中搜索文件签名
                    for file_type in file_types:
                        if file_type in self.file_signatures:
                            signatures = self.file_signatures[file_type]
                            
                            for header in signatures['header']:
                                pos = 0
                                while True:
                                    pos = chunk.find(header, pos)
                                    if pos == -1:
                                        break
                                    
                                    file_offset = offset + pos
                                    
                                    # 尝试恢复文件
                                    recovered_file = self._recover_file(
                                        disk_file, file_offset, file_type, 
                                        signatures, output_dir, file_counter
                                    )
                                    
                                    if recovered_file:
                                        recovered_files.append(recovered_file)
                                        self.status_updated.emit(
                                            f"恢复文件: {os.path.basename(recovered_file)}"
                                        )
                                    
                                    pos += 1
                    
                    offset += chunk_size
            
            self.status_updated.emit(f"恢复完成，共恢复 {len(recovered_files)} 个文件")
            
        except FileNotFoundError as e:
            # 磁盘路径不存在，直接返回空列表
            self.status_updated.emit(f"磁盘路径错误: {str(e)}")
            return []
        except Exception as e:
            self.status_updated.emit(f"恢复过程中出错: {str(e)}")
            print(f"文件恢复异常: {e}")
            import traceback
            traceback.print_exc()
            return []
        
        return recovered_files
    
    def _recover_file(self, disk_file, offset, file_type, signatures, output_dir, file_counter):
        """恢复单个文件"""
        try:
            # 保存当前位置
            current_pos = disk_file.tell()
            
            # 移动到文件开始位置
            disk_file.seek(offset)
            
            # 读取文件数据
            max_file_size = 100 * 1024 * 1024  # 最大100MB
            file_data = b''
            
            if signatures['footer']:
                # 有结束标志的文件类型
                for footer in signatures['footer']:
                    disk_file.seek(offset)
                    data = disk_file.read(max_file_size)
                    
                    footer_pos = data.find(footer)
                    if footer_pos != -1:
                        file_data = data[:footer_pos + len(footer)]
                        break
            
            if not file_data:
                # 没有结束标志或未找到结束标志，使用启发式方法
                disk_file.seek(offset)
                file_data = self._extract_file_heuristic(disk_file, file_type, max_file_size)
            
            # 恢复当前位置
            disk_file.seek(current_pos)
            
            if file_data and len(file_data) > 100:  # 至少100字节
                # 生成文件名
                if file_type not in file_counter:
                    file_counter[file_type] = 0
                file_counter[file_type] += 1
                
                extension = signatures['extension']
                filename = f"recovered_{file_type}_{file_counter[file_type]:04d}_{offset:08X}{extension}"
                filepath = os.path.join(output_dir, filename)
                
                # 保存文件
                with open(filepath, 'wb') as f:
                    f.write(file_data)
                
                return filepath
        
        except Exception as e:
            # 恢复位置
            try:
                disk_file.seek(current_pos)
            except (OSError, IOError) as e:
                # 磁盘定位失败，跳过
                pass
        
        return None
    
    def _extract_file_heuristic(self, disk_file, file_type, max_size):
        """使用启发式方法提取文件"""
        data = disk_file.read(max_size)
        
        if file_type == 'jpg':
            # JPEG文件：查找下一个JPEG头或文件结束
            next_jpg = data.find(b'\xff\xd8\xff', 1)
            if next_jpg != -1:
                return data[:next_jpg]
        
        elif file_type == 'png':
            # PNG文件：查找IEND块
            iend_pos = data.find(b'IEND')
            if iend_pos != -1:
                return data[:iend_pos + 8]  # IEND + CRC
        
        elif file_type in ['zip', 'docx', 'xlsx']:
            # ZIP格式文件：查找中央目录结束记录
            eocd_pos = data.rfind(b'PK\x05\x06')
            if eocd_pos != -1:
                return data[:eocd_pos + 22]  # EOCD最小长度
        
        # 默认返回固定大小
        return data[:min(len(data), 1024 * 1024)]  # 1MB
    
    def _get_device_size(self, device_path):
        """获取设备大小"""
        try:
            if os.name == 'nt':  # Windows
                import win32file
                handle = win32file.CreateFile(
                    device_path,
                    0,
                    win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None
                )
                if handle != win32file.INVALID_HANDLE_VALUE:
                    try:
                        size = win32file.GetFileSize(handle)
                        win32file.CloseHandle(handle)
                        return size if size > 0 else 1024 * 1024 * 1024  # 如果获取失败，返回默认1GB
                    except:
                        win32file.CloseHandle(handle)
                        return 0  # 获取失败返回0
                else:
                    return 0  # 无法打开设备返回0
            else:  # Linux/Unix
                with open(device_path, 'rb') as f:
                    f.seek(0, 2)  # 移动到文件末尾
                    return f.tell()
        except:
            return 0  # 异常时返回0
        
        return 0  # 默认返回0表示无法获取大小
    
    def _format_size(self, size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f'{size:.1f} {unit}'
            size /= 1024.0
        return f'{size:.1f} PB'