#!/usr/bin/env python
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (
    QTextEdit, QTreeWidget, QTreeWidgetItem, QHeaderView, QWidget, 
    QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QSplitter,
    QPushButton, QComboBox, QCheckBox, QFileDialog, QMessageBox,
    QTabWidget, QGroupBox, QRadioButton, QSpinBox, QLineEdit,
    QFormLayout, QDialog, QDialogButtonBox, QApplication
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt5.QtGui import QFont, QColor, QTextCursor, QIcon, QPixmap
import os
import platform
import threading
import traceback

class HexViewer(QTextEdit):
    """十六进制查看器组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont('Courier New', 10))
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.current_offset = 0
        self.bytes_per_line = 16
        self.total_size = 0
        self.data = b''
    
    def set_data(self, data, offset=0):
        """设置要显示的数据"""
        self.data = data
        self.total_size = len(data)
        self.current_offset = offset
        self.update_view()
    
    def load_data_from_disk(self, disk_path, offset, size=1024):
        """从磁盘加载数据"""
        try:
            from disk_utils import DiskManager
            
            disk_manager = DiskManager()
            
            # 计算起始扇区和扇区数
            start_sector = offset // 512
            sector_count = (size + 511) // 512  # 向上取整
            
            # 读取扇区数据
            data = disk_manager.read_sectors(disk_path, start_sector, sector_count)
            
            # 检查返回的数据类型
            if not isinstance(data, (bytes, bytearray)):
                raise Exception(f"读取数据类型错误: 期望bytes，实际得到{type(data)}")
            
            # 如果偏移量不是扇区对齐的，需要调整数据
            sector_offset = offset % 512
            if sector_offset > 0:
                data = data[sector_offset:]
            
            # 截取到指定大小
            if len(data) > size:
                data = data[:size]
            
            self.set_data(data, offset)
                
        except Exception as e:
            error_msg = f"读取磁盘数据失败: {str(e)}"
            self.setText(error_msg)
    
    def _create_sample_disk_data(self, disk_path, offset, size):
        """创建示例磁盘数据"""
        # 创建模拟的磁盘数据
        if offset == 0:
            # 模拟MBR/引导扇区
            sample_data = bytearray(size)
            # 添加一些典型的引导扇区标识
            sample_data[0:3] = b'\xEB\x3C\x90'  # 跳转指令
            sample_data[3:11] = b'MSWIN4.1'    # OEM标识
            sample_data[510:512] = b'\x55\xAA'  # 引导签名
            # 添加一些文本信息
            info_text = f"Disk: {disk_path} at offset {offset:08X}".encode('ascii')
            sample_data[100:100+len(info_text)] = info_text
        else:
            # 其他偏移量的模拟数据
            sample_data = bytearray(size)
            for i in range(0, size, 16):
                # 创建有规律的数据模式
                pattern = f"OFFSET_{offset+i:08X}".encode('ascii')
                end_pos = min(i + len(pattern), size)
                sample_data[i:end_pos] = pattern[:end_pos-i]
        
        self.set_data(bytes(sample_data), offset)
    
    def update_view(self):
        """更新视图"""
        if not self.data:
            self.setText("无数据可显示")
            return
        
        text = ""
        for i in range(0, len(self.data), self.bytes_per_line):
            # 地址列
            addr = self.current_offset + i
            text += f"{addr:08X}: "
            
            # 十六进制列
            hex_part = ""
            for j in range(self.bytes_per_line):
                if i + j < len(self.data):
                    hex_part += f"{self.data[i+j]:02X} "
                else:
                    hex_part += "   "
            text += hex_part.ljust(self.bytes_per_line * 3)
            
            # ASCII列
            ascii_part = ""
            for j in range(self.bytes_per_line):
                if i + j < len(self.data):
                    byte = self.data[i+j]
                    if 32 <= byte <= 126:  # 可打印ASCII字符
                        ascii_part += chr(byte)
                    else:
                        ascii_part += "."
            text += " " + ascii_part + "\n"
        
        self.setText(text)
    
    def set_offset(self, offset):
        """设置当前偏移量"""
        self.current_offset = offset
        self.update_view()
    
    def navigate(self, direction):
        """导航数据（上/下/页上/页下）"""
        if direction == "up":
            self.current_offset = max(0, self.current_offset - self.bytes_per_line)
        elif direction == "down":
            self.current_offset = min(self.total_size - 1, self.current_offset + self.bytes_per_line)
        elif direction == "page_up":
            lines_per_page = self.height() // 20  # 估计每页行数
            self.current_offset = max(0, self.current_offset - lines_per_page * self.bytes_per_line)
        elif direction == "page_down":
            lines_per_page = self.height() // 20  # 估计每页行数
            self.current_offset = min(self.total_size - 1, self.current_offset + lines_per_page * self.bytes_per_line)
        
        self.update_view()

class FileSystemTree(QTreeWidget):
    """文件系统树组件"""
    
    item_double_clicked = pyqtSignal(dict)
    item_clicked = pyqtSignal(dict)  # 添加单击事件信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["名称", "大小", "类型", "属性"])
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.header().setStretchLastSection(False)
        self.setAlternatingRowColors(True)
        self.setAnimated(True)
        self.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.itemClicked.connect(self.on_item_clicked)  # 连接单击事件
        self.items_data = {}  # 存储项目关联的数据
        
        # 优化显示效果，减少行高和间距
        self.setIndentation(15)  # 减少缩进
        self.header().setDefaultSectionSize(80)  # 设置默认列宽
        self.header().setMinimumSectionSize(50)  # 设置最小列宽
        
        # 设置样式以减少行高
        self.setStyleSheet("""
            QTreeWidget::item {
                height: 20px;
                padding: 1px;
            }
            QTreeWidget::item:selected {
                background-color: #3daee9;
            }
        """)
    
    def add_item(self, parent, name, size="", item_type="", attributes="", item_data=None):
        """添加项目到树"""
        item = QTreeWidgetItem(parent if parent else self)
        item.setText(0, name)
        item.setText(1, size)
        item.setText(2, item_type)
        item.setText(3, attributes)
        
        # 存储项目关联的数据
        if item_data:
            self.items_data[id(item)] = item_data
        
        return item
    
    def clear_tree(self):
        """清空树"""
        self.clear()
        self.items_data = {}
    
    def on_item_double_clicked(self, item, column):
        """处理项目双击事件"""
        item_id = id(item)
        if item_id in self.items_data:
            self.item_double_clicked.emit(self.items_data[item_id])
    
    def on_item_clicked(self, item, column):
        """处理项目单击事件"""
        item_id = id(item)
        if item_id in self.items_data:
            self.item_clicked.emit(self.items_data[item_id])
    
    def load_disk(self, disk_path):
        """加载磁盘文件系统"""
        try:
            from disk_utils import DiskManager
            
            self.clear_tree()
            disk_manager = DiskManager()
            
            # 添加根节点
            root_item = self.add_item(None, f"磁盘: {disk_path}", "", "磁盘", "")
            
            # 获取磁盘信息
            disk_info = disk_manager.get_disk_info(disk_path)
            
            # 检查是否是逻辑驱动器
            is_logical_drive = disk_info.get('is_logical_drive', False)
            
            if not is_logical_drive:
                # 对于物理磁盘或虚拟磁盘文件，添加MBR项目
                mbr_item = self.add_item(root_item, "主引导记录 (MBR)", "512 字节", "系统", "只读",
                                       {"disk_path": disk_path, "offset": 0, "size": 512, "type": "mbr"})
            
            # 如果有分区信息，添加分区项目
            if 'partitions' in disk_info and disk_info['partitions']:
                if not is_logical_drive:
                    partitions_item = self.add_item(root_item, "分区", "", "文件夹", "")
                else:
                    partitions_item = root_item  # 对于逻辑驱动器，直接在根节点下添加
                
                for i, partition in enumerate(disk_info['partitions']):
                    if partition['type'] != 0:  # 跳过空分区
                        if is_logical_drive:
                            # 对于逻辑驱动器，显示为引导扇区
                            part_name = f"引导扇区 (DBR) - {partition['type_name']}"
                        else:
                            part_name = f"分区 {i+1} ({partition['type_name']})"
                        part_size = f"{partition['size_human']}"
                        
                        # 计算DBR偏移量（分区起始扇区）
                        dbr_offset = partition['start_sector'] * 512
                        
                        part_item = self.add_item(partitions_item, part_name, part_size, "分区", "",
                                                 {"disk_path": disk_path, "offset": dbr_offset, 
                                                  "size": 512, "type": "dbr", "partition_info": partition})
            
            # 展开根节点
            root_item.setExpanded(True)
            
        except Exception as e:
            # 如果加载失败，显示错误信息
            error_item = self.add_item(None, f"加载失败: {str(e)}", "", "错误", "")
            error_item.setExpanded(True)

class DiskInfoPanel(QWidget):
    """磁盘信息面板组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(3, 3, 3, 3)  # 减少边距
        self.layout.setSpacing(2)  # 减少间距
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.layout.addWidget(self.info_text)
    
    def set_info(self, info_text):
        """设置纯文本信息"""
        self.info_text.setPlainText(info_text)
    
    def set_html(self, info_dict):
        """设置HTML格式的信息"""
        if not info_dict:
            self.info_text.setHtml("<p>无可用信息</p>")
            return
        
        html = "<table border='0' cellspacing='2' cellpadding='4' width='100%'>"
        
        # 处理错误信息
        if 'error' in info_dict:
            html += f"<tr><td colspan='2' style='color:red;'>{info_dict['error']}</td></tr>"
            html += "</table>"
            self.info_text.setHtml(html)
            return
        
        # 添加表头
        html += "<tr bgcolor='#E0E0E0'><th align='left'>属性</th><th align='left'>值</th></tr>"
        
        # 添加信息行
        row_class = ['#F8F8F8', '#FFFFFF']
        row_index = 0
        
        # 处理特殊键
        special_keys = ['error', 'partitions', 'scan_result', 'mbr_info', 'files', 'by_type']
        
        # 首先处理文件系统类型（如果有）
        if 'filesystem' in info_dict:
            html += f"<tr bgcolor='{row_class[row_index % 2]}'><td><b>文件系统</b></td><td>{info_dict['filesystem']}</td></tr>"
            row_index += 1
        
        # 处理常规键值对
        for key, value in info_dict.items():
            if key in special_keys:
                continue
            
            # 格式化键名
            key_name = key.replace('_', ' ').title()
            
            # 添加行
            html += f"<tr bgcolor='{row_class[row_index % 2]}'><td>{key_name}</td><td>{value}</td></tr>"
            row_index += 1
        
        # 处理分区信息
        if 'partitions' in info_dict and info_dict['partitions']:
            html += f"<tr bgcolor='#E0E0E0'><th colspan='2' align='left'>分区信息</th></tr>"
            
            for partition in info_dict['partitions']:
                html += f"<tr bgcolor='{row_class[row_index % 2]}'><td colspan='2'>"
                html += "<table border='0' cellspacing='1' cellpadding='2' width='100%'>"
                html += f"<tr><td><b>分区 {partition.get('index', '')}</b></td><td>{partition.get('type_name', '')}</td></tr>"
                html += f"<tr><td>状态</td><td>{partition.get('status', '')}</td></tr>"
                html += f"<tr><td>起始扇区</td><td>{partition.get('start_lba', '')}</td></tr>"
                html += f"<tr><td>扇区数</td><td>{partition.get('sectors', '')}</td></tr>"
                html += f"<tr><td>大小</td><td>{partition.get('size_human', '')}</td></tr>"
                html += "</table>"
                html += "</td></tr>"
                row_index += 1
        
        # 处理扫描结果
        if 'scan_result' in info_dict and 'found_files' in info_dict['scan_result']:
            found_files = info_dict['scan_result']['found_files']
            if found_files:
                html += f"<tr bgcolor='#E0E0E0'><th colspan='2' align='left'>文件扫描结果</th></tr>"
                html += f"<tr bgcolor='{row_class[row_index % 2]}'><td colspan='2'>找到 {len(found_files)} 个文件</td></tr>"
                row_index += 1
                
                # 按类型统计
                if 'files_by_type' in info_dict['scan_result']:
                    files_by_type = info_dict['scan_result']['files_by_type']
                    html += f"<tr bgcolor='{row_class[row_index % 2]}'><td colspan='2'>"
                    html += "<table border='0' cellspacing='1' cellpadding='2' width='100%'>"
                    html += "<tr><th>类型</th><th>数量</th></tr>"
                    
                    for file_type, files in files_by_type.items():
                        html += f"<tr><td>{file_type}</td><td>{len(files)}</td></tr>"
                    
                    html += "</table>"
                    html += "</td></tr>"
                    row_index += 1
        
        html += "</table>"
        self.info_text.setHtml(html)

class ProgressDialog(QDialog):
    """进度对话框组件"""
    
    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # 消息标签
        self.message_label = QLabel(message)
        layout.addWidget(self.message_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        
        # 详细信息标签
        self.detail_label = QLabel("")
        layout.addWidget(self.detail_label)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Cancel)
        button_box.setStyleSheet("""
            QDialogButtonBox QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-family: "Microsoft YaHei", "SimHei", "黑体";
                font-weight: bold;
                font-size: 14px;
                min-width: 80px;
                min-height: 30px;
            }
            QDialogButtonBox QPushButton:hover {
                background-color: #7f8c8d;
            }
            QDialogButtonBox QPushButton:pressed {
                background-color: #6c7b7d;
            }
        """)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # 设置模态
        self.setModal(True)
    
    def set_progress(self, value):
        """设置进度值"""
        self.progress_bar.setValue(value)
    
    def show_message(self, text):
        """显示消息"""
        self.set_message(text)
    
    def set_message(self, message):
        """设置消息"""
        self.message_label.setText(message)
    
    def set_detail(self, detail):
        """设置详细信息"""
        self.detail_label.setText(detail)

class DataWipeDialog(QDialog):
    """数据擦除对话框组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("数据擦除")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        # 警告信息
        warning_label = QLabel("<b>警告：数据擦除操作不可逆！</b>")
        warning_label.setStyleSheet("color: red;")
        layout.addWidget(warning_label)
        
        # 说明信息
        info_label = QLabel("此操作将永久删除所选磁盘或分区上的所有数据。请确保您已备份重要数据。")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 擦除方法组
        method_group = QGroupBox("擦除方法")
        method_layout = QVBoxLayout()
        
        self.method_zero = QRadioButton("零填充（快速）")
        self.method_zero.setChecked(True)
        method_layout.addWidget(self.method_zero)
        
        self.method_random = QRadioButton("随机数据填充（中等）")
        method_layout.addWidget(self.method_random)
        
        self.method_dod = QRadioButton("DoD 5220.22-M（3次，安全）")
        method_layout.addWidget(self.method_dod)
        
        self.method_dod_7pass = QRadioButton("DoD 5220.22-M（7次，高安全）")
        method_layout.addWidget(self.method_dod_7pass)
        
        self.method_gutmann = QRadioButton("Gutmann方法（35次，极高安全）")
        method_layout.addWidget(self.method_gutmann)
        
        method_group.setLayout(method_layout)
        layout.addWidget(method_group)
        
        # 确认输入
        confirm_group = QGroupBox("确认")
        confirm_layout = QFormLayout()
        
        self.confirm_text = QLineEdit()
        confirm_layout.addRow("请输入\"CONFIRM\"以继续：", self.confirm_text)
        
        confirm_group.setLayout(confirm_layout)
        layout.addWidget(confirm_group)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.setStyleSheet("""
            QDialogButtonBox QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-family: "Microsoft YaHei", "SimHei", "黑体";
                font-weight: bold;
                font-size: 14px;
                min-width: 80px;
                min-height: 30px;
            }
            QDialogButtonBox QPushButton:hover {
                background-color: #2980b9;
            }
            QDialogButtonBox QPushButton:pressed {
                background-color: #21618c;
            }
            QDialogButtonBox QPushButton[text="Cancel"],
            QDialogButtonBox QPushButton[text="取消"] {
                background-color: #95a5a6;
            }
            QDialogButtonBox QPushButton[text="Cancel"]:hover,
            QDialogButtonBox QPushButton[text="取消"]:hover {
                background-color: #7f8c8d;
            }
            QDialogButtonBox QPushButton[text="Cancel"]:pressed,
            QDialogButtonBox QPushButton[text="取消"]:pressed {
                background-color: #6c7b7d;
            }
        """)
        button_box.accepted.connect(self.validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # 设置模态
        self.setModal(True)
    
    def validate_and_accept(self):
        """验证确认文本并接受对话框"""
        if self.confirm_text.text() == "CONFIRM":
            self.accept()
        else:
            QMessageBox.warning(self, "确认失败", "请输入\"CONFIRM\"以继续操作。")
    
    def get_selected_method(self):
        """获取选择的擦除方法"""
        if self.method_zero.isChecked():
            return "zero"
        elif self.method_random.isChecked():
            return "random"
        elif self.method_dod.isChecked():
            return "dod"
        elif self.method_dod_7pass.isChecked():
            return "dod_7pass"
        elif self.method_gutmann.isChecked():
            return "gutmann"
        return "zero"  # 默认方法
    
    def get_wipe_settings(self):
        """获取擦除设置（方法和遍数）"""
        method = self.get_selected_method()
        
        # 根据方法确定默认遍数
        passes_mapping = {
            'zero': 1,
            'random': 1,
            'dod': 3,
            'dod_7pass': 7,
            'gutmann': 35
        }
        
        passes = passes_mapping.get(method, 1)
        return method, passes

class FileRecoveryDialog(QDialog):
    """文件恢复对话框组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("文件恢复")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        # 文件类型选择
        type_group = QGroupBox("文件类型")
        type_layout = QVBoxLayout()
        
        self.type_all = QCheckBox("所有类型")
        self.type_all.setChecked(True)
        self.type_all.stateChanged.connect(self.on_type_all_changed)
        type_layout.addWidget(self.type_all)
        
        # 常见文件类型
        self.type_images = QCheckBox("图片 (JPG, PNG, GIF, BMP)")
        type_layout.addWidget(self.type_images)
        
        self.type_documents = QCheckBox("文档 (PDF, DOC, DOCX, TXT)")
        type_layout.addWidget(self.type_documents)
        
        self.type_archives = QCheckBox("压缩文件 (ZIP, RAR, 7Z)")
        type_layout.addWidget(self.type_archives)
        
        self.type_audio = QCheckBox("音频 (MP3, WAV, FLAC)")
        type_layout.addWidget(self.type_audio)
        
        self.type_video = QCheckBox("视频 (MP4, AVI, MOV)")
        type_layout.addWidget(self.type_video)
        
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)
        
        # 扫描选项
        options_group = QGroupBox("扫描选项")
        options_layout = QFormLayout()
        
        self.scan_direction = QComboBox()
        self.scan_direction.addItems(["从头到尾扫描", "从尾到头扫描"])
        options_layout.addRow("扫描方向：", self.scan_direction)
        
        self.save_path = QLineEdit()
        self.save_path.setReadOnly(True)
        browse_button = QPushButton("浏览...")
        browse_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-family: "Microsoft YaHei", "SimHei", "黑体";
                font-weight: bold;
                font-size: 14px;
                min-width: 80px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)
        browse_button.clicked.connect(self.browse_save_path)
        save_path_layout = QHBoxLayout()
        save_path_layout.addWidget(self.save_path)
        save_path_layout.addWidget(browse_button)
        options_layout.addRow("保存位置：", save_path_layout)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.setStyleSheet("""
            QDialogButtonBox QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-family: "Microsoft YaHei", "SimHei", "黑体";
                font-weight: bold;
                font-size: 14px;
                min-width: 80px;
                min-height: 30px;
            }
            QDialogButtonBox QPushButton:hover {
                background-color: #2980b9;
            }
            QDialogButtonBox QPushButton:pressed {
                background-color: #21618c;
            }
            QDialogButtonBox QPushButton[text="Cancel"],
            QDialogButtonBox QPushButton[text="取消"] {
                background-color: #95a5a6;
            }
            QDialogButtonBox QPushButton[text="Cancel"]:hover,
            QDialogButtonBox QPushButton[text="取消"]:hover {
                background-color: #7f8c8d;
            }
            QDialogButtonBox QPushButton[text="Cancel"]:pressed,
            QDialogButtonBox QPushButton[text="取消"]:pressed {
                background-color: #6c7b7d;
            }
        """)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # 设置模态
        self.setModal(True)
        
        # 初始化保存路径
        self.save_path.setText(os.path.join(os.path.expanduser("~"), "Desktop", "RecoveredFiles"))
    
    def on_type_all_changed(self, state):
        """处理"所有类型"复选框状态变化"""
        checked = state == Qt.Checked
        self.type_images.setEnabled(not checked)
        self.type_documents.setEnabled(not checked)
        self.type_archives.setEnabled(not checked)
        self.type_audio.setEnabled(not checked)
        self.type_video.setEnabled(not checked)
        
        if checked:
            self.type_images.setChecked(False)
            self.type_documents.setChecked(False)
            self.type_archives.setChecked(False)
            self.type_audio.setChecked(False)
            self.type_video.setChecked(False)
    
    def browse_save_path(self):
        """浏览保存路径"""
        directory = QFileDialog.getExistingDirectory(self, "选择保存目录", self.save_path.text())
        if directory:
            self.save_path.setText(directory)
    
    def get_selected_types(self):
        """获取选择的文件类型"""
        if self.type_all.isChecked():
            return ["all"]
        
        selected = []
        if self.type_images.isChecked():
            selected.append("images")
        if self.type_documents.isChecked():
            selected.append("documents")
        if self.type_archives.isChecked():
            selected.append("archives")
        if self.type_audio.isChecked():
            selected.append("audio")
        if self.type_video.isChecked():
            selected.append("video")
        
        return selected if selected else ["all"]
    
    def get_scan_direction(self):
        """获取扫描方向"""
        return self.scan_direction.currentIndex() == 1  # True表示从尾到头
    
    def get_save_path(self):
        """获取保存路径"""
        return self.save_path.text()

class WorkerThread(QThread):
    """工作线程基类"""
    
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    detail_updated = pyqtSignal(str)
    operation_completed = pyqtSignal(dict)
    operation_failed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_cancelled = False
        self._cancel_lock = threading.Lock()
    
    def cancel(self):
        """取消操作"""
        with self._cancel_lock:
            self._is_cancelled = True
    
    @property
    def is_cancelled(self):
        """线程安全的取消状态检查"""
        with self._cancel_lock:
            return self._is_cancelled

class StatusBar(QWidget):
    """状态栏组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 1, 3, 1)  # 减少边距
        layout.setSpacing(3)  # 减少间距
        
        self.status_label = QLabel("就绪")
        self.status_label.setMaximumHeight(20)  # 限制高度
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(150)
        self.progress_bar.setMaximumHeight(18)  # 减少进度条高度
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 设置整个状态栏的最大高度
        self.setMaximumHeight(25)
    
    def set_status(self, text):
        """设置状态文本"""
        self.status_label.setText(text)
    
    def show_progress(self, visible=True):
        """显示或隐藏进度条"""
        self.progress_bar.setVisible(visible)
        if visible:
            self.progress_bar.setValue(0)
    
    def hide_progress(self):
        """隐藏进度条"""
        self.progress_bar.setVisible(False)
    
    def set_progress(self, value):
        """设置进度值"""
        self.progress_bar.setValue(value)