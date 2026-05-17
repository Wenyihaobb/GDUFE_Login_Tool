import configparser
import sys
from typing import Optional
import requests
import socket
import json
import base64
from bs4 import BeautifulSoup
from cryptography.fernet import Fernet
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QMessageBox, QSystemTrayIcon, QMenu, QDialog, QDialogButtonBox, QHBoxLayout, QSpinBox
from PySide6.QtGui import QIcon, QAction
from plyer import notification
import os
import winreg


# 配置文件存储在用户主目录下的隐藏目录 ".gdufe_login" 中
config_dir = os.path.expanduser(os.path.join("~", ".gdufe_login"))
os.makedirs(config_dir, exist_ok=True)  # 确保目录存在
CONFIG_FILE = os.path.join(config_dir, 'user_config.ini')
KEY_FILE = os.path.join(config_dir, 'secret.key')


def get_encryption_key():
    """获取或生成加密密钥"""
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, 'rb') as key_file:
            return key_file.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, 'wb') as key_file:
            key_file.write(key)
        return key


def encrypt_password(password: str) -> str:
    """加密密码"""
    if not password:
        return ''
    key = get_encryption_key()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(password.encode())
    return base64.urlsafe_b64encode(encrypted).decode()


def decrypt_password(encrypted_password: str) -> str:
    """解密密码"""
    if not encrypted_password:
        return ''
    try:
        key = get_encryption_key()
        fernet = Fernet(key)
        decoded = base64.urlsafe_b64decode(encrypted_password.encode())
        decrypted = fernet.decrypt(decoded)
        return decrypted.decode()
    except Exception:
        # 如果解密失败（可能是旧版本的明文密码），返回原值
        return encrypted_password

def check_login_status():
    try:
        response = requests.get('http://100.64.13.17/', timeout=5)
        BeautifulSoup(response.text, 'html.parser')
        if "注销页" in response.text:
            return "logged_in"
        elif "上网登录页" in response.text:
            return "logged_out"
        else:
            return "unknown"
    except requests.exceptions.RequestException:
        return "error"


def get_local_ip():
    """获取本机IP地址"""
    try:
        # 创建一个socket连接，通过这个连接获取本机IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 连接一个公共的服务器地址，不需要真正连接
        s.connect(("1.1.1.1", 80))
        # 获取本机的IP地址
        ip = s.getsockname()[0]
        s.close()
        return ip
    except(socket.error, OSError):
        # 如果获取失败，返回默认IP
        return "0.0.0.0"


def clear_user_info():
    """清除用户信息"""
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if 'Credentials' in config:
        config.remove_section('Credentials')
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)


def quit_application():
    """退出应用程序"""
    QApplication.quit()


def check_network_status_after_login():
    """登录后检查网络状态并更新界面"""
    # 仅处理通知，不再改变界面状态
    status = check_login_status()
    if status == "logged_in":
        notification.notify(
            title='登录',
            message='登录成功，已连接到校园网',
            timeout=5
        )
    else:
        # 可能暂时网络问题，但登录可能成功，所以不改变界面
        pass


class CampusNetLogin(QWidget):
    def __init__(self):
        super().__init__()
        self.reconnect_interval = 30
        self.layout = QVBoxLayout()  # 定义为类的成员变量
        self.reconnect_retry_count = 0
        self.reconnect_timer = QTimer()
        self.reconnect_timer.timeout.connect(self.check_reconnect)
        self.autoReconnectCheckbox = None  # 预声明变量
        self.settingsLink = QLabel('<a href="#">设置</a>')
        self.tray_icon = QSystemTrayIcon(self)
        self.userLabel = QLabel('用户名:')
        self.userInput = QLineEdit()
        self.passLabel = QLabel('密码:')
        self.passInput = QLineEdit()
        self.rememberMe = QCheckBox('记住我')
        self.autoStartCheckbox = QCheckBox('开机启动')
        self.autoStartCheckbox.stateChanged.connect(self.on_auto_start_changed)  # 修改信号连接目标
        self.autoLoginCheckbox = QCheckBox('自动登录')  # 新增自动登录复选框
        self.autoLoginCheckbox.setEnabled(self.autoStartCheckbox.isChecked())  # 初始化自动登录可用性
        self.autoReconnectCheckbox = QCheckBox('自动重连')
        self.autoReconnectCheckbox.stateChanged.connect(self.on_auto_reconnect_changed)  # 新增信号连接
        self.loginButton = QPushButton('登录')
        self.logoutButton = QPushButton('注销')
        self.icon_path = self.get_icon_path()  # 提取图标路径
        self.initui()  # 初始化界面布局
        self.load_user_info()
        # 新增对开机启动参数的检测
        self.is_auto_start = "--autostart" in sys.argv
        # 修改自动登录触发条件
        if self.is_auto_start and self.autoStartCheckbox.isChecked() and self.autoLoginCheckbox.isChecked() and self.rememberMe.isChecked() and self.userInput.text() and self.passInput.text():
            QTimer.singleShot(0, self.do_login)  # 延迟执行确保界面显示
        self.check_network_status()
        self.setup_tray_icon()
        self.first_close = True
        self.exit_requested = False  # 新增退出请求标记

    def get_icon_path(self):
        """获取图标文件路径"""
        return os.path.join(getattr(sys, '_MEIPASS', os.path.abspath(".")), 'favicon.ico')

    def initui(self):
        self.layout.addWidget(self.userLabel)
        self.layout.addWidget(self.userInput)
        self.layout.addWidget(self.passLabel)
        self.passInput.setEchoMode(QLineEdit.EchoMode.Password)
        self.layout.addWidget(self.passInput)

        # 复选框形式的"记住我"
        hbox = QHBoxLayout()
        hbox.addWidget(self.rememberMe)
        self.settingsLink.linkActivated.connect(self.show_settings_dialog)
        hbox.addWidget(self.settingsLink)
        self.layout.addLayout(hbox)

        self.loginButton.clicked.connect(self.do_login)
        self.layout.addWidget(self.loginButton)
        self.logoutButton.clicked.connect(self.do_logout)
        self.layout.addWidget(self.logoutButton)
        self.setLayout(self.layout)  # 设置布局
        self.setWindowTitle('GDUFE Login Tool')
        self.setWindowIcon(QIcon(self.icon_path))
        self.show()

    def load_user_info(self):
        """加载用户信息"""
        config = configparser.ConfigParser()
        if config.read(CONFIG_FILE):
            try:
                username = config.get('Credentials', 'username')
                encrypted_password = config.get('Credentials', 'password')
                # 解密密码（兼容旧版本的明文密码）
                password = decrypt_password(encrypted_password)
                remember = config.getboolean('Credentials', 'remember')
                auto_start = config.getboolean('Credentials', 'auto_start')
                auto_login = config.getboolean('Credentials', 'auto_login', fallback=False)
                auto_reconnect = config.getboolean('Credentials', 'auto_reconnect', fallback=False)
                self.userInput.setText(username)
                self.passInput.setText(password)
                self.rememberMe.setChecked(remember)
                self.autoStartCheckbox.setChecked(auto_start)
                self.autoLoginCheckbox.setChecked(auto_login)
                self.autoReconnectCheckbox.setChecked(auto_reconnect)
                self.reconnect_interval = config.getint('Credentials', 'reconnect_interval', fallback=30)  # 新增读取间隔时间
            except (configparser.NoSectionError, configparser.NoOptionError):
                # 如果配置文件中没有相关配置项，则默认不启用自动重连
                self.autoReconnectCheckbox.setChecked(False)
        else:
            # 如果没有配置文件，则默认不启用自动重连
            self.autoReconnectCheckbox.setChecked(False)

    def save_user_info(self):
        """保存用户信息"""
        config = configparser.ConfigParser()
        # 加密密码后保存
        encrypted_password = encrypt_password(self.passInput.text())
        config['Credentials'] = {
            'username': self.userInput.text(),
            'password': encrypted_password,
            'remember': str(self.rememberMe.isChecked()),
            'auto_start': str(self.autoStartCheckbox.isChecked()),
            'auto_login': str(self.autoLoginCheckbox.isChecked()),  # 新增自动登录配置保存
            'auto_reconnect': str(self.autoReconnectCheckbox.isChecked()),
            'reconnect_interval': str(self.reconnect_interval),  # 新增保存间隔时间
        }
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)

    def on_auto_start_changed(self):
        """处理开机启动和自动登录联动"""
        self.toggle_auto_start()  # 先处理开机启动设置
        enabled = self.autoStartCheckbox.isChecked()
        self.autoLoginCheckbox.setEnabled(enabled)
        if not enabled:
            self.autoLoginCheckbox.setChecked(False)
        self.save_user_info()

    # 修改开机启动BAT路径和参数传递方式
    def toggle_auto_start(self):
        enabled = self.autoStartCheckbox.isChecked()
        if sys.platform == 'win32':
            # 注册表路径
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            app_name = "GDUFE Login Tool"
            exe_path = os.path.abspath(sys.argv[0])
            
            try:
                # 打开注册表键
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                
                if enabled:
                    # 写入注册表值
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{exe_path}" --autostart')
                else:
                    # 删除注册表值
                    winreg.DeleteValue(key, app_name)
                    
                winreg.CloseKey(key)
            except Exception as e:
                # 简单错误处理（可按需扩展）
                QMessageBox.warning(self, "设置失败", f"无法修改注册表: {str(e)}")

    def check_network_status(self, show_notification=False):
        """检查网络状态，并根据状态调整界面"""
        status = check_login_status()
        if status == "logged_in" :
            # 仅在手动检查时显示通知
            if show_notification:
                notification.notify(
                    title='已登录',
                    message='校园网已处于登录状态',
                    timeout=5
                )
            self.toggle_ui_elements(False, True)
            self.hide()  # 隐藏窗口
        else:
            self.toggle_ui_elements(True, False)

    def toggle_ui_elements(self, login_enabled, logout_enabled):
        """根据参数启用或禁用界面元素"""
        self.userInput.setEnabled(login_enabled)
        self.passInput.setEnabled(login_enabled)
        self.loginButton.setEnabled(login_enabled)
        self.rememberMe.setEnabled(login_enabled)
        self.logoutButton.setEnabled(logout_enabled)

    def do_login(self):
        username = self.userInput.text()
        password = self.passInput.text()
        login_url = "http://100.64.13.17:801/eportal/portal/login"
        
        # 获取当前IP地址
        user_ip = get_local_ip()
        
        params = {
            'callback': 'dr1003',
            'login_method': '1',
            'user_account': ',0,' + username,
            'user_password': password,
            'wlan_user_ip': user_ip,
            'wlan_ac_ip': '100.64.13.18',
            'jsVersion': '4.1.3',
            'lang': 'zh'
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh-TW;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6",
            "Referer": "http://100.64.64.17/"
        }

        try:
            response = requests.get(login_url, params=params, headers=headers, timeout=10)
            print(response.text)

            # 新增JSON解析逻辑
            response_str = response.text.strip()
            start = response_str.find('(') + 1
            end = response_str.rfind(')')
            json_str = response_str[start:end]
            try:
                data = json.loads(json_str)
                if data.get('result') == 1 or data.get('msg') == 'AC999':
                    # 登录成功处理
                    if self.rememberMe.isChecked():
                        self.save_user_info()
                    else:
                        clear_user_info()

                    # 立即更新界面状态并隐藏窗口
                    self.toggle_ui_elements(False, True)
                    self.hide()  # 隐藏窗口
                    
                    # 保留定时器用于通知
                    QTimer.singleShot(1000, lambda: check_network_status_after_login())
                else:
                    # 登录失败处理
                    QMessageBox.critical(self, "错误", "登录失败，请检查用户名和密码")
                    notification.notify(
                        title='登录',
                        message='登录失败，请检查用户名和密码',
                        timeout=5
                    )
                    self.toggle_ui_elements(True, False)  # 保持登录控件可用
            except json.JSONDecodeError:
                QMessageBox.critical(self, "错误", "登录失败，响应格式异常")
                self.toggle_ui_elements(True, False)
        except requests.exceptions.Timeout:
            QMessageBox.critical(self, "错误", "登录超时，请检查网络连接")
            self.toggle_ui_elements(True, False)
        except requests.exceptions.ConnectionError:
            QMessageBox.critical(self, "错误", "无法连接到服务器，请检查网络")
            self.toggle_ui_elements(True, False)
        except requests.exceptions.RequestException as e:
            QMessageBox.critical(self, "错误", f"登录请求失败: {str(e)}")
            self.toggle_ui_elements(True, False)

    def do_logout(self):
        logout_url = "http://100.64.13.17:801/eportal/portal/logout"
        
        # 获取当前IP地址
        user_ip = get_local_ip()
        
        params = {
            'callback': 'dr1004',
            'login_method': '1',
            'user_account': 'drcom',
            'user_password': '123',
            'ac_logout': '1',
            'register_mode': '1',
            'wlan_user_ip': user_ip,
            'wlan_ac_ip': '100.64.13.18',
            'jsVersion': '4.1.3',
            'v': '8927',
            'lang': 'zh'
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh-TW;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6",
        }
        try:
            response = requests.get(logout_url, params=params, headers=headers, timeout=10)
            print(response.text)
            # 假设注销总是成功的
            self.toggle_ui_elements(True, False)  # 启用登录相关控件，禁用注销按钮
            # 添加注销通知
            notification.notify(
                title='注销',
                message='校园网已注销',
                timeout=5
            )
        except requests.exceptions.Timeout:
            QMessageBox.warning(self, "警告", "注销超时，但可能已成功")
            self.toggle_ui_elements(True, False)
        except requests.exceptions.ConnectionError:
            QMessageBox.warning(self, "警告", "无法连接到服务器，但可能已注销")
            self.toggle_ui_elements(True, False)
        except requests.exceptions.RequestException as e:
            QMessageBox.warning(self, "警告", f"注销请求异常: {str(e)}")
            self.toggle_ui_elements(True, False)

    def setup_tray_icon(self):
        """设置系统托盘图标"""
        # 使用类常量中的图标路径
        self.tray_icon.setIcon(QIcon(self.icon_path))
            
        # 创建托盘菜单
        tray_menu = QMenu()
            
        # 添加“显示”菜单项
        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
            
        # 添加分隔线
        tray_menu.addSeparator()
            
        # 添加“注销”菜单项（保存引用以便动态启用/禁用）
        self.logout_action = QAction("注销", self)
        self.logout_action.triggered.connect(self.do_logout)
        tray_menu.addAction(self.logout_action)
            
        # 添加分隔线
        tray_menu.addSeparator()
            
        # 添加“退出”菜单项
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.request_exit)  # 修改为连接到新方法
        tray_menu.addAction(quit_action)
            
        # 设置托盘图标的菜单
        self.tray_icon.setContextMenu(tray_menu)
            
        # 设置托盘图标的提示文字
        self.tray_icon.setToolTip("GDUFE Login Tool")
            
        # 显示托盘图标
        self.tray_icon.show()
            
        # 连接托盘图标的激活信号（双击或点击）
        self.tray_icon.activated.connect(self.tray_icon_activated)

    def tray_icon_activated(self, reason):
        """处理托盘图标的激活事件"""
        # 如果是双击托盘图标
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            # 如果窗口不可见，则显示窗口
            if not self.isVisible():
                self.show()
                # 将窗口设为活动窗口
                self.activateWindow()

    def request_exit(self):
        """处理托盘退出请求"""
        self.exit_requested = True
        self.close()  # 触发closeEvent

    def closeEvent(self, event):
        """修复退出逻辑，区分主动退出和最小化"""
        if self.exit_requested:  # 如果是主动退出请求
            self.exit_requested = False
            event.accept()  # 允许退出
            QApplication.quit()  # 新增：强制退出应用程序
        else:
            # 保留原有最小化逻辑
            if self.first_close:
                notification.notify(
                    title='GDUFE Login Tool',
                    message='程序已最小化到系统托盘，双击托盘图标可以重新打开窗口',
                    timeout=3
                )
                self.first_close = False  # 仅首次显示
            self.hide()
            event.ignore()  # 阻止窗口关闭

    def on_auto_login_changed(self):
        self.save_user_info()

    def on_auto_reconnect_changed(self, state):
        """处理自动重连选项状态变化"""
        # 检查复选框的状态是否为选中状态
        if state == 2:  # Qt.CheckState.Checked 的值是 2
            enabled = True
        else:
            enabled = False
        self.toggle_reconnect_timer(enabled)
        self.save_user_info()

    def toggle_reconnect_timer(self, enabled):
        """正确实现定时器启停逻辑"""
        if enabled:
            self.reconnect_timer.start(self.reconnect_interval * 1000)  # 使用动态间隔时间
        else:
            self.reconnect_timer.stop()
            self.reconnect_retry_count = 0

    def check_reconnect(self):
        """修正后的重连检测逻辑"""
        status = check_login_status()

        if status == "logged_out":  # 检测到未登录状态
            # 检查是否有保存的凭证
            config = configparser.ConfigParser()
            if not config.read(CONFIG_FILE) or 'Credentials' not in config:
                notification.notify(
                    title='重连失败',
                    message='未找到保存的登录凭证，请手动登录',
                    timeout=5
                )
                self.toggle_reconnect_timer(False)
                self.autoReconnectCheckbox.setChecked(False)
                return
            
            username = config.get('Credentials', 'username', fallback='')
            encrypted_password = config.get('Credentials', 'password', fallback='')
            # 解密密码（兼容旧版本的明文密码）
            password = decrypt_password(encrypted_password)
            
            if not username or not password:
                notification.notify(
                    title='重连失败',
                    message='登录凭证不完整，请手动登录',
                    timeout=5
                )
                self.toggle_reconnect_timer(False)
                self.autoReconnectCheckbox.setChecked(False)
                return
            
            self.reconnect_retry_count += 1
            max_retries = 5

            if self.reconnect_retry_count >= max_retries:
                notification.notify(
                    title='重连失败',
                    message=f'尝试{max_retries}次失败，请检查网络后手动登录',
                    timeout=5
                )
                self.reconnect_retry_count = 0
            else:
                notification.notify(
                    title='检测到注销',
                    message='正在尝试重连......',
                    timeout=3
                )
                self.do_login()
        elif status in ["logged_in", "error", "unknown"]:  # 其他情况重置计数器
            self.reconnect_retry_count = 0

    # 新增方法：显示设置对话框
    def show_settings_dialog(self):
        dialog = SettingsDialog(self)
        if dialog.exec():
            # 同步设置到主窗口
            old_auto_reconnect = self.autoReconnectCheckbox.isChecked()
            self.autoStartCheckbox.setChecked(dialog.auto_start.isChecked())
            self.autoLoginCheckbox.setChecked(dialog.auto_login.isChecked())
            self.autoReconnectCheckbox.setChecked(dialog.auto_reconnect.isChecked())
            self.reconnect_interval = dialog.reconnect_interval.value()  # 新增同步间隔时间
            
            # 如果自动重连状态发生变化，更新定时器
            if old_auto_reconnect != self.autoReconnectCheckbox.isChecked():
                self.toggle_reconnect_timer(self.autoReconnectCheckbox.isChecked())
            elif self.autoReconnectCheckbox.isChecked():
                # 如果重连已启用但间隔时间变化，重启定时器
                self.toggle_reconnect_timer(False)
                self.toggle_reconnect_timer(True)
            
            self.save_user_info()  # 保存新配置

# 新增设置对话框类
class SettingsDialog(QDialog):
    def __init__(self, parent: Optional[CampusNetLogin] = None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.layout = QVBoxLayout()
        
        self.auto_start = QCheckBox("开机启动")
        self.auto_login = QCheckBox("自动登录")
        self.auto_reconnect = QCheckBox("自动重连")
        self.reconnect_interval = QSpinBox()  # 新增间隔时间输入框
        self.reconnect_interval.setRange(1, 3600)  # 设置范围为1秒到1小时
        self.reconnect_interval.setSuffix(" 秒")  # 设置单位
        
        # 初始化当前值
        checkbox_pairs = [
            (self.auto_start, 'autoStartCheckbox'),
            (self.auto_login, 'autoLoginCheckbox'),
            (self.auto_reconnect, 'autoReconnectCheckbox')
        ]
        for child, parent_attr in checkbox_pairs:
            parent_checkbox = getattr(parent, parent_attr)
            child.setChecked(parent_checkbox.isChecked())
        self.reconnect_interval.setValue(parent.reconnect_interval)  # 初始化间隔时间
        
        # 设置联动关系
        self.auto_login.setEnabled(self.auto_start.isChecked())
        self.auto_start.stateChanged.connect(self.on_auto_start_changed)
        
        self.layout.addWidget(self.auto_start)
        self.layout.addWidget(self.auto_login)
        self.layout.addWidget(self.auto_reconnect)
        self.layout.addWidget(self.reconnect_interval)  # 添加间隔时间输入框
        
        # 添加按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout.addWidget(button_box)
        
        self.setLayout(self.layout)

    def on_auto_start_changed(self, state):
        enabled = (state == Qt.Checked)
        self.auto_login.setEnabled(enabled)
        if not enabled:
            self.auto_login.setChecked(False)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = CampusNetLogin()
    sys.exit(app.exec())
