
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 仓库批量管理工具 - Flask版本启动脚本

特性：
- ✅ 支持表格排序且不会重置
- ✅ 支持拖选多个条目
- ✅ 更好的交互体验
- ✅ 解决Streamlit的所有限制
"""

from app_flask import app
import webbrowser
import threading
import time


def open_browser():
    """延迟打开浏览器"""
    time.sleep(1.5)
    webbrowser.open('http://localhost:5000')


if __name__ == '__main__':
    print("=" * 50)
    print("🚀 GitHub 仓库批量管理工具 - Flask版本")
    print("=" * 50)
    print("✅ 支持表格排序且不会重置")
    print("✅ 支持拖选多个条目")
    print("✅ 更好的交互体验")
    print("✅ 解决Streamlit的所有限制")
    print()
    print("🌐 启动中... 浏览器将自动打开")
    print("📍 手动访问: http://localhost:5000")
    print("🛑 停止服务: Ctrl+C")
    print("=" * 50)

    # 在新线程中打开浏览器
    threading.Thread(target=open_browser, daemon=True).start()

    # 启动Flask应用
    app.run(debug=False, host='0.0.0.0', port=5000)
