#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import platform
import struct
import traceback
from disk_reader import DiskReader
from file_signature_recovery import FileSignatureRecovery

class FileSystemReader:
    """文件系统读取类，提供对FAT32和NTFS文件系统的读取功能"""
    
    @staticmethod
    def read_mbr(disk_path):
        """读取MBR分区表"""
        try:
            # 读取第一个扇区（MBR）
            mbr_data = DiskReader.read_disk_sector(disk_path, 0, 1)
            if not mbr_data or len(mbr_data) < 512:
                return {'error': '无法读取MBR'}
            
            # 检查MBR签名
            if mbr_data[510:512] != b'\x55\xAA':
                return {'error': 'MBR签名无效'}
            
            # 解析分区表
            partitions = []
            for i in range(4):  # MBR有4个主分区表项
                offset = 446 + i * 16  # 分区表从偏移446开始
                entry = mbr_data[offset:offset+16]
                
                if len(entry) < 16:
                    continue
                
                # 解析分区表项
                status = entry[0]  # 0x80表示活动分区
                partition_type = entry[4]
                lba_start = struct.unpack('<I', entry[8:12])[0]
                sectors = struct.unpack('<I', entry[12:16])[0]
                
                # 跳过空分区
                if partition_type == 0 or sectors == 0:
                    continue
                
                # 确定分区类型
                type_name = FileSystemReader.get_partition_type_name(partition_type)
                
                # 添加分区信息
                partitions.append({
                    'index': i + 1,
                    'status': '活动' if status == 0x80 else '非活动',
                    'type': partition_type,
                    'type_name': type_name,
                    'start_lba': lba_start,
                    'sectors': sectors,
                    'size': sectors * 512,  # 假设扇区大小为512字节
                    'size_human': FileSystemReader.format_size(sectors * 512)
                })
            
            return {
                'signature_valid': True,
                'partitions': partitions
            }
        except Exception as e:
            print(f"读取MBR错误: {e}")
            traceback.print_exc()
            return {'error': f'读取MBR错误: {str(e)}'}
    
    @staticmethod
    def get_partition_type_name(type_code):
        """获取分区类型名称"""
        partition_types = {
            0x00: "空分区",
            0x01: "FAT12",
            0x04: "FAT16 (小于32MB)",
            0x05: "扩展分区",
            0x06: "FAT16 (大于32MB)",
            0x07: "NTFS/exFAT",
            0x0B: "FAT32 (CHS)",
            0x0C: "FAT32 (LBA)",
            0x0E: "FAT16 (LBA)",
            0x0F: "扩展分区 (LBA)",
            0x82: "Linux Swap",
            0x83: "Linux",
            0x8E: "Linux LVM",
            0xA5: "FreeBSD",
            0xA6: "OpenBSD",
            0xA9: "NetBSD",
            0xAF: "Apple HFS/HFS+",
            0xEE: "GPT保护分区",
            0xEF: "EFI系统分区"
        }
        return partition_types.get(type_code, f"未知类型 (0x{type_code:02X})")
    
    @staticmethod
    def format_size(size_bytes):
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    
    @staticmethod
    def read_fat32_boot_sector(disk_path, partition_start=0):
        """读取FAT32引导扇区"""
        try:
            # 读取引导扇区
            boot_sector = DiskReader.read_disk_sector(disk_path, partition_start, 1)
            if not boot_sector or len(boot_sector) < 512:
                return {'error': '无法读取引导扇区'}
            
            # 检查FAT32签名
            if boot_sector[0x52:0x5A] != b'FAT32   ':
                return {'error': '不是FAT32文件系统'}
            
            # 解析引导扇区
            bytes_per_sector = struct.unpack('<H', boot_sector[0x0B:0x0D])[0]
            sectors_per_cluster = boot_sector[0x0D]
            reserved_sectors = struct.unpack('<H', boot_sector[0x0E:0x10])[0]
            num_fats = boot_sector[0x10]
            root_entries = struct.unpack('<H', boot_sector[0x11:0x13])[0]
            total_sectors_small = struct.unpack('<H', boot_sector[0x13:0x15])[0]
            media_descriptor = boot_sector[0x15]
            sectors_per_fat_16 = struct.unpack('<H', boot_sector[0x16:0x18])[0]
            sectors_per_track = struct.unpack('<H', boot_sector[0x18:0x1A])[0]
            num_heads = struct.unpack('<H', boot_sector[0x1A:0x1C])[0]
            hidden_sectors = struct.unpack('<I', boot_sector[0x1C:0x20])[0]
            total_sectors_large = struct.unpack('<I', boot_sector[0x20:0x24])[0]
            
            # FAT32特有字段
            sectors_per_fat_32 = struct.unpack('<I', boot_sector[0x24:0x28])[0]
            ext_flags = struct.unpack('<H', boot_sector[0x28:0x2A])[0]
            fs_version = struct.unpack('<H', boot_sector[0x2A:0x2C])[0]
            root_cluster = struct.unpack('<I', boot_sector[0x2C:0x30])[0]
            fs_info_sector = struct.unpack('<H', boot_sector[0x30:0x32])[0]
            backup_boot_sector = struct.unpack('<H', boot_sector[0x32:0x34])[0]
            
            # 计算一些有用的值
            total_sectors = total_sectors_large if total_sectors_small == 0 else total_sectors_small
            fat_size = sectors_per_fat_32
            first_data_sector = reserved_sectors + (num_fats * fat_size)
            first_fat_sector = reserved_sectors
            data_sectors = total_sectors - first_data_sector
            total_clusters = data_sectors // sectors_per_cluster
            
            # 卷标
            volume_label = boot_sector[0x47:0x52].decode('ascii', errors='replace').strip()
            
            return {
                'filesystem': 'FAT32',
                'bytes_per_sector': bytes_per_sector,
                'sectors_per_cluster': sectors_per_cluster,
                'cluster_size': bytes_per_sector * sectors_per_cluster,
                'reserved_sectors': reserved_sectors,
                'num_fats': num_fats,
                'root_entries': root_entries,
                'total_sectors': total_sectors,
                'media_descriptor': f"0x{media_descriptor:02X}",
                'sectors_per_fat': sectors_per_fat_32,
                'sectors_per_track': sectors_per_track,
                'num_heads': num_heads,
                'hidden_sectors': hidden_sectors,
                'root_cluster': root_cluster,
                'fs_info_sector': fs_info_sector,
                'backup_boot_sector': backup_boot_sector,
                'first_fat_sector': first_fat_sector,
                'first_data_sector': first_data_sector,
                'data_sectors': data_sectors,
                'total_clusters': total_clusters,
                'volume_label': volume_label,
                'total_size': total_sectors * bytes_per_sector,
                'total_size_human': FileSystemReader.format_size(total_sectors * bytes_per_sector)
            }
        except Exception as e:
            print(f"读取FAT32引导扇区错误: {e}")
            traceback.print_exc()
            return {'error': f'读取FAT32引导扇区错误: {str(e)}'}
    
    @staticmethod
    def read_ntfs_boot_sector(disk_path, partition_start=0):
        """读取NTFS引导扇区"""
        try:
            # 读取引导扇区
            boot_sector = DiskReader.read_disk_sector(disk_path, partition_start, 1)
            if not boot_sector or len(boot_sector) < 512:
                return {'error': '无法读取引导扇区'}
            
            # 检查NTFS签名
            if boot_sector[3:7] != b'NTFS':
                return {'error': '不是NTFS文件系统'}
            
            # 解析引导扇区
            bytes_per_sector = struct.unpack('<H', boot_sector[0x0B:0x0D])[0]
            sectors_per_cluster = boot_sector[0x0D]
            reserved_sectors = struct.unpack('<H', boot_sector[0x0E:0x10])[0]
            media_descriptor = boot_sector[0x15]
            sectors_per_track = struct.unpack('<H', boot_sector[0x18:0x1A])[0]
            num_heads = struct.unpack('<H', boot_sector[0x1A:0x1C])[0]
            hidden_sectors = struct.unpack('<I', boot_sector[0x1C:0x20])[0]
            
            # NTFS特有字段
            total_sectors = struct.unpack('<Q', boot_sector[0x28:0x30])[0]
            mft_cluster = struct.unpack('<Q', boot_sector[0x30:0x38])[0]
            mft_mirror_cluster = struct.unpack('<Q', boot_sector[0x38:0x40])[0]
            clusters_per_mft_record = boot_sector[0x40]
            clusters_per_index_buffer = boot_sector[0x44]
            
            # 计算MFT记录大小
            if clusters_per_mft_record >= 0:
                mft_record_size = clusters_per_mft_record * sectors_per_cluster * bytes_per_sector
            else:
                mft_record_size = 2 ** abs(clusters_per_mft_record)
            
            # 卷序列号
            volume_serial = struct.unpack('<Q', boot_sector[0x48:0x50])[0]
            
            return {
                'filesystem': 'NTFS',
                'bytes_per_sector': bytes_per_sector,
                'sectors_per_cluster': sectors_per_cluster,
                'cluster_size': bytes_per_sector * sectors_per_cluster,
                'reserved_sectors': reserved_sectors,
                'media_descriptor': f"0x{media_descriptor:02X}",
                'sectors_per_track': sectors_per_track,
                'num_heads': num_heads,
                'hidden_sectors': hidden_sectors,
                'total_sectors': total_sectors,
                'mft_cluster': mft_cluster,
                'mft_mirror_cluster': mft_mirror_cluster,
                'mft_record_size': mft_record_size,
                'clusters_per_index_buffer': clusters_per_index_buffer,
                'volume_serial': f"{volume_serial:016X}",
                'total_size': total_sectors * bytes_per_sector,
                'total_size_human': FileSystemReader.format_size(total_sectors * bytes_per_sector)
            }
        except Exception as e:
            print(f"读取NTFS引导扇区错误: {e}")
            traceback.print_exc()
            return {'error': f'读取NTFS引导扇区错误: {str(e)}'}
    
    @staticmethod
    def detect_filesystem(disk_path, partition_start=0):
        """检测文件系统类型"""
        try:
            # 读取引导扇区
            boot_sector = DiskReader.read_disk_sector(disk_path, partition_start, 1)
            if not boot_sector or len(boot_sector) < 512:
                return {'error': '无法读取引导扇区'}
            
            # 检查NTFS签名
            if boot_sector[3:7] == b'NTFS':
                return {'filesystem': 'NTFS'}
            
            # 检查FAT32签名
            if boot_sector[0x52:0x5A] == b'FAT32   ':
                return {'filesystem': 'FAT32'}
            
            # 检查FAT16签名
            if boot_sector[0x36:0x3E] == b'FAT16   ':
                return {'filesystem': 'FAT16'}
            
            # 检查FAT12签名
            if boot_sector[0x36:0x3E] == b'FAT12   ':
                return {'filesystem': 'FAT12'}
            
            # 检查exFAT签名
            if boot_sector[3:8] == b'EXFAT':
                return {'filesystem': 'exFAT'}
            
            # 检查EXT文件系统
            if boot_sector[0x438:0x43A] == b'\x53\xEF':
                return {'filesystem': 'EXT'}
            
            return {'filesystem': '未知'}
        except Exception as e:
            print(f"检测文件系统错误: {e}")
            traceback.print_exc()
            return {'error': f'检测文件系统错误: {str(e)}'}
    
    @staticmethod
    def read_universal_filesystem(disk_path, partition_start=0):
        """通用文件系统读取"""
        try:
            # 检测文件系统类型
            fs_info = FileSystemReader.detect_filesystem(disk_path, partition_start)
            
            if 'error' in fs_info:
                return fs_info
            
            filesystem = fs_info.get('filesystem', '未知')
            
            # 根据文件系统类型读取详细信息
            if filesystem == 'NTFS':
                return FileSystemReader.read_ntfs_boot_sector(disk_path, partition_start)
            elif filesystem == 'FAT32':
                return FileSystemReader.read_fat32_boot_sector(disk_path, partition_start)
            elif filesystem == '未知':
                # 尝试读取MBR
                mbr_info = FileSystemReader.read_mbr(disk_path)
                
                # 如果MBR读取成功，返回MBR信息
                if 'error' not in mbr_info:
                    return {
                        'filesystem': 'MBR',
                        'mbr_info': mbr_info
                    }
                
                # 如果MBR读取失败，尝试使用文件签名扫描
                print("尝试使用文件签名扫描...")
                
                # 读取前1000个扇区进行扫描
                scan_data = b''
                for i in range(1000):
                    sector_data = DiskReader.read_disk_sector(disk_path, partition_start + i, 1)
                    if not sector_data:
                        break
                    scan_data += sector_data
                    if len(scan_data) >= 512000:  # 限制扫描数据大小
                        break
                
                # 在扫描数据中查找常见文件签名
                found_files = []
                for sig, info in FileSignatureRecovery.DETAILED_SIGNATURES.items():
                    sig_len = len(sig)
                    offset = 0
                    while True:
                        pos = scan_data.find(sig, offset)
                        if pos == -1:
                            break
                        
                        # 计算文件在磁盘中的实际偏移量
                        file_offset = partition_start * 512 + pos
                        
                        # 获取用于文件大小估算的数据
                        analysis_size = min(10 * 1024 * 1024, len(scan_data) - pos)
                        analysis_data = scan_data[pos:pos + analysis_size]
                        
                        # 智能估算文件大小
                        estimated_size = FileSignatureRecovery.estimate_file_size(
                            analysis_data, info, file_offset
                        )
                        
                        # 记录找到的文件
                        found_files.append({
                            'type': info['type'],
                            'ext': info['ext'],
                            'desc': info['desc'],
                            'offset': file_offset,
                            'estimated_size': estimated_size
                        })
                        
                        # 移动偏移量，继续查找
                        offset = pos + sig_len
                
                # 按类型组织找到的文件
                files_by_type = {}
                for file in found_files:
                    file_type = file['type']
                    if file_type not in files_by_type:
                        files_by_type[file_type] = []
                    files_by_type[file_type].append(file)
                
                return {
                    'filesystem': '未知',
                    'scan_result': {
                        'found_files': found_files,
                        'files_by_type': files_by_type
                    }
                }
            else:
                return {
                    'filesystem': filesystem,
                    'message': f'暂不支持读取{filesystem}文件系统详细信息'
                }
        except Exception as e:
            print(f"读取文件系统错误: {e}")
            traceback.print_exc()
            return {'error': f'读取文件系统错误: {str(e)}'}