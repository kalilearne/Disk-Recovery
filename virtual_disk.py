import os
import struct
from PyQt5.QtCore import QObject, pyqtSignal

class VirtualDisk(QObject):
    """虚拟磁盘管理类"""
    
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
    
    def create_disk_image(self, source_disk, output_path, image_type='raw'):
        """创建磁盘镜像"""
        try:
            self.status_updated.emit(f"正在创建磁盘镜像: {output_path}")
            
            with open(source_disk, 'rb') as source:
                with open(output_path, 'wb') as output:
                    total_size = self._get_disk_size(source)
                    copied_size = 0
                    chunk_size = 1024 * 1024  # 1MB chunks
                    
                    while True:
                        chunk = source.read(chunk_size)
                        if not chunk:
                            break
                        
                        output.write(chunk)
                        copied_size += len(chunk)
                        
                        if total_size > 0:
                            progress = min(100, (copied_size * 100) // total_size)
                            self.progress_updated.emit(progress)
                    
                    self.status_updated.emit(f"磁盘镜像创建完成: {output_path}")
                    return output_path
        
        except Exception as e:
            self.status_updated.emit(f"创建磁盘镜像失败: {str(e)}")
            raise e
    
    def mount_disk_image(self, image_path):
        """挂载磁盘镜像"""
        try:
            self.status_updated.emit(f"正在挂载磁盘镜像: {image_path}")
            
            # 检查镜像文件
            if not os.path.exists(image_path):
                raise Exception(f"镜像文件不存在: {image_path}")
            
            # 分析镜像类型
            image_info = self._analyze_disk_image(image_path)
            
            self.status_updated.emit(f"磁盘镜像挂载成功: {image_info['type']}")
            return image_info
        
        except Exception as e:
            self.status_updated.emit(f"挂载磁盘镜像失败: {str(e)}")
            raise e
    
    def create_virtual_partition(self, size_mb, filesystem='FAT32', output_path=None):
        """创建虚拟分区"""
        try:
            if not output_path:
                output_path = f"virtual_partition_{filesystem.lower()}_{size_mb}mb.img"
            
            self.status_updated.emit(f"正在创建虚拟分区: {filesystem} ({size_mb}MB)")
            
            size_bytes = size_mb * 1024 * 1024
            
            with open(output_path, 'wb') as f:
                if filesystem.upper() == 'FAT32':
                    self._create_fat32_partition(f, size_bytes)
                elif filesystem.upper() == 'NTFS':
                    self._create_ntfs_partition(f, size_bytes)
                else:
                    # 创建空分区
                    f.write(b'\x00' * size_bytes)
            
            self.status_updated.emit(f"虚拟分区创建完成: {output_path}")
            return output_path
        
        except Exception as e:
            self.status_updated.emit(f"创建虚拟分区失败: {str(e)}")
            raise e
    
    def _get_disk_size(self, disk_file):
        """获取磁盘大小"""
        try:
            current_pos = disk_file.tell()
            disk_file.seek(0, 2)  # 移动到文件末尾
            size = disk_file.tell()
            disk_file.seek(current_pos)  # 恢复原位置
            return size
        except:
            return 0
    
    def _analyze_disk_image(self, image_path):
        """分析磁盘镜像"""
        info = {
            'path': image_path,
            'size': os.path.getsize(image_path),
            'type': 'Unknown',
            'partitions': []
        }
        
        try:
            with open(image_path, 'rb') as f:
                # 读取前512字节
                header = f.read(512)
                
                if len(header) < 512:
                    info['type'] = 'Invalid'
                    return info
                
                # 检查MBR签名
                if header[510:512] == b'\x55\xaa':
                    info['type'] = 'MBR Disk'
                    info['partitions'] = self._parse_mbr_partitions(header)
                
                # 检查文件系统签名
                elif header[3:11] == b'NTFS    ':
                    info['type'] = 'NTFS Partition'
                elif b'FAT32' in header[82:90]:
                    info['type'] = 'FAT32 Partition'
                elif header[54:59] == b'FAT16':
                    info['type'] = 'FAT16 Partition'
                else:
                    info['type'] = 'Raw Data'
        
        except Exception as e:
            info['type'] = f'Error: {str(e)}'
        
        return info
    
    def _parse_mbr_partitions(self, mbr_data):
        """解析MBR分区表"""
        partitions = []
        
        for i in range(4):
            offset = 446 + i * 16
            partition_entry = mbr_data[offset:offset + 16]
            
            if len(partition_entry) < 16:
                continue
            
            partition_type = partition_entry[4]
            if partition_type == 0:
                continue
            
            start_lba = struct.unpack('<L', partition_entry[8:12])[0]
            size_sectors = struct.unpack('<L', partition_entry[12:16])[0]
            
            partition_info = {
                'index': i + 1,
                'type': self._get_partition_type_name(partition_type),
                'type_code': partition_type,
                'start_lba': start_lba,
                'size_sectors': size_sectors,
                'size_mb': (size_sectors * 512) // (1024 * 1024)
            }
            
            partitions.append(partition_info)
        
        return partitions
    
    def _get_partition_type_name(self, type_code):
        """获取分区类型名称"""
        partition_types = {
            0x01: 'FAT12',
            0x04: 'FAT16 (< 32MB)',
            0x06: 'FAT16',
            0x07: 'NTFS/HPFS',
            0x0B: 'FAT32',
            0x0C: 'FAT32 (LBA)',
            0x0E: 'FAT16 (LBA)',
            0x0F: 'Extended (LBA)',
            0x82: 'Linux Swap',
            0x83: 'Linux',
            0x8E: 'Linux LVM',
            0xEE: 'GPT Protective'
        }
        
        return partition_types.get(type_code, f'Unknown (0x{type_code:02X})')
    
    def _create_fat32_partition(self, file_obj, size_bytes):
        """创建FAT32分区"""
        # 计算参数
        bytes_per_sector = 512
        sectors_per_cluster = 8
        reserved_sectors = 32
        num_fats = 2
        
        total_sectors = size_bytes // bytes_per_sector
        sectors_per_fat = max(1, (total_sectors - reserved_sectors) // (sectors_per_cluster * 65536 + num_fats))
        
        # 创建引导扇区
        boot_sector = bytearray(512)
        
        # 跳转指令
        boot_sector[0:3] = b'\xEB\x58\x90'
        
        # OEM标识
        boot_sector[3:11] = b'MSWIN4.1'
        
        # BPB (BIOS Parameter Block)
        struct.pack_into('<H', boot_sector, 11, bytes_per_sector)  # 每扇区字节数
        boot_sector[13] = sectors_per_cluster  # 每簇扇区数
        struct.pack_into('<H', boot_sector, 14, reserved_sectors)  # 保留扇区数
        boot_sector[16] = num_fats  # FAT表数量
        struct.pack_into('<H', boot_sector, 17, 0)  # 根目录项数 (FAT32为0)
        struct.pack_into('<H', boot_sector, 19, 0)  # 总扇区数 (小于65536时使用)
        boot_sector[21] = 0xF8  # 媒体描述符
        struct.pack_into('<H', boot_sector, 22, 0)  # 每FAT扇区数 (FAT32为0)
        struct.pack_into('<H', boot_sector, 24, 63)  # 每磁道扇区数
        struct.pack_into('<H', boot_sector, 26, 255)  # 磁头数
        struct.pack_into('<L', boot_sector, 28, 0)  # 隐藏扇区数
        struct.pack_into('<L', boot_sector, 32, total_sectors)  # 总扇区数
        
        # FAT32扩展BPB
        struct.pack_into('<L', boot_sector, 36, sectors_per_fat)  # 每FAT扇区数
        struct.pack_into('<H', boot_sector, 40, 0)  # 扩展标志
        struct.pack_into('<H', boot_sector, 42, 0)  # 文件系统版本
        struct.pack_into('<L', boot_sector, 44, 2)  # 根目录簇号
        struct.pack_into('<H', boot_sector, 48, 1)  # 文件系统信息扇区
        struct.pack_into('<H', boot_sector, 50, 6)  # 备份引导扇区
        
        # 驱动器号和签名
        boot_sector[64] = 0x80  # 驱动器号
        boot_sector[66] = 0x29  # 扩展引导签名
        struct.pack_into('<L', boot_sector, 67, 0x12345678)  # 卷序列号
        boot_sector[71:82] = b'NO NAME    '  # 卷标
        boot_sector[82:90] = b'FAT32   '  # 文件系统类型
        
        # 引导签名
        boot_sector[510:512] = b'\x55\xAA'
        
        # 写入引导扇区
        file_obj.write(boot_sector)
        
        # 写入剩余的保留扇区
        for i in range(1, reserved_sectors):
            file_obj.write(b'\x00' * bytes_per_sector)
        
        # 写入FAT表
        fat_data = bytearray(sectors_per_fat * bytes_per_sector)
        fat_data[0:4] = b'\xF8\xFF\xFF\x0F'  # 媒体描述符和EOC
        fat_data[4:8] = b'\xFF\xFF\xFF\xFF'  # 根目录簇链结束
        
        for i in range(num_fats):
            file_obj.write(fat_data)
        
        # 写入数据区
        data_sectors = total_sectors - reserved_sectors - num_fats * sectors_per_fat
        for i in range(data_sectors):
            file_obj.write(b'\x00' * bytes_per_sector)
    
    def _create_ntfs_partition(self, file_obj, size_bytes):
        """创建NTFS分区"""
        # 计算参数
        bytes_per_sector = 512
        sectors_per_cluster = 8
        total_sectors = size_bytes // bytes_per_sector
        
        # 创建引导扇区
        boot_sector = bytearray(512)
        
        # 跳转指令
        boot_sector[0:3] = b'\xEB\x52\x90'
        
        # OEM标识
        boot_sector[3:11] = b'NTFS    '
        
        # BPB
        struct.pack_into('<H', boot_sector, 11, bytes_per_sector)  # 每扇区字节数
        boot_sector[13] = sectors_per_cluster  # 每簇扇区数
        struct.pack_into('<H', boot_sector, 14, 0)  # 保留扇区数
        boot_sector[16] = 0  # FAT表数量
        struct.pack_into('<H', boot_sector, 17, 0)  # 根目录项数
        struct.pack_into('<H', boot_sector, 19, 0)  # 总扇区数 (小值)
        boot_sector[21] = 0xF8  # 媒体描述符
        struct.pack_into('<H', boot_sector, 22, 0)  # 每FAT扇区数
        struct.pack_into('<H', boot_sector, 24, 63)  # 每磁道扇区数
        struct.pack_into('<H', boot_sector, 26, 255)  # 磁头数
        struct.pack_into('<L', boot_sector, 28, 0)  # 隐藏扇区数
        struct.pack_into('<L', boot_sector, 32, 0)  # 总扇区数 (大值)
        
        # NTFS扩展BPB
        struct.pack_into('<Q', boot_sector, 40, total_sectors)  # 总扇区数
        struct.pack_into('<Q', boot_sector, 48, total_sectors // 2)  # MFT簇号
        struct.pack_into('<Q', boot_sector, 56, total_sectors // 4)  # MFT镜像簇号
        
        # 引导签名
        boot_sector[510:512] = b'\x55\xAA'
        
        # 写入引导扇区
        file_obj.write(boot_sector)
        
        # 写入剩余扇区
        for i in range(1, total_sectors):
            file_obj.write(b'\x00' * bytes_per_sector)