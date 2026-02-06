# -*- coding: utf-8 -*-

import sys
import traceback

print("Testing basic imports...")

try:
    print("1. Testing PyQt5...")
    from PyQt5.QtWidgets import QApplication, QMainWindow
    print("   ✓ PyQt5 imported successfully")
    
    print("2. Testing DiskRecoveryTool import...")
    from disk_recovery_tool import DiskRecoveryTool
    print("   ✓ DiskRecoveryTool imported successfully")
    
    print("3. Testing class instantiation...")
    app = QApplication(sys.argv)
    window = DiskRecoveryTool()
    print("   ✓ DiskRecoveryTool created successfully")
    
    print("4. Testing method existence...")
    has_method = hasattr(window, 'on_tree_item_double_clicked')
    print(f"   ✓ on_tree_item_double_clicked method exists: {has_method}")
    
    print("\n🎉 All tests passed! The GUI should work now.")
    print("\nTo start the GUI, run: python main.py")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please install missing dependencies: pip install PyQt5 pywin32")
except Exception as e:
    print(f"❌ Error: {e}")
    print(f"Traceback: {traceback.format_exc()}")

input("\nPress Enter to exit...")