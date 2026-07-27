"""
驱动器与网络位置转换器 - 主程序
支持双向转换：驱动器↔网络位置
Supports bidirectional conversion: Drive ↔ Network Location
Compatible with Windows 7/10/11
"""

import customtkinter as ctk
from tkinter import messagebox
from tkinter import font as tkfont
import platform
from drive_utils import (
    get_mapped_drives, 
    get_network_locations,
    get_available_drive_letters,
    convert_drive_to_network_location,
    convert_network_location_to_drive,
    drive_to_unc,
    normalize_unc_path,
    normalize_server_name,
    suggest_location_name,
    add_network_drive_or_location,
    remove_network_drive,
    remove_network_location_item,
    list_server_shares,
    diagnose_share_browse_identity,
    test_share_credentials,
    get_clearable_smb_connections,
    disconnect_server_sessions,
    open_windows_credential_manager,
    diagnose_drive_reconnect,
    repair_drive_reconnect,
    normalize_account_identity,
    ACCOUNT_SCOPE_TARGET,
    ACCOUNT_SCOPE_DOMAIN,
    ACCOUNT_SCOPE_MICROSOFT,
)


def get_system_font():
    """获取系统可用的中文字体，兼容Win7/10/11"""
    # 按优先级尝试的字体列表
    preferred_fonts = [
        "Microsoft YaHei UI",  # Win10/11
        "Microsoft YaHei",     # Win7/10/11
        "SimHei",              # 黑体，所有Windows版本
        "SimSun",              # 宋体，所有Windows版本
        "Arial",               # 回退到英文字体
    ]
    
    try:
        # 创建临时窗口获取可用字体列表
        import tkinter as tk
        temp_root = tk.Tk()
        temp_root.withdraw()
        available_fonts = set(tkfont.families())
        temp_root.destroy()
        
        for font_name in preferred_fonts:
            if font_name in available_fonts:
                return font_name
    except Exception:
        pass
    
    # 如果检测失败，根据Windows版本选择
    try:
        win_version = platform.version()
        major_version = int(win_version.split('.')[0])
        if major_version >= 10:
            return "Microsoft YaHei UI"
        else:
            return "Microsoft YaHei"
    except Exception:
        return "Microsoft YaHei"


# 获取系统字体
SYSTEM_FONT = get_system_font()

# 多语言文本
LANGUAGES = {
    "zh": {
        "window_title": '驱动器 ↔ 网络位置 转换器',
        "main_title": '🔄 驱动器 ↔ 网络位置 转换器',
        "subtitle": '在映射驱动器和网络位置之间双向转换',
        "tab_drive_to_loc": '驱动器 → 网络位置',
        "tab_loc_to_drive": '网络位置 → 驱动器',
        "tab_add": '添加网络驱动器/位置',
        "tab_remove": '删除网络驱动器/位置',
        "tab_repair": '重连修复',
        "mapped_drives": '💿 映射的网络驱动器',
        "network_locations": '📁 网络位置',
        "refresh": '🔄 刷新',
        "convert_to_location": '转换为网络位置',
        "convert_to_drive": '映射为驱动器',
        "drive_letter": '盘符:',
        "no_drives": '未检测到映射的网络驱动器',
        "no_locations": '未检测到网络位置\n\n网络位置可通过"驱动器 → 网络位置"转换创建，或使用"添加网络驱动器/位置"',
        "tip_drive_to_loc": '💡 点击"转换为网络位置"后，将在Windows的网络位置中创建快捷方式，并断开驱动器映射',
        "tip_loc_to_drive": '💡 选择一个可用的盘符，点击"映射为驱动器"后，将创建驱动器映射并删除网络位置',
        "ready": '就绪',
        "refreshed": '列表已刷新',
        "converting": '正在转换...',
        "confirm_drive_to_loc": '确定要将驱动器 {drive} 转换为网络位置吗？\n\nUNC路径: {unc}\n\n⚠️ 此操作将：\n• 创建网络位置快捷方式\n• 断开驱动器 {drive} 的映射\n\n请确保没有正在使用该驱动器的文件！',
        "confirm_loc_to_drive": '确定要将网络位置转换为驱动器映射吗？\n\n网络位置: {name}\nUNC路径: {unc}\n目标盘符: {drive}\n\n此操作将：\n• 映射 {drive} 到 {unc}\n• 删除网络位置 {name}',
        "confirm_title": '确认转换',
        "success": '转换成功',
        "error": '转换失败',
        "error_no_drive": '请选择一个驱动器盘符',
        "files_in_use": '文件占用',
        "force_disconnect": '{msg}\n\n是否强制断开？（可能导致未保存数据丢失）',
        "lang_btn": 'EN',
        "add_title": '➕ 添加网络驱动器或位置',
        "add_unc_label": '网络路径 (UNC / IP):',
        "add_unc_placeholder": '例如 \\\\server\\share 或仅 IP: 192.168.1.10',
        "add_browse_shares": '浏览共享',
        "add_diagnose_browse": '排查浏览',
        "diagnosing_browse": '正在排查 SMB 浏览身份...',
        "diagnose_browse_title": 'SMB 浏览身份排查',
        "test_credentials": '测试凭证',
        "testing_credentials": '正在测试用户名和密码...',
        "test_credentials_title": 'SMB 凭证测试',
        "clear_current_sessions": '清理当前连接',
        "open_credential_manager": '🔐 凭据管理器',
        "credential_manager_opened": '已打开 Windows 凭据管理器',
        "credential_manager_error": '无法打开凭据管理器',
        "confirm_clear_current_sessions": '确定清理 {unc} 所属服务器的无盘符 SMB 连接吗？\n\n软件会直接尝试断开完整共享路径、IPC$ 和服务器根连接；已有映射盘会保留。',
        "add_browsing_shares": '正在浏览共享...',
        "add_shares_label": '可用共享（点击选择）:',
        "add_shares_empty": '未找到共享文件夹',
        "add_shares_hint": '可只输入 IP/主机名，点击“浏览共享”后选择文件夹',
        "add_include_hidden": '显示隐藏共享 ($)',
        "error_no_server": '请输入服务器 IP、主机名或完整 UNC 路径',
        "error_browse_failed": '无法浏览共享',
        "browse_success": '已找到共享',
        "add_mode_label": '添加类型:',
        "add_mode_drive": '网络驱动器',
        "add_mode_location": '网络位置',
        "add_mode_both": '同时添加两者',
        "add_drive_letter": '盘符:',
        "add_location_name": '位置名称:',
        "add_location_name_placeholder": '可选，留空自动生成',
        "add_username": '用户名:',
        "add_password": '密码:',
        "add_username_placeholder": '可选，需要认证时填写',
        "add_password_placeholder": '可选',
        "account_scope": '账户归属:',
        "account_scope_target": '目标电脑本地账户（默认）',
        "account_scope_domain": 'AD 域或完整账户',
        "account_scope_microsoft": 'Microsoft 账户',
        "account_preview": '实际连接账户: {username}',
        "account_preview_empty": '实际连接账户: 未填写',
        "add_persistent": '登录后重新连接',
        "add_save_credential": '保存到 Windows 凭据管理器',
        "add_button": '添加',
        "adding": '正在添加...',
        "add_success": '添加成功',
        "add_error": '添加失败',
        "error_no_unc": '请输入网络路径',
        "error_invalid_unc": '网络路径格式无效，请使用 \\\\server\\share',
        "error_no_drive_add": '请选择一个驱动器盘符',
        "tip_add": '💡 可输入完整 UNC，或只输入 IP/主机名后点击“浏览共享”选择文件夹。映射驱动器/浏览共享时可填写可选凭据。',
        "confirm_add": '确定要添加吗？\n\n网络路径: {unc}\n类型: {mode}\n{extra}',
        "confirm_add_title": '确认添加',
        "add_mode_drive_desc": '映射网络驱动器',
        "add_mode_location_desc": '创建网络位置',
        "add_mode_both_desc": '同时映射驱动器并创建网络位置',
        "remove_title": '🗑️ 删除网络驱动器或位置',
        "remove_drives_section": '💿 网络驱动器',
        "remove_locations_section": '📁 网络位置',
        "remove_drive": '删除驱动器',
        "remove_location": '删除位置',
        "remove_no_drives": '没有可删除的网络驱动器',
        "remove_no_locations": '没有可删除的网络位置',
        "remove_sessions_section": '可清理的 SMB 连接',
        "remove_no_sessions": '没有检测到可枚举的 SMB 连接',
        "remove_session": '断开服务器会话',
        "confirm_remove_session": '确定断开服务器 {server} 的无盘符 SMB 会话吗？\n\n检测到的身份: {identity}\n\n已有映射盘会被保留；正在使用的文件可能导致断开失败。',
        "removing": '正在删除...',
        "remove_success": '删除成功',
        "remove_error": '删除失败',
        "confirm_remove_drive": '确定要删除网络驱动器吗？\n\n盘符: {drive}\nUNC路径: {unc}\n\n⚠️ 此操作将断开该驱动器映射。{cred_note}\n请确保没有正在使用该驱动器的文件！',
        "confirm_remove_location": '确定要删除网络位置吗？\n\n名称: {name}\nUNC路径: {unc}\n\n此操作将移除该网络位置快捷方式。{cred_note}',
        "confirm_remove_title": '确认删除',
        "tip_remove": '💡 可在此直接删除已映射的网络驱动器，或移除已创建的网络位置。勾选清理选项后，会断开该服务器残留的无盘符 SMB 会话（如 IPC$）并删除保存凭据；同一服务器的其他映射盘会保留。',
        "remove_also_credentials": '断开残留 SMB 会话并删除相关凭据',
        "cred_note_yes": '\n• 断开该服务器残留的无盘符 SMB 会话\n• 同时删除相关 Windows 凭据',
        "cred_note_no": '',
        "repair_title": '🛠 映射盘重连诊断与修复',
        "repair_drive": '映射盘:',
        "repair_diagnose": '诊断',
        "repair_username": '用户名:',
        "repair_password": '密码:',
        "repair_button": '分析后修复',
        "repair_no_drive": '没有可诊断的映射网络驱动器',
        "repair_ready": '选择映射盘并点击“诊断”',
        "repair_confirm_title": '确认重连修复',
        "repair_confirm": '将断开并重建以下映射，并替换该服务器的保存凭据：\n\n{report}\n\n⚠️ 如果驱动器正被文件或程序占用，修复将强制断开；未保存的数据可能丢失。\n\n确认继续吗？',
        "repair_success": '重连修复完成',
        "repair_error": '重连修复失败',
        "repair_credentials_required": '请输入用于重连的用户名；没有已保存密码时还需填写密码',
        "repair_password_optional": '可留空以优先复用已保存密码',
        "repair_reuse_password": '将优先复用 Windows 凭据管理器中已保存的密码。',
        "repair_test_deferred": '检测到现有 SMB 会话，Windows 无法在不先断开的情况下独立验证新密码；将在确认后的重建阶段验证。',
        "repair_tip": '修复会保存精确匹配 UNC 服务器的当前用户凭据，并重建持久映射。不会修改组策略或创建启动任务。',
    },
    "en": {
        "window_title": 'Drive ↔ Network Location Converter',
        "main_title": '🔄 Drive ↔ Network Location Converter',
        "subtitle": 'Bidirectional conversion between mapped drives and network locations',
        "tab_drive_to_loc": 'Drive → Network Location',
        "tab_loc_to_drive": 'Network Location → Drive',
        "tab_add": 'Add Drive/Location',
        "tab_remove": 'Remove Drive/Location',
        "tab_repair": 'Reconnect Repair',
        "mapped_drives": '💿 Mapped Network Drives',
        "network_locations": '📁 Network Locations',
        "refresh": '🔄 Refresh',
        "convert_to_location": 'Convert to Location',
        "convert_to_drive": 'Map as Drive',
        "drive_letter": 'Drive:',
        "no_drives": 'No mapped network drives detected',
        "no_locations": 'No network locations detected\n\nNetwork locations can be created via "Drive → Network Location" conversion or "Add Drive/Location"',
        "tip_drive_to_loc": '💡 Click "Convert to Location" to create a shortcut in Windows Network Locations and disconnect the drive mapping',
        "tip_loc_to_drive": '💡 Select an available drive letter, click "Map as Drive" to create drive mapping and delete the network location',
        "ready": 'Ready',
        "refreshed": 'List refreshed',
        "converting": 'Converting...',
        "confirm_drive_to_loc": 'Are you sure you want to convert drive {drive} to a network location?\n\nUNC Path: {unc}\n\n⚠️ This will:\n• Create a network location shortcut\n• Disconnect drive {drive} mapping\n\nMake sure no files are in use on this drive!',
        "confirm_loc_to_drive": 'Are you sure you want to convert the network location to a drive mapping?\n\nNetwork Location: {name}\nUNC Path: {unc}\nTarget Drive: {drive}\n\nThis will:\n• Map {drive} to {unc}\n• Delete network location {name}',
        "confirm_title": 'Confirm Conversion',
        "success": 'Conversion Successful',
        "error": 'Conversion Failed',
        "error_no_drive": 'Please select a drive letter',
        "files_in_use": 'Files In Use',
        "force_disconnect": '{msg}\n\nForce disconnect? (May cause unsaved data loss)',
        "lang_btn": '中文',
        "add_title": '➕ Add Network Drive or Location',
        "add_unc_label": 'Network Path (UNC / IP):',
        "add_unc_placeholder": 'e.g. \\\\server\\share or just IP: 192.168.1.10',
        "add_browse_shares": 'Browse Shares',
        "add_diagnose_browse": 'Diagnose',
        "diagnosing_browse": 'Diagnosing SMB browse identity...',
        "diagnose_browse_title": 'SMB Browse Identity Diagnosis',
        "test_credentials": 'Test Credentials',
        "testing_credentials": 'Testing username and password...',
        "test_credentials_title": 'SMB Credential Test',
        "clear_current_sessions": 'Clear Connections',
        "open_credential_manager": '🔐 Credential Manager',
        "credential_manager_opened": 'Windows Credential Manager opened',
        "credential_manager_error": 'Cannot Open Credential Manager',
        "confirm_clear_current_sessions": 'Clear drive-less SMB connections for {unc}?\n\nThe exact share, IPC$, and server root will be tried. Existing mapped drives are preserved.',
        "add_browsing_shares": 'Browsing shares...',
        "add_shares_label": 'Available shares (click to select):',
        "add_shares_empty": 'No shared folders found',
        "add_shares_hint": 'You can enter only an IP/hostname, then click Browse Shares',
        "add_include_hidden": 'Show hidden shares ($)',
        "error_no_server": 'Enter a server IP, hostname, or full UNC path',
        "error_browse_failed": 'Cannot Browse Shares',
        "browse_success": 'Shares found',
        "add_mode_label": 'Add as:',
        "add_mode_drive": 'Network Drive',
        "add_mode_location": 'Network Location',
        "add_mode_both": 'Both',
        "add_drive_letter": 'Drive:',
        "add_location_name": 'Location Name:',
        "add_location_name_placeholder": 'Optional, auto-generated if empty',
        "add_username": 'Username:',
        "add_password": 'Password:',
        "add_username_placeholder": 'Optional, if authentication is required',
        "add_password_placeholder": 'Optional',
        "account_scope": 'Account scope:',
        "account_scope_target": 'Target computer local account (default)',
        "account_scope_domain": 'AD domain or full identity',
        "account_scope_microsoft": 'Microsoft account',
        "account_preview": 'Effective identity: {username}',
        "account_preview_empty": 'Effective identity: not entered',
        "add_persistent": 'Reconnect at sign-in',
        "add_save_credential": 'Save in Windows Credential Manager',
        "add_button": 'Add',
        "adding": 'Adding...',
        "add_success": 'Added Successfully',
        "add_error": 'Add Failed',
        "error_no_unc": 'Please enter a network path',
        "error_invalid_unc": 'Invalid network path. Use \\\\server\\share',
        "error_no_drive_add": 'Please select a drive letter',
        "tip_add": '💡 Enter a full UNC path, or just an IP/hostname and click Browse Shares to pick a folder. Optional credentials are used for drive mapping and share browsing.',
        "confirm_add": 'Are you sure you want to add this?\n\nNetwork Path: {unc}\nType: {mode}\n{extra}',
        "confirm_add_title": 'Confirm Add',
        "add_mode_drive_desc": 'Map network drive',
        "add_mode_location_desc": 'Create network location',
        "add_mode_both_desc": 'Map drive and create network location',
        "remove_title": '🗑️ Remove Network Drive or Location',
        "remove_drives_section": '💿 Network Drives',
        "remove_locations_section": '📁 Network Locations',
        "remove_drive": 'Remove Drive',
        "remove_location": 'Remove Location',
        "remove_no_drives": 'No network drives to remove',
        "remove_no_locations": 'No network locations to remove',
        "remove_sessions_section": 'Clearable SMB Connections',
        "remove_no_sessions": 'No enumerable SMB connections detected',
        "remove_session": 'Disconnect Server',
        "confirm_remove_session": 'Disconnect drive-less SMB sessions for {server}?\n\nDetected identity: {identity}\n\nMapped drives are preserved; open files may prevent disconnection.',
        "removing": 'Removing...',
        "remove_success": 'Removed Successfully',
        "remove_error": 'Remove Failed',
        "confirm_remove_drive": 'Are you sure you want to remove this network drive?\n\nDrive: {drive}\nUNC Path: {unc}\n\n⚠️ This will disconnect the drive mapping.{cred_note}\nMake sure no files are in use on this drive!',
        "confirm_remove_location": 'Are you sure you want to remove this network location?\n\nName: {name}\nUNC Path: {unc}\n\nThis will delete the network location shortcut.{cred_note}',
        "confirm_remove_title": 'Confirm Removal',
        "tip_remove": '💡 Remove a mapped drive or network location here. When cleanup is checked, the app disconnects leftover SMB sessions without drive letters (such as IPC$) and deletes saved credentials. Other mapped drives on the same server are preserved.',
        "remove_also_credentials": 'Disconnect leftover SMB sessions and delete related credentials',
        "cred_note_yes": '\n• Disconnect leftover SMB sessions without drive letters\n• Also delete related Windows credentials',
        "cred_note_no": '',
        "repair_title": '🛠 Mapped Drive Reconnect Diagnosis and Repair',
        "repair_drive": 'Mapped drive:',
        "repair_diagnose": 'Diagnose',
        "repair_username": 'Username:',
        "repair_password": 'Password:',
        "repair_button": 'Review and Repair',
        "repair_no_drive": 'No mapped network drive is available',
        "repair_ready": 'Select a mapped drive and click Diagnose',
        "repair_confirm_title": 'Confirm Reconnect Repair',
        "repair_confirm": 'The mapping below will be disconnected and rebuilt, and the saved credential for its server will be replaced:\n\n{report}\n\n⚠️ If files or applications are using the drive, repair will force-disconnect it and unsaved data may be lost.\n\nContinue?',
        "repair_success": 'Reconnect Repair Completed',
        "repair_error": 'Reconnect Repair Failed',
        "repair_credentials_required": 'Enter a username; a password is required only when none is saved',
        "repair_password_optional": 'Leave blank to reuse the saved password first',
        "repair_reuse_password": 'The saved Windows credential password will be reused first.',
        "repair_test_deferred": 'An existing SMB session prevents an isolated password test without disconnecting it first. The credential will be verified during the confirmed rebuild.',
        "repair_tip": 'Repair saves a current-user credential that exactly matches the UNC server and rebuilds a persistent mapping. It does not change Group Policy or create startup tasks.',
    }
}


class DriveNetworkConverter(ctk.CTk):
    """主应用程序窗口"""
    
    def __init__(self):
        super().__init__()
        
        # 语言设置
        self.current_lang = "zh"
        self.texts = LANGUAGES[self.current_lang]
        
        # 窗口配置
        self.title(self.texts["window_title"])
        self.geometry("850x750")
        self.minsize(500, 400)  # 允许缩小到较小尺寸
        
        # 主题设置
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # 数据
        self.mapped_drives = []
        self.network_locations = []
        self.available_drives = []
        self.refresh_data()
        
        # 创建UI
        self.create_widgets()
    
    def get_text(self, key):
        """获取当前语言的文本"""
        return self.texts.get(key, key)
    
    def switch_language(self):
        """切换语言"""
        self.current_lang = "en" if self.current_lang == "zh" else "zh"
        self.texts = LANGUAGES[self.current_lang]
        
        # 更新窗口标题
        self.title(self.texts["window_title"])
        
        # 重建UI
        for widget in self.main_frame.winfo_children():
            widget.destroy()
        self.create_ui_content()
    
    def refresh_data(self):
        """刷新数据"""
        self.mapped_drives = get_mapped_drives()
        self.available_drives = get_available_drive_letters()
        try:
            self.network_locations = get_network_locations()
        except Exception:
            self.network_locations = []
        try:
            self.smb_sessions, self.smb_sessions_error = get_clearable_smb_connections()
        except Exception as exc:
            self.smb_sessions, self.smb_sessions_error = [], str(exc)
    
    def create_widgets(self):
        """创建所有UI组件"""
        
        # 主容器
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        self.create_ui_content()
    
    def create_ui_content(self):
        """创建UI内容（可重建）"""
        
        # ===== 顶部栏：标题 + 语言按钮 =====
        top_bar = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 5))
        
        self.title_label = ctk.CTkLabel(
            top_bar,
            text=self.get_text("main_title"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=22)
        )
        self.title_label.pack(side="left")
        
        # 语言切换按钮
        self.lang_btn = ctk.CTkButton(
            top_bar,
            text=self.get_text("lang_btn"),
            width=60,
            height=30,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            fg_color="#555555",
            hover_color="#666666",
            command=self.switch_language
        )
        self.lang_btn.pack(side="right")
        
        self.subtitle_label = ctk.CTkLabel(
            self.main_frame,
            text=self.get_text("subtitle"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=14),
            text_color="gray"
        )
        self.subtitle_label.pack(pady=(0, 15))
        
        # ===== 选项卡 =====
        self.tabview = ctk.CTkTabview(self.main_frame)
        self.tabview.pack(fill="both", expand=True)
        
        # 设置选项卡字体
        self.tabview._segmented_button.configure(
            font=ctk.CTkFont(family=SYSTEM_FONT, size=14)
        )
        
        # 创建选项卡
        self.tab_drive_to_loc = self.tabview.add(self.get_text("tab_drive_to_loc"))
        self.tab_loc_to_drive = self.tabview.add(self.get_text("tab_loc_to_drive"))
        self.tab_add = self.tabview.add(self.get_text("tab_add"))
        self.tab_repair = self.tabview.add(self.get_text("tab_repair"))
        self.tab_remove = self.tabview.add(self.get_text("tab_remove"))
        
        # 构建选项卡内容
        self.create_drive_to_location_tab()
        self.create_location_to_drive_tab()
        self.create_add_tab()
        self.create_repair_tab()
        self.create_remove_tab()
        
        # ===== 状态栏 =====
        self.status_frame = ctk.CTkFrame(self.main_frame, height=35)
        self.status_frame.pack(fill="x", pady=(10, 0))
        
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text=self.get_text("ready"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=14),
            text_color="gray"
        )
        self.status_label.pack(padx=15, pady=8)
    
    # ==================== 驱动器 → 网络位置 选项卡 ====================
    
    def create_drive_to_location_tab(self):
        """创建驱动器转网络位置的选项卡"""
        tab = self.tab_drive_to_loc
        
        # 标题
        header = ctk.CTkFrame(tab, fg_color="transparent")
        header.pack(fill="x", pady=(10, 10))
        
        ctk.CTkLabel(
            header,
            text=self.get_text("mapped_drives"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=16)
        ).pack(side="left")
        
        ctk.CTkButton(
            header,
            text=self.get_text("refresh"),
            width=90,
            height=28,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=12),
            command=self.on_refresh
        ).pack(side="right")
        
        # 驱动器列表
        self.drives_list_frame = ctk.CTkScrollableFrame(tab, height=200)
        self.drives_list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        self.update_drives_list()
        
        # 说明
        info = ctk.CTkFrame(tab, fg_color="#1a3a5c")
        info.pack(fill="x", pady=(5, 0))
        
        tip_label = ctk.CTkLabel(
            info,
            text=self.get_text("tip_drive_to_loc"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            text_color="#a0c4e0",
            wraplength=600
        )
        tip_label.pack(padx=15, pady=10, fill="x")
    
    def update_drives_list(self):
        """更新驱动器列表"""
        for widget in self.drives_list_frame.winfo_children():
            widget.destroy()
        
        if not self.mapped_drives:
            ctk.CTkLabel(
                self.drives_list_frame,
                text=self.get_text("no_drives"),
                text_color="gray",
                font=ctk.CTkFont(family=SYSTEM_FONT, size=15)
            ).pack(pady=40)
            return
        
        for drive, unc in self.mapped_drives:
            row = ctk.CTkFrame(self.drives_list_frame, height=50)
            row.pack(fill="x", pady=3)
            row.pack_propagate(False)
            
            ctk.CTkLabel(
                row,
                text=f"💿 {drive}",
                font=ctk.CTkFont(family=SYSTEM_FONT, size=16),
                width=80
            ).pack(side="left", padx=(10, 0))
            
            ctk.CTkLabel(
                row,
                text="→",
                font=ctk.CTkFont(size=16),
                text_color="#4dabf7"
            ).pack(side="left", padx=10)
            
            ctk.CTkLabel(
                row,
                text=unc,
                font=ctk.CTkFont(family=SYSTEM_FONT, size=14),
                text_color="#d0d0d0"
            ).pack(side="left", fill="x", expand=True)
            
            ctk.CTkButton(
                row,
                text=self.get_text("convert_to_location"),
                width=140,
                height=32,
                font=ctk.CTkFont(family=SYSTEM_FONT, size=12),
                fg_color="#2e7d32",
                hover_color="#1b5e20",
                command=lambda d=drive, u=unc: self.on_convert_drive_to_location(d, u)
            ).pack(side="right", padx=10)
    
    def on_convert_drive_to_location(self, drive, unc):
        """转换驱动器为网络位置"""
        msg = self.get_text("confirm_drive_to_loc").format(drive=drive, unc=unc)
        
        if not messagebox.askyesno(self.get_text("confirm_title"), msg, icon="warning"):
            return
        
        self.set_status(self.get_text("converting"), color="yellow")
        self.update()
        
        success, message = convert_drive_to_network_location(drive, force=False)
        
        if success:
            self.set_status(message, color="green")
            self.refresh_data()
            self.update_drives_list()
            self.update_locations_list()
            self.update_add_drive_letters()
            self.update_remove_lists()
            messagebox.showinfo(self.get_text("success"), message)
        else:
            self.set_status(f"❌ {message}", color="red")
            
            if "正在使用" in message or "in use" in message.lower():
                force_msg = self.get_text("force_disconnect").format(msg=message)
                if messagebox.askyesno(self.get_text("files_in_use"), force_msg, icon="warning"):
                    success, message = convert_drive_to_network_location(drive, force=True)
                    if success:
                        self.set_status(message, color="green")
                        self.refresh_data()
                        self.update_drives_list()
                        self.update_locations_list()
                        self.update_add_drive_letters()
                        self.update_remove_lists()
                        messagebox.showinfo(self.get_text("success"), message)
                    else:
                        messagebox.showerror(self.get_text("error"), message)
            else:
                messagebox.showerror(self.get_text("error"), message)
    
    # ==================== 网络位置 → 驱动器 选项卡 ====================
    
    def create_location_to_drive_tab(self):
        """创建网络位置转驱动器的选项卡"""
        tab = self.tab_loc_to_drive
        
        # 标题
        header = ctk.CTkFrame(tab, fg_color="transparent")
        header.pack(fill="x", pady=(10, 10))
        
        ctk.CTkLabel(
            header,
            text=self.get_text("network_locations"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=16)
        ).pack(side="left")
        
        ctk.CTkButton(
            header,
            text=self.get_text("refresh"),
            width=90,
            height=28,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=12),
            command=self.on_refresh
        ).pack(side="right")
        
        # 网络位置列表
        self.locations_list_frame = ctk.CTkScrollableFrame(tab, height=200)
        self.locations_list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        self.update_locations_list()
        
        # 说明
        info = ctk.CTkFrame(tab, fg_color="#3a1a5c")
        info.pack(fill="x", pady=(5, 0))
        
        tip_label2 = ctk.CTkLabel(
            info,
            text=self.get_text("tip_loc_to_drive"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            text_color="#c4a0e0",
            wraplength=600
        )
        tip_label2.pack(padx=15, pady=10, fill="x")
    
    def update_locations_list(self):
        """更新网络位置列表"""
        for widget in self.locations_list_frame.winfo_children():
            widget.destroy()
        
        if not self.network_locations:
            ctk.CTkLabel(
                self.locations_list_frame,
                text=self.get_text("no_locations"),
                text_color="gray",
                font=ctk.CTkFont(family=SYSTEM_FONT, size=15)
            ).pack(pady=40)
            return
        
        for name, unc in self.network_locations:
            row = ctk.CTkFrame(self.locations_list_frame, height=55)
            row.pack(fill="x", pady=3)
            row.pack_propagate(False)
            
            # 名称和路径
            info_frame = ctk.CTkFrame(row, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, padx=(10, 0))
            
            ctk.CTkLabel(
                info_frame,
                text=f"📁 {name}",
                font=ctk.CTkFont(family=SYSTEM_FONT, size=15),
                anchor="w"
            ).pack(fill="x", pady=(5, 0))
            
            ctk.CTkLabel(
                info_frame,
                text=unc,
                font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
                text_color="#d0d0d0",
                anchor="w"
            ).pack(fill="x")
            
            # 盘符选择器
            drive_var = ctk.StringVar(value=self.available_drives[0] if self.available_drives else "")
            
            drive_selector = ctk.CTkComboBox(
                row,
                values=self.available_drives,
                variable=drive_var,
                width=70,
                height=32,
                font=ctk.CTkFont(family=SYSTEM_FONT, size=13)
            )
            drive_selector.pack(side="right", padx=5)
            
            ctk.CTkLabel(
                row,
                text=self.get_text("drive_letter"),
                font=ctk.CTkFont(family=SYSTEM_FONT, size=14),
                text_color="gray"
            ).pack(side="right", padx=(10, 5))
            
            ctk.CTkButton(
                row,
                text=self.get_text("convert_to_drive"),
                width=130,
                height=32,
                font=ctk.CTkFont(family=SYSTEM_FONT, size=12),
                fg_color="#5c2e7d",
                hover_color="#3d1b5e",
                command=lambda n=name, dv=drive_var: self.on_convert_location_to_drive(n, dv.get())
            ).pack(side="right", padx=10)
    
    def on_convert_location_to_drive(self, location_name, drive_letter):
        """转换网络位置为驱动器"""
        if not drive_letter:
            messagebox.showerror(self.get_text("error"), self.get_text("error_no_drive"))
            return
        
        # 获取UNC路径
        unc = None
        for name, path in self.network_locations:
            if name == location_name:
                unc = path
                break
        
        msg = self.get_text("confirm_loc_to_drive").format(
            name=location_name, unc=unc, drive=drive_letter
        )
        
        if not messagebox.askyesno(self.get_text("confirm_title"), msg, icon="question"):
            return
        
        self.set_status(self.get_text("converting"), color="yellow")
        self.update()
        
        success, message = convert_network_location_to_drive(location_name, drive_letter)
        
        if success:
            self.set_status(message, color="green")
            self.refresh_data()
            self.update_drives_list()
            self.update_locations_list()
            self.update_add_drive_letters()
            self.update_remove_lists()
            messagebox.showinfo(self.get_text("success"), message)
        else:
            self.set_status(f"❌ {message}", color="red")
            messagebox.showerror(self.get_text("error"), message)
    

    # ==================== 添加网络驱动器/位置 选项卡 ====================

    def create_add_tab(self):
        """创建添加网络驱动器或位置的选项卡"""
        tab = self.tab_add

        form = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        form.pack(fill="both", expand=True, pady=(10, 10))

        ctk.CTkLabel(
            form,
            text=self.get_text("add_title"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=16),
            anchor="w",
        ).pack(fill="x", pady=(0, 12))

        # UNC / IP
        ctk.CTkLabel(
            form,
            text=self.get_text("add_unc_label"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=14),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        unc_row = ctk.CTkFrame(form, fg_color="transparent")
        unc_row.pack(fill="x", pady=(0, 4))

        self.add_unc_entry = ctk.CTkEntry(
            unc_row,
            placeholder_text=self.get_text("add_unc_placeholder"),
            height=36,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=14),
        )
        self.add_unc_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.add_unc_entry.bind("<KeyRelease>", lambda _event: self._schedule_add_account_preview())

        self.add_browse_btn = ctk.CTkButton(
            unc_row,
            text=self.get_text("add_browse_shares"),
            width=110,
            height=36,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            fg_color="#2e7d32",
            hover_color="#1b5e20",
            command=self.on_browse_shares,
        )
        self.add_browse_btn.pack(side="left")

        self.add_diagnose_btn = ctk.CTkButton(
            unc_row,
            text=self.get_text("add_diagnose_browse"),
            width=100,
            height=36,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            fg_color="#6a1b9a",
            hover_color="#4a148c",
            command=self.on_diagnose_share_browse,
        )
        self.add_diagnose_btn.pack(side="left", padx=(8, 0))

        ctk.CTkLabel(
            form,
            text=self.get_text("add_shares_hint"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=12),
            text_color=("#5a6a7a", "#9aa8b5"),
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        # Optional credentials (mapping + browsing)
        self.add_cred_options = ctk.CTkFrame(form, fg_color=("#eef3e8", "#1f2a1f"))
        self.add_cred_options.pack(fill="x", pady=(0, 10))
        cred_inner = ctk.CTkFrame(self.add_cred_options, fg_color="transparent")
        cred_inner.pack(fill="x", padx=12, pady=10)

        scope_row = ctk.CTkFrame(cred_inner, fg_color="transparent")
        scope_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            scope_row,
            text=self.get_text("account_scope"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        ).pack(side="left", padx=(0, 8))
        self.add_account_scope_var = ctk.StringVar(value=self.get_text("account_scope_target"))
        self.add_account_scope_combo = ctk.CTkComboBox(
            scope_row,
            values=self._account_scope_labels(),
            variable=self.add_account_scope_var,
            state="readonly",
            width=260,
            height=32,
            command=lambda _value: self._schedule_add_account_preview(),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        )
        self.add_account_scope_combo.pack(side="left")

        cred_row = ctk.CTkFrame(cred_inner, fg_color="transparent")
        cred_row.pack(fill="x")

        user_col = ctk.CTkFrame(cred_row, fg_color="transparent")
        user_col.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(
            user_col,
            text=self.get_text("add_username"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            anchor="w",
        ).pack(fill="x")
        self.add_username_entry = ctk.CTkEntry(
            user_col,
            placeholder_text=self.get_text("add_username_placeholder"),
            height=32,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        )
        self.add_username_entry.pack(fill="x", pady=(4, 0))
        self.add_username_entry.bind("<KeyRelease>", lambda _event: self._schedule_add_account_preview())

        pass_col = ctk.CTkFrame(cred_row, fg_color="transparent")
        pass_col.pack(side="left", fill="x", expand=True, padx=(8, 0))
        ctk.CTkLabel(
            pass_col,
            text=self.get_text("add_password"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            anchor="w",
        ).pack(fill="x")
        self.add_password_entry = ctk.CTkEntry(
            pass_col,
            placeholder_text=self.get_text("add_password_placeholder"),
            height=32,
            show="*",
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        )
        self.add_password_entry.pack(fill="x", pady=(4, 0))

        self.add_account_preview_label = ctk.CTkLabel(
            cred_inner,
            text=self.get_text("account_preview_empty"),
            anchor="w",
            text_color=("#356035", "#9bc49b"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=12),
        )
        self.add_account_preview_label.pack(fill="x", pady=(8, 0))

        cred_action_row = ctk.CTkFrame(cred_inner, fg_color="transparent")
        cred_action_row.pack(fill="x", pady=(10, 0))

        self.add_test_credentials_btn = ctk.CTkButton(
            cred_action_row,
            text=self.get_text("test_credentials"),
            width=130,
            height=32,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            fg_color="#ad6517",
            hover_color="#7f480d",
            command=self.on_test_credentials,
        )
        self.add_test_credentials_btn.pack(side="right")

        self.add_clear_sessions_btn = ctk.CTkButton(
            cred_action_row,
            text=self.get_text("clear_current_sessions"),
            width=130,
            height=32,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            fg_color="#6d4c41",
            hover_color="#4e342e",
            command=self.on_clear_current_server_sessions,
        )
        self.add_clear_sessions_btn.pack(side="right", padx=(0, 8))

        # Share list container
        self.add_shares_frame = ctk.CTkFrame(form, fg_color=("#e8f0e8", "#1c2a1c"))
        shares_header = ctk.CTkFrame(self.add_shares_frame, fg_color="transparent")
        shares_header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            shares_header,
            text=self.get_text("add_shares_label"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        self.add_include_hidden_var = ctk.BooleanVar(value=False)
        self.add_include_hidden_check = ctk.CTkCheckBox(
            shares_header,
            text=self.get_text("add_include_hidden"),
            variable=self.add_include_hidden_var,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=12),
            command=self.on_browse_shares,
        )
        self.add_include_hidden_check.pack(side="right")
        self.add_shares_list = ctk.CTkScrollableFrame(
            self.add_shares_frame,
            fg_color="transparent",
            height=140,
        )
        self.add_shares_list.pack(fill="x", padx=8, pady=(0, 10))
        self._add_share_items = []

        # Mode
        ctk.CTkLabel(
            form,
            text=self.get_text("add_mode_label"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=14),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        self.add_mode_var = ctk.StringVar(value="drive")
        mode_row = ctk.CTkFrame(form, fg_color="transparent")
        mode_row.pack(fill="x", pady=(0, 12))

        self.add_mode_drive_radio = ctk.CTkRadioButton(
            mode_row,
            text=self.get_text("add_mode_drive"),
            variable=self.add_mode_var,
            value="drive",
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            command=self.on_add_mode_changed,
        )
        self.add_mode_drive_radio.pack(side="left", padx=(0, 16))

        self.add_mode_location_radio = ctk.CTkRadioButton(
            mode_row,
            text=self.get_text("add_mode_location"),
            variable=self.add_mode_var,
            value="location",
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            command=self.on_add_mode_changed,
        )
        self.add_mode_location_radio.pack(side="left", padx=(0, 16))

        self.add_mode_both_radio = ctk.CTkRadioButton(
            mode_row,
            text=self.get_text("add_mode_both"),
            variable=self.add_mode_var,
            value="both",
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            command=self.on_add_mode_changed,
        )
        self.add_mode_both_radio.pack(side="left")

        # Drive options frame
        self.add_drive_options = ctk.CTkFrame(form, fg_color=("#e8eef5", "#1f2a36"))
        self.add_drive_options.pack(fill="x", pady=(0, 10))

        drive_inner = ctk.CTkFrame(self.add_drive_options, fg_color="transparent")
        drive_inner.pack(fill="x", padx=12, pady=12)

        drive_row = ctk.CTkFrame(drive_inner, fg_color="transparent")
        drive_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            drive_row,
            text=self.get_text("add_drive_letter"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=14),
            width=90,
            anchor="w",
        ).pack(side="left")

        self.add_drive_var = ctk.StringVar(
            value=self.available_drives[0] if self.available_drives else ""
        )
        self.add_drive_combo = ctk.CTkComboBox(
            drive_row,
            values=self.available_drives or [""],
            variable=self.add_drive_var,
            width=100,
            height=32,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        )
        self.add_drive_combo.pack(side="left")

        self.add_persistent_var = ctk.BooleanVar(value=True)
        self.add_persistent_check = ctk.CTkCheckBox(
            drive_row,
            text=self.get_text("add_persistent"),
            variable=self.add_persistent_var,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        )
        self.add_persistent_check.pack(side="left", padx=(20, 0))

        self.add_save_credential_var = ctk.BooleanVar(value=False)
        self.add_save_credential_check = ctk.CTkCheckBox(
            drive_inner,
            text=self.get_text("add_save_credential"),
            variable=self.add_save_credential_var,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        )
        self.add_save_credential_check.pack(anchor="w", pady=(4, 0))

        # Location options frame
        self.add_location_options = ctk.CTkFrame(form, fg_color=("#efe8f5", "#2a1f36"))
        self.add_location_options.pack(fill="x", pady=(0, 10))

        loc_inner = ctk.CTkFrame(self.add_location_options, fg_color="transparent")
        loc_inner.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(
            loc_inner,
            text=self.get_text("add_location_name"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=14),
            anchor="w",
        ).pack(fill="x")
        self.add_location_name_entry = ctk.CTkEntry(
            loc_inner,
            placeholder_text=self.get_text("add_location_name_placeholder"),
            height=32,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        )
        self.add_location_name_entry.pack(fill="x", pady=(4, 0))

        # Button
        action_row = ctk.CTkFrame(form, fg_color="transparent")
        action_row.pack(fill="x", pady=(4, 8))

        self.add_submit_btn = ctk.CTkButton(
            action_row,
            text=self.get_text("add_button"),
            width=140,
            height=36,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=14),
            fg_color="#1565c0",
            hover_color="#0d47a1",
            command=self.on_add_network,
        )
        self.add_submit_btn.pack(side="left")

        # Tip
        tip = ctk.CTkFrame(tab, fg_color="#1a3a5c")
        tip.pack(fill="x", pady=(0, 0))
        ctk.CTkLabel(
            tip,
            text=self.get_text("tip_add"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            text_color="#a0c4e0",
            wraplength=700,
            justify="left",
            anchor="w",
        ).pack(padx=15, pady=10, fill="x")

        self.on_add_mode_changed()


    def _account_scope_labels(self):
        return [
            self.get_text("account_scope_target"),
            self.get_text("account_scope_domain"),
            self.get_text("account_scope_microsoft"),
        ]

    def _account_scope_value(self, selected):
        labels = self._account_scope_labels()
        values = [ACCOUNT_SCOPE_TARGET, ACCOUNT_SCOPE_DOMAIN, ACCOUNT_SCOPE_MICROSOFT]
        try:
            return values[labels.index(selected)]
        except ValueError:
            return ACCOUNT_SCOPE_TARGET

    def _normalized_ui_identity(self, raw_path, username, selected_scope):
        server = normalize_server_name(raw_path)
        if not username:
            return True, "", ""
        if not server:
            return False, "", self.get_text("error_no_server")
        return normalize_account_identity(
            server, username, self._account_scope_value(selected_scope)
        )

    def _update_add_account_preview(self):
        if not hasattr(self, "add_account_preview_label"):
            return
        raw = self.add_unc_entry.get().strip() if hasattr(self, "add_unc_entry") else ""
        username = self.add_username_entry.get().strip() if hasattr(self, "add_username_entry") else ""
        selected = self.add_account_scope_var.get()
        ok, identity, error = self._normalized_ui_identity(raw, username, selected)
        if not username:
            text = self.get_text("account_preview_empty")
        elif ok:
            text = self.get_text("account_preview").format(username=identity)
        else:
            text = error
        self.add_account_preview_label.configure(text=text, text_color=("#356035", "#9bc49b") if ok else "#d05a5a")

    def _schedule_add_account_preview(self):
        pending = getattr(self, "_add_account_preview_after", None)
        if pending:
            try:
                self.after_cancel(pending)
            except Exception:
                pass
        self._add_account_preview_after = self.after(400, self._update_add_account_preview)

    def on_browse_shares(self):
        """根据 IP/主机名浏览对方共享文件夹"""
        raw = self.add_unc_entry.get().strip() if hasattr(self, "add_unc_entry") else ""
        server = normalize_server_name(raw)
        if not server:
            messagebox.showerror(self.get_text("add_error"), self.get_text("error_no_server"))
            return

        username = self.add_username_entry.get().strip() if hasattr(self, "add_username_entry") else ""
        password = self.add_password_entry.get() if hasattr(self, "add_password_entry") else ""
        identity_ok, username, identity_error = self._normalized_ui_identity(
            raw, username, self.add_account_scope_var.get()
        )
        if not identity_ok:
            messagebox.showerror(self.get_text("add_error"), identity_error)
            return
        include_hidden = (
            self.add_include_hidden_var.get()
            if hasattr(self, "add_include_hidden_var")
            else False
        )

        self.set_status(self.get_text("add_browsing_shares"), color="yellow")
        if hasattr(self, "add_browse_btn"):
            self.add_browse_btn.configure(state="disabled")
        self.update()

        try:
            success, message, shares = list_server_shares(
                server,
                username=username or None,
                password=password or None,
                include_hidden=include_hidden,
                include_special=include_hidden,
            )
        finally:
            if hasattr(self, "add_browse_btn"):
                self.add_browse_btn.configure(state="normal")

        if not success:
            first_line = message.splitlines()[0] if message else self.get_text("error_browse_failed")
            self.set_status(f"❌ {first_line}", color="red")
            self._render_share_list([])
            self.show_detail_error(self.get_text("error_browse_failed"), message)
            return

        self._render_share_list(shares)
        if shares:
            self.set_status(f"{self.get_text('browse_success')}: {message}", color="green")
        else:
            self.set_status(message, color="yellow")
            messagebox.showinfo(self.get_text("browse_success"), message)

    def on_diagnose_share_browse(self):
        """排查为什么未输入凭据仍能枚举指定服务器的共享。"""
        raw = self.add_unc_entry.get().strip() if hasattr(self, "add_unc_entry") else ""
        server = normalize_server_name(raw)
        if not server:
            messagebox.showerror(self.get_text("add_error"), self.get_text("error_no_server"))
            return

        self.set_status(self.get_text("diagnosing_browse"), color="yellow")
        if hasattr(self, "add_diagnose_btn"):
            self.add_diagnose_btn.configure(state="disabled")
        self.update()

        try:
            success, report = diagnose_share_browse_identity(server)
        finally:
            if hasattr(self, "add_diagnose_btn"):
                self.add_diagnose_btn.configure(state="normal")

        if success:
            self.set_status(self.get_text("diagnose_browse_title"), color="green")
        else:
            self.set_status(f"❌ {report}", color="red")
        self.show_detail_error(self.get_text("diagnose_browse_title"), report)

    def on_test_credentials(self):
        """Test entered credentials against the selected concrete share."""
        unc = self.add_unc_entry.get().strip() if hasattr(self, "add_unc_entry") else ""
        username = self.add_username_entry.get().strip() if hasattr(self, "add_username_entry") else ""
        password = self.add_password_entry.get() if hasattr(self, "add_password_entry") else ""
        identity_ok, username, identity_error = self._normalized_ui_identity(
            unc, username, self.add_account_scope_var.get()
        )
        if not identity_ok:
            messagebox.showerror(self.get_text("add_error"), identity_error)
            return

        self.set_status(self.get_text("testing_credentials"), color="yellow")
        self.add_test_credentials_btn.configure(state="disabled")
        self.update()
        try:
            success, report = test_share_credentials(unc, username, password)
        finally:
            self.add_test_credentials_btn.configure(state="normal")

        self.set_status(
            self.get_text("test_credentials_title") if success else report.splitlines()[-1],
            color="green" if success else "red",
        )
        self.show_detail_error(self.get_text("test_credentials_title"), report)

    def on_clear_current_server_sessions(self):
        """Clear hidden SMB state using the exact UNC entered by the user."""
        raw = self.add_unc_entry.get().strip() if hasattr(self, "add_unc_entry") else ""
        unc = normalize_unc_path(raw)
        if not unc:
            messagebox.showerror(self.get_text("add_error"), self.get_text("error_invalid_unc"))
            return
        msg = self.get_text("confirm_clear_current_sessions").format(unc=unc)
        if not messagebox.askyesno(self.get_text("confirm_remove_title"), msg, icon="warning"):
            return
        self.add_clear_sessions_btn.configure(state="disabled")
        self.set_status(self.get_text("removing"), color="yellow")
        self.update()
        try:
            success, message, removed = disconnect_server_sessions(unc, force=True)
            server = normalize_server_name(unc)
            remaining, check_error = get_clearable_smb_connections()
            remaining = [
                item for item in remaining
                if str(item.get("ServerName") or "").casefold() == str(server).casefold()
            ]
            if remaining:
                success = False
                shares = ", ".join(sorted({str(i.get("ShareName") or "(server)") for i in remaining}))
                message += "\n仍检测到连接: " + shares
            elif check_error:
                message += "\n复查提示: " + check_error
            elif removed:
                message += "\n已复查：Get-SmbConnection 中未再发现该服务器。"
        finally:
            self.add_clear_sessions_btn.configure(state="normal")
        self.refresh_data()
        if hasattr(self, "remove_list_frame"):
            self.update_remove_lists()
        self.set_status(message, color="green" if success else "red")
        if success:
            messagebox.showinfo(self.get_text("remove_success"), message)
        else:
            self.show_detail_error(self.get_text("remove_error"), message)

    def _render_share_list(self, shares):
        """渲染共享列表"""
        if not hasattr(self, "add_shares_list"):
            return

        for child in self.add_shares_list.winfo_children():
            child.destroy()
        self._add_share_items = list(shares or [])

        if shares:
            if not self.add_shares_frame.winfo_ismapped():
                self.add_shares_frame.pack(fill="x", pady=(0, 10), after=self.add_cred_options)
        else:
            if self.add_shares_frame.winfo_ismapped():
                self.add_shares_frame.pack_forget()
            return

        for item in shares:
            name = item.get("name", "")
            unc = item.get("unc", "")
            remark = (item.get("remark") or "").strip()
            label = name if not remark else f"{name}  —  {remark}"
            if item.get("is_hidden"):
                label = f"{label}  [$]"

            row = ctk.CTkFrame(self.add_shares_list, fg_color=("#f7fbf7", "#243024"))
            row.pack(fill="x", padx=4, pady=3)

            btn = ctk.CTkButton(
                row,
                text=label,
                anchor="w",
                height=32,
                font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
                fg_color="transparent",
                hover_color=("#d9ecd9", "#2f3f2f"),
                text_color=("#1b5e20", "#c8e6c9"),
                command=lambda u=unc: self.on_select_share(u),
            )
            btn.pack(fill="x", padx=4, pady=2)

            path_preview = ctk.CTkEntry(
                row,
                font=ctk.CTkFont(family=SYSTEM_FONT, size=11),
                text_color=("#6a7a6a", "#8a9a8a"),
                fg_color="transparent",
                border_width=0,
                height=24,
            )
            path_preview.insert(0, unc)
            # A read-only entry keeps the path selectable and copyable without
            # allowing accidental edits to the preview.
            path_preview.configure(state="readonly")
            path_preview.pack(fill="x", padx=7, pady=(0, 4))

    def on_select_share(self, unc_path):
        """选择共享后填入 UNC 输入框"""
        if not hasattr(self, "add_unc_entry"):
            return
        self.add_unc_entry.delete(0, "end")
        self.add_unc_entry.insert(0, unc_path)
        self.set_status(f"✓ {unc_path}", color="green")

    def on_add_mode_changed(self):
        """根据添加类型显示/隐藏相关选项"""
        mode = self.add_mode_var.get() if hasattr(self, "add_mode_var") else "drive"

        if hasattr(self, "add_drive_options"):
            if mode in ("drive", "both"):
                self.add_drive_options.pack(fill="x", pady=(0, 10))
            else:
                self.add_drive_options.pack_forget()

        if hasattr(self, "add_location_options"):
            if mode in ("location", "both"):
                self.add_location_options.pack(fill="x", pady=(0, 10))
            else:
                self.add_location_options.pack_forget()

    def update_add_drive_letters(self):
        """刷新添加页的可用盘符"""
        if not hasattr(self, "add_drive_combo"):
            return
        values = self.available_drives or [""]
        self.add_drive_combo.configure(values=values)
        current = self.add_drive_var.get() if hasattr(self, "add_drive_var") else ""
        if current not in values:
            self.add_drive_var.set(values[0])

    def on_add_network(self):
        """处理添加网络驱动器/位置"""
        raw_unc = self.add_unc_entry.get().strip()
        if not raw_unc:
            messagebox.showerror(self.get_text("add_error"), self.get_text("error_no_unc"))
            return

        unc = normalize_unc_path(raw_unc)
        if not unc:
            server = normalize_server_name(raw_unc)
            if server:
                messagebox.showerror(
                    self.get_text("add_error"),
                    self.get_text("error_invalid_unc")
                    + "\n\n"
                    + self.get_text("add_shares_hint"),
                )
            else:
                messagebox.showerror(self.get_text("add_error"), self.get_text("error_invalid_unc"))
            return

        mode = self.add_mode_var.get()
        drive_letter = self.add_drive_var.get() if mode in ("drive", "both") else None
        location_name = (
            self.add_location_name_entry.get().strip()
            if mode in ("location", "both")
            else None
        )
        username = self.add_username_entry.get().strip() if mode in ("drive", "both") else None
        password = self.add_password_entry.get() if mode in ("drive", "both") else None
        account_scope = self._account_scope_value(self.add_account_scope_var.get())
        persistent = self.add_persistent_var.get() if mode in ("drive", "both") else True
        save_credential = (
            self.add_save_credential_var.get()
            if mode in ("drive", "both") and hasattr(self, "add_save_credential_var")
            else False
        )

        if mode in ("drive", "both") and not drive_letter:
            messagebox.showerror(self.get_text("add_error"), self.get_text("error_no_drive_add"))
            return
        if save_credential and (not username or not password):
            messagebox.showerror(
                self.get_text("add_error"),
                self.get_text("repair_credentials_required"),
            )
            return
        normalized_username = username
        if mode in ("drive", "both") and username:
            identity_ok, normalized_username, identity_error = normalize_account_identity(
                unc, username, account_scope
            )
            if not identity_ok:
                messagebox.showerror(self.get_text("add_error"), identity_error)
                return

        mode_desc_key = {
            "drive": "add_mode_drive_desc",
            "location": "add_mode_location_desc",
            "both": "add_mode_both_desc",
        }[mode]
        mode_desc = self.get_text(mode_desc_key)

        extra_parts = []
        if mode in ("drive", "both"):
            extra_parts.append(f"{self.get_text('add_drive_letter')} {drive_letter}")
            if normalized_username:
                extra_parts.append(f"{self.get_text('add_username')} {normalized_username}")
        if mode in ("location", "both"):
            name_preview = location_name or suggest_location_name(unc)
            extra_parts.append(f"{self.get_text('add_location_name')} {name_preview}")
        extra = "\n".join(extra_parts)

        confirm_msg = self.get_text("confirm_add").format(
            unc=unc,
            mode=mode_desc,
            extra=extra,
        )
        if not messagebox.askyesno(self.get_text("confirm_add_title"), confirm_msg, icon="question"):
            return

        self.set_status(self.get_text("adding"), color="yellow")
        self.update()

        success, message = add_network_drive_or_location(
            unc_path=unc,
            mode=mode,
            drive_letter=drive_letter,
            location_name=location_name,
            username=username or None,
            password=password or None,
            persistent=persistent,
            save_credential=save_credential,
            account_scope=account_scope,
        )

        if success:
            self.set_status(message, color="green")
            self.refresh_data()
            self.update_drives_list()
            self.update_locations_list()
            self.update_add_drive_letters()
            self.update_remove_lists()
            # 清空敏感字段
            messagebox.showinfo(self.get_text("add_success"), message)
        else:
            first_line = message.splitlines()[0] if message else self.get_text("add_error")
            self.set_status(f"❌ {first_line}", color="red")
            self.show_detail_error(self.get_text("add_error"), message)



    # ==================== 重连修复 选项卡 ====================

    def create_repair_tab(self):
        tab = self.tab_repair
        body = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(10, 10))

        ctk.CTkLabel(
            body,
            text=self.get_text("repair_title"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=16),
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        drive_row = ctk.CTkFrame(body, fg_color="transparent")
        drive_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            drive_row,
            text=self.get_text("repair_drive"),
            width=90,
            anchor="w",
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        ).pack(side="left")
        drive_values = [drive for drive, _ in self.mapped_drives] or [""]
        self.repair_drive_var = ctk.StringVar(value=drive_values[0])
        self.repair_drive_combo = ctk.CTkComboBox(
            drive_row,
            values=drive_values,
            variable=self.repair_drive_var,
            width=110,
            height=32,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        )
        self.repair_drive_combo.pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            drive_row,
            text=self.get_text("repair_diagnose"),
            width=100,
            height=32,
            command=self.on_diagnose_reconnect,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        ).pack(side="left")

        self.repair_report_box = ctk.CTkTextbox(
            body,
            height=220,
            wrap="word",
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        )
        self.repair_report_box.pack(fill="both", expand=True, pady=(0, 10))
        self._set_repair_report(
            self.get_text("repair_ready") if self.mapped_drives else self.get_text("repair_no_drive")
        )

        credential_frame = ctk.CTkFrame(body)
        credential_frame.pack(fill="x", pady=(0, 10))
        credential_inner = ctk.CTkFrame(credential_frame, fg_color="transparent")
        credential_inner.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(
            credential_inner,
            text=self.get_text("account_scope"),
            width=90,
            anchor="w",
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.repair_account_scope_var = ctk.StringVar(value=self.get_text("account_scope_target"))
        self.repair_account_scope_combo = ctk.CTkComboBox(
            credential_inner,
            values=self._account_scope_labels(),
            variable=self.repair_account_scope_var,
            state="readonly",
            height=32,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        )
        self.repair_account_scope_combo.grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(
            credential_inner,
            text=self.get_text("repair_username"),
            width=90,
            anchor="w",
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        ).grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.repair_username_entry = ctk.CTkEntry(
            credential_inner,
            height=32,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        )
        self.repair_username_entry.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(
            credential_inner,
            text=self.get_text("repair_password"),
            width=90,
            anchor="w",
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        ).grid(row=2, column=0, sticky="w")
        self.repair_password_entry = ctk.CTkEntry(
            credential_inner,
            height=32,
            show="*",
            placeholder_text=self.get_text("repair_password_optional"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        )
        self.repair_password_entry.grid(row=2, column=1, sticky="ew")
        credential_inner.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            body,
            text=self.get_text("repair_button"),
            width=160,
            height=36,
            command=self.on_repair_reconnect,
            fg_color="#2e7d32",
            hover_color="#1b5e20",
            font=ctk.CTkFont(family=SYSTEM_FONT, size=14),
        ).pack(anchor="w")
        ctk.CTkLabel(
            body,
            text=self.get_text("repair_tip"),
            wraplength=760,
            justify="left",
            text_color="gray",
            font=ctk.CTkFont(family=SYSTEM_FONT, size=12),
        ).pack(fill="x", pady=(10, 0))
        self._last_reconnect_diagnosis = None

    def _set_repair_report(self, message):
        if not hasattr(self, "repair_report_box"):
            return
        self.repair_report_box.configure(state="normal")
        self.repair_report_box.delete("1.0", "end")
        self.repair_report_box.insert("1.0", str(message or ""))
        self.repair_report_box.configure(state="disabled")

    def update_repair_drives(self):
        if not hasattr(self, "repair_drive_combo"):
            return
        values = [drive for drive, _ in self.mapped_drives] or [""]
        self.repair_drive_combo.configure(values=values)
        if self.repair_drive_var.get() not in values:
            self.repair_drive_var.set(values[0])

    def on_diagnose_reconnect(self):
        drive = self.repair_drive_var.get().strip()
        if not drive:
            self._set_repair_report(self.get_text("repair_no_drive"))
            return
        self.set_status(self.get_text("repair_diagnose"), color="yellow")
        self.update()
        success, result = diagnose_drive_reconnect(drive)
        if success:
            self._last_reconnect_diagnosis = result
            self._set_repair_report(result.format_report())
            suggested = result.suggested_username or (
                result.saved_credential_users[0] if len(result.saved_credential_users) == 1 else result.persistent_username
            )
            if suggested:
                self.repair_username_entry.delete(0, "end")
                self.repair_username_entry.insert(0, suggested)
            self.set_status(self.get_text("refreshed"), color="green")
        else:
            self._last_reconnect_diagnosis = None
            self._set_repair_report(result)
            self.set_status(result, color="red")

    def on_repair_reconnect(self):
        drive = self.repair_drive_var.get().strip()
        username = self.repair_username_entry.get().strip()
        password = self.repair_password_entry.get()
        if not drive:
            messagebox.showerror(self.get_text("repair_error"), self.get_text("repair_no_drive"))
            return
        if not username:
            messagebox.showerror(
                self.get_text("repair_error"),
                self.get_text("repair_credentials_required"),
            )
            return

        diag_ok, diagnosis = diagnose_drive_reconnect(drive)
        if not diag_ok:
            self.show_detail_error(self.get_text("repair_error"), diagnosis)
            return
        report = diagnosis.format_report()
        account_scope = self._account_scope_value(self.repair_account_scope_var.get())
        identity_ok, normalized_username, identity_error = normalize_account_identity(
            diagnosis.server, username, account_scope
        )
        if not identity_ok:
            self.show_detail_error(self.get_text("repair_error"), identity_error)
            return
        report += "\n\n" + self.get_text("account_preview").format(username=normalized_username)
        if password:
            test_ok, test_report = test_share_credentials(
                diagnosis.unc_path,
                normalized_username,
                password,
            )
            existing_session_deferred = (
                "已有 SMB 会话" in test_report
                or "existing SMB session" in test_report
            )
            if not test_ok and not existing_session_deferred:
                self._set_repair_report(report + "\n\n" + test_report)
                self.show_detail_error(self.get_text("repair_error"), test_report)
                return
            if existing_session_deferred:
                report += "\n\n" + self.get_text("repair_test_deferred")
            else:
                report += "\n\n" + test_report
        else:
            report += "\n\n" + self.get_text("repair_reuse_password")

        if not messagebox.askyesno(
            self.get_text("repair_confirm_title"),
            self.get_text("repair_confirm").format(report=report),
            icon="warning",
        ):
            return

        self.set_status(self.get_text("repair_button"), color="yellow")
        self.update()
        success, message = repair_drive_reconnect(
            drive,
            username,
            password,
            save_credential=True,
            account_scope=account_scope,
            reuse_saved_password=True,
        )
        self.repair_password_entry.delete(0, "end")
        self._set_repair_report(message)
        self.refresh_data()
        self.update_repair_drives()
        self.update_drives_list()
        self.update_remove_lists()
        if success:
            self.set_status(self.get_text("repair_success"), color="green")
            messagebox.showinfo(self.get_text("repair_success"), message)
        else:
            self.set_status(self.get_text("repair_error"), color="red")
            self.show_detail_error(self.get_text("repair_error"), message)


    # ==================== 删除网络驱动器/位置 选项卡 ====================

    def create_remove_tab(self):
        """创建删除网络驱动器或位置的选项卡"""
        tab = self.tab_remove

        header = ctk.CTkFrame(tab, fg_color="transparent")
        header.pack(fill="x", pady=(10, 10))

        ctk.CTkLabel(
            header,
            text=self.get_text("remove_title"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=16),
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text=self.get_text("refresh"),
            width=90,
            height=28,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=12),
            command=self.on_refresh,
        ).pack(side="right")

        ctk.CTkButton(
            header,
            text=self.get_text("open_credential_manager"),
            width=140,
            height=28,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=12),
            fg_color="#455a64",
            hover_color="#37474f",
            command=self.on_open_credential_manager,
        ).pack(side="right", padx=(0, 8))

        options = ctk.CTkFrame(tab, fg_color="transparent")
        options.pack(fill="x", pady=(0, 8))

        if not hasattr(self, "remove_delete_credentials_var"):
            self.remove_delete_credentials_var = ctk.BooleanVar(value=False)
        self.remove_delete_credentials_check = ctk.CTkCheckBox(
            options,
            text=self.get_text("remove_also_credentials"),
            variable=self.remove_delete_credentials_var,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
        )
        self.remove_delete_credentials_check.pack(side="left")

        body = ctk.CTkScrollableFrame(tab)
        body.pack(fill="both", expand=True, pady=(0, 10))
        self.remove_list_frame = body

        self.update_remove_lists()

        tip = ctk.CTkFrame(tab, fg_color="#5c1a1a")
        tip.pack(fill="x", pady=(0, 0))
        ctk.CTkLabel(
            tip,
            text=self.get_text("tip_remove"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            text_color="#e0a0a0",
            wraplength=700,
            justify="left",
            anchor="w",
        ).pack(padx=15, pady=10, fill="x")

    def update_remove_lists(self):
        """刷新删除页的驱动器与网络位置列表"""
        if not hasattr(self, "remove_list_frame"):
            return

        for widget in self.remove_list_frame.winfo_children():
            widget.destroy()

        # Drives section
        ctk.CTkLabel(
            self.remove_list_frame,
            text=self.get_text("remove_drives_section"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=15),
            anchor="w",
        ).pack(fill="x", pady=(4, 6))

        if not self.mapped_drives:
            ctk.CTkLabel(
                self.remove_list_frame,
                text=self.get_text("remove_no_drives"),
                text_color="gray",
                font=ctk.CTkFont(family=SYSTEM_FONT, size=14),
                anchor="w",
            ).pack(fill="x", padx=8, pady=(0, 12))
        else:
            for drive, unc in self.mapped_drives:
                row = ctk.CTkFrame(self.remove_list_frame, height=50)
                row.pack(fill="x", pady=3)
                row.pack_propagate(False)

                ctk.CTkLabel(
                    row,
                    text=f"💿 {drive}",
                    font=ctk.CTkFont(family=SYSTEM_FONT, size=15),
                    width=80,
                ).pack(side="left", padx=(10, 0))

                ctk.CTkLabel(
                    row,
                    text="→",
                    font=ctk.CTkFont(size=15),
                    text_color="#4dabf7",
                ).pack(side="left", padx=10)

                ctk.CTkLabel(
                    row,
                    text=unc,
                    font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
                    text_color="#d0d0d0",
                ).pack(side="left", fill="x", expand=True)

                ctk.CTkButton(
                    row,
                    text=self.get_text("remove_drive"),
                    width=120,
                    height=32,
                    font=ctk.CTkFont(family=SYSTEM_FONT, size=12),
                    fg_color="#c62828",
                    hover_color="#8e0000",
                    command=lambda d=drive, u=unc: self.on_remove_drive(d, u),
                ).pack(side="right", padx=10)

        # Active SMB sessions section (includes IPC$/drive-less sessions).
        ctk.CTkLabel(
            self.remove_list_frame,
            text=self.get_text("remove_sessions_section"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=15),
            anchor="w",
        ).pack(fill="x", pady=(14, 6))

        sessions_by_server = {}
        for item in getattr(self, "smb_sessions", []):
            server = str(item.get("ServerName") or "").strip()
            if server:
                sessions_by_server.setdefault(server, []).append(item)

        if not sessions_by_server:
            empty_text = getattr(self, "smb_sessions_error", None) or self.get_text("remove_no_sessions")
            ctk.CTkLabel(
                self.remove_list_frame,
                text=empty_text,
                text_color="gray",
                font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
                anchor="w",
            ).pack(fill="x", padx=8, pady=(0, 8))
        else:
            for server, items in sorted(sessions_by_server.items()):
                identities = sorted({str(i.get("UserName") or i.get("Credential") or "未知身份") for i in items})
                shares = sorted({str(i.get("ShareName") or "(server)") for i in items})
                sources = sorted({source for i in items for source in i.get("Sources", [])})
                identity = ", ".join(identities)
                row = ctk.CTkFrame(self.remove_list_frame, height=78)
                row.pack(fill="x", pady=3)
                row.pack_propagate(False)
                ctk.CTkLabel(
                    row,
                    text=f"{server}\n{identity} | {', '.join(shares)}\n来源: {', '.join(sources) or 'Windows'}",
                    font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
                    anchor="w",
                    justify="left",
                ).pack(side="left", fill="x", expand=True, padx=10)
                ctk.CTkButton(
                    row,
                    text=self.get_text("remove_session"),
                    width=135,
                    height=32,
                    fg_color="#c62828",
                    hover_color="#8e0000",
                    command=lambda s=server, i=identity: self.on_remove_smb_session(s, i),
                ).pack(side="right", padx=10)

        # Locations section
        ctk.CTkLabel(
            self.remove_list_frame,
            text=self.get_text("remove_locations_section"),
            font=ctk.CTkFont(family=SYSTEM_FONT, size=15),
            anchor="w",
        ).pack(fill="x", pady=(14, 6))

        if not self.network_locations:
            ctk.CTkLabel(
                self.remove_list_frame,
                text=self.get_text("remove_no_locations"),
                text_color="gray",
                font=ctk.CTkFont(family=SYSTEM_FONT, size=14),
                anchor="w",
            ).pack(fill="x", padx=8, pady=(0, 8))
        else:
            for name, unc in self.network_locations:
                row = ctk.CTkFrame(self.remove_list_frame, height=55)
                row.pack(fill="x", pady=3)
                row.pack_propagate(False)

                info_frame = ctk.CTkFrame(row, fg_color="transparent")
                info_frame.pack(side="left", fill="both", expand=True, padx=(10, 0))

                ctk.CTkLabel(
                    info_frame,
                    text=f"📁 {name}",
                    font=ctk.CTkFont(family=SYSTEM_FONT, size=15),
                    anchor="w",
                ).pack(fill="x", pady=(5, 0))

                ctk.CTkLabel(
                    info_frame,
                    text=unc,
                    font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
                    text_color="#d0d0d0",
                    anchor="w",
                ).pack(fill="x")

                ctk.CTkButton(
                    row,
                    text=self.get_text("remove_location"),
                    width=120,
                    height=32,
                    font=ctk.CTkFont(family=SYSTEM_FONT, size=12),
                    fg_color="#c62828",
                    hover_color="#8e0000",
                    command=lambda n=name, u=unc: self.on_remove_location(n, u),
                ).pack(side="right", padx=10)

    def _remove_cred_note(self):
        """根据是否勾选删除凭据，返回确认框附加说明"""
        delete_creds = bool(
            hasattr(self, "remove_delete_credentials_var")
            and self.remove_delete_credentials_var.get()
        )
        return self.get_text("cred_note_yes") if delete_creds else self.get_text("cred_note_no")

    def on_remove_drive(self, drive, unc):
        """删除映射网络驱动器"""
        delete_creds = bool(
            hasattr(self, "remove_delete_credentials_var")
            and self.remove_delete_credentials_var.get()
        )
        msg = self.get_text("confirm_remove_drive").format(
            drive=drive,
            unc=unc,
            cred_note=self._remove_cred_note(),
        )
        if not messagebox.askyesno(self.get_text("confirm_remove_title"), msg, icon="warning"):
            return

        self.set_status(self.get_text("removing"), color="yellow")
        self.update()

        success, message = remove_network_drive(
            drive,
            force=False,
            delete_credentials=delete_creds,
        )
        if success:
            self.set_status(message, color="green")
            self.refresh_data()
            self.update_drives_list()
            self.update_locations_list()
            self.update_add_drive_letters()
            self.update_remove_lists()
            messagebox.showinfo(self.get_text("remove_success"), message)
            return

        self.set_status(f"❌ {message}", color="red")
        if "正在使用" in message or "in use" in message.lower() or "打开" in message:
            force_msg = self.get_text("force_disconnect").format(msg=message)
            if messagebox.askyesno(self.get_text("files_in_use"), force_msg, icon="warning"):
                success, message = remove_network_drive(
                    drive,
                    force=True,
                    delete_credentials=delete_creds,
                )
                if success:
                    self.set_status(message, color="green")
                    self.refresh_data()
                    self.update_drives_list()
                    self.update_locations_list()
                    self.update_add_drive_letters()
                    self.update_remove_lists()
                    messagebox.showinfo(self.get_text("remove_success"), message)
                else:
                    self.set_status(f"❌ {message}", color="red")
                    messagebox.showerror(self.get_text("remove_error"), message)
            return

        messagebox.showerror(self.get_text("remove_error"), message)

    def on_remove_location(self, location_name, unc):
        """删除网络位置"""
        delete_creds = bool(
            hasattr(self, "remove_delete_credentials_var")
            and self.remove_delete_credentials_var.get()
        )
        msg = self.get_text("confirm_remove_location").format(
            name=location_name,
            unc=unc,
            cred_note=self._remove_cred_note(),
        )
        if not messagebox.askyesno(self.get_text("confirm_remove_title"), msg, icon="warning"):
            return

        self.set_status(self.get_text("removing"), color="yellow")
        self.update()

        success, message = remove_network_location_item(
            location_name,
            delete_credentials=delete_creds,
        )
        if success:
            self.set_status(message, color="green")
            self.refresh_data()
            self.update_drives_list()
            self.update_locations_list()
            self.update_add_drive_letters()
            self.update_remove_lists()
            messagebox.showinfo(self.get_text("remove_success"), message)
        else:
            self.set_status(f"❌ {message}", color="red")
            messagebox.showerror(self.get_text("remove_error"), message)

    def on_remove_smb_session(self, server, identity):
        msg = self.get_text("confirm_remove_session").format(server=server, identity=identity)
        if not messagebox.askyesno(self.get_text("confirm_remove_title"), msg, icon="warning"):
            return
        success, message, _removed = disconnect_server_sessions(server, force=True)
        self.refresh_data()
        self.update_remove_lists()
        remaining = [
            item for item in getattr(self, "smb_sessions", [])
            if str(item.get("ServerName") or "").casefold() == str(server).casefold()
        ]
        if remaining:
            success = False
            remaining_shares = ", ".join(sorted({str(i.get("ShareName") or "(server)") for i in remaining}))
            message += "\n仍检测到连接: " + remaining_shares + "。如果它属于映射盘，请先删除对应映射盘。"
        self.set_status(message, color="green" if success else "red")
        if success:
            messagebox.showinfo(self.get_text("remove_success"), message)
        else:
            messagebox.showerror(self.get_text("remove_error"), message)


    # ==================== 通用方法 ====================

    def on_open_credential_manager(self):
        """打开当前 Windows 用户的凭据管理器。"""
        success, message = open_windows_credential_manager()
        if success:
            self.set_status(self.get_text("credential_manager_opened"), color="green")
            return

        self.set_status(message, color="red")
        messagebox.showerror(self.get_text("credential_manager_error"), message)
    
    def on_refresh(self):
        """刷新所有数据"""
        self.refresh_data()
        self.update_drives_list()
        self.update_locations_list()
        self.update_add_drive_letters()
        self.update_repair_drives()
        self.update_remove_lists()
        self.set_status(self.get_text("refreshed"), color="green")
    

    def show_detail_error(self, title, message):
        """显示可滚动的详细错误对话框（适合多行诊断信息）。"""
        msg = str(message or "")
        # 短消息继续用系统弹窗
        if msg.count("\n") < 4 and len(msg) < 220:
            messagebox.showerror(title, msg)
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("640x460")
        dialog.minsize(480, 320)
        dialog.transient(self)
        dialog.grab_set()

        # 居中
        try:
            dialog.update_idletasks()
            x = self.winfo_rootx() + max(20, (self.winfo_width() - 640) // 2)
            y = self.winfo_rooty() + max(20, (self.winfo_height() - 460) // 2)
            dialog.geometry(f"+{x}+{y}")
        except Exception:
            pass

        header = ctk.CTkLabel(
            dialog,
            text=title,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=16),
            anchor="w",
        )
        header.pack(fill="x", padx=16, pady=(16, 8))

        box = ctk.CTkTextbox(
            dialog,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            wrap="word",
        )
        box.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        box.insert("1.0", msg)
        box.configure(state="disabled")

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 16))

        def _copy():
            try:
                self.clipboard_clear()
                self.clipboard_append(msg)
                self.update()
            except Exception:
                pass

        ctk.CTkButton(
            btn_row,
            text="复制详情",
            width=100,
            height=32,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            fg_color="#455a64",
            hover_color="#37474f",
            command=_copy,
        ).pack(side="left")

        ctk.CTkButton(
            btn_row,
            text="关闭",
            width=100,
            height=32,
            font=ctk.CTkFont(family=SYSTEM_FONT, size=13),
            command=dialog.destroy,
        ).pack(side="right")

        dialog.wait_window()

    def set_status(self, message, color="gray"):
        """设置状态信息"""
        colors = {
            "gray": "gray",
            "green": "#51cf66",
            "red": "#ff6b6b",
            "yellow": "#ffd43b"
        }
        self.status_label.configure(text=message, text_color=colors.get(color, color))


def main():
    """程序入口"""
    app = DriveNetworkConverter()
    app.mainloop()


if __name__ == "__main__":
    main()
