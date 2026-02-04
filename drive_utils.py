"""
驱动器工具模块 - 处理Windows映射驱动器与网络位置的转换
"""

import os
import string
import ctypes
from ctypes import wintypes
import shutil


# Windows API 常量
CONNECT_UPDATE_PROFILE = 0x1
RESOURCETYPE_DISK = 0x1


def get_network_shortcuts_path():
    """获取网络位置快捷方式目录"""
    return os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Network Shortcuts')


def get_mapped_drives():
    """
    获取所有映射的网络驱动器
    
    Returns:
        list: 包含 (驱动器盘符, UNC路径) 元组的列表
    """
    mapped_drives = []
    
    # 获取所有逻辑驱动器
    drives_bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    
    for i, letter in enumerate(string.ascii_uppercase):
        if drives_bitmask & (1 << i):
            drive = f"{letter}:"
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{drive}\\")
            
            # 类型4 = DRIVE_REMOTE (网络驱动器)
            if drive_type == 4:
                unc_path = drive_to_unc(drive)
                if unc_path:
                    mapped_drives.append((drive, unc_path))
    
    return mapped_drives


def get_network_locations():
    """
    获取所有网络位置
    
    Returns:
        list: 包含 (名称, UNC路径) 元组的列表
    """
    locations = []
    shortcuts_path = get_network_shortcuts_path()
    
    if not os.path.exists(shortcuts_path):
        return locations
    
    for name in os.listdir(shortcuts_path):
        folder_path = os.path.join(shortcuts_path, name)
        if os.path.isdir(folder_path):
            target_lnk = os.path.join(folder_path, 'target.lnk')
            if os.path.exists(target_lnk):
                # 读取快捷方式目标
                try:
                    import win32com.client
                    shell = win32com.client.Dispatch("WScript.Shell")
                    shortcut = shell.CreateShortcut(target_lnk)
                    target_path = shortcut.TargetPath
                    if target_path:
                        locations.append((name, target_path))
                except Exception:
                    # 如果无法读取，跳过
                    pass
    
    return locations


def drive_to_unc(drive_letter):
    """
    将驱动器盘符转换为UNC路径
    
    Args:
        drive_letter: 驱动器盘符，如 "Z:" 或 "Z"
    
    Returns:
        str: UNC路径，如 "\\\\server\\share"，失败返回 None
    """
    # 标准化驱动器盘符
    drive = drive_letter.upper().rstrip(":\\")
    drive_path = f"{drive}:"
    
    # 使用 WNetGetConnectionW 获取远程名称
    buffer_size = 1024
    buffer = ctypes.create_unicode_buffer(buffer_size)
    size = wintypes.DWORD(buffer_size)
    
    result = ctypes.windll.mpr.WNetGetConnectionW(
        drive_path,
        buffer,
        ctypes.byref(size)
    )
    
    if result == 0:  # NO_ERROR
        return buffer.value
    
    return None


def create_network_location(name, unc_path):
    """
    创建网络位置快捷方式
    
    Args:
        name: 网络位置名称
        unc_path: UNC路径，如 "\\\\server\\share"
    
    Returns:
        tuple: (成功与否, 消息)
    """
    try:
        shortcuts_path = get_network_shortcuts_path()
        
        # 确保目录存在
        if not os.path.exists(shortcuts_path):
            os.makedirs(shortcuts_path)
        
        # 创建网络位置文件夹
        location_folder = os.path.join(shortcuts_path, name)
        if os.path.exists(location_folder):
            return False, f"网络位置 '{name}' 已存在"
        
        os.makedirs(location_folder)
        
        # 创建 desktop.ini
        desktop_ini_path = os.path.join(location_folder, 'desktop.ini')
        with open(desktop_ini_path, 'w', encoding='utf-8') as f:
            f.write('[.ShellClassInfo]\n')
            f.write('CLSID2={0AFACED1-E828-11D1-9187-B532F1E9575D}\n')
            f.write('Flags=2\n')
        
        # 设置desktop.ini为隐藏和系统属性
        ctypes.windll.kernel32.SetFileAttributesW(
            desktop_ini_path,
            0x02 | 0x04  # HIDDEN | SYSTEM
        )
        
        # 创建 target.lnk
        target_lnk_path = os.path.join(location_folder, 'target.lnk')
        
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(target_lnk_path)
        shortcut.TargetPath = unc_path
        shortcut.Save()
        
        # 设置文件夹为只读属性（让Windows识别为网络位置）
        ctypes.windll.kernel32.SetFileAttributesW(
            location_folder,
            0x01  # READONLY
        )
        
        return True, f"已创建网络位置: {name}"
        
    except Exception as e:
        return False, f"创建网络位置失败: {str(e)}"


def disconnect_drive(drive_letter, force=False):
    """
    断开映射的网络驱动器
    
    Args:
        drive_letter: 驱动器盘符，如 "Z:" 或 "Z"
        force: 是否强制断开（即使有文件正在使用）
    
    Returns:
        tuple: (成功与否, 消息)
    """
    try:
        # 标准化驱动器盘符
        drive = drive_letter.upper().rstrip(":\\")
        drive_path = f"{drive}:"
        
        # 调用 WNetCancelConnection2W
        result = ctypes.windll.mpr.WNetCancelConnection2W(
            drive_path,
            CONNECT_UPDATE_PROFILE,  # 更新用户配置
            force  # 是否强制
        )
        
        if result == 0:  # NO_ERROR
            return True, f"已断开驱动器 {drive_path}"
        elif result == 2401:  # ERROR_OPEN_FILES
            return False, f"驱动器 {drive_path} 有文件正在使用，请关闭相关文件后重试"
        elif result == 2250:  # ERROR_NOT_CONNECTED
            return False, f"驱动器 {drive_path} 未连接"
        else:
            return False, f"断开驱动器失败，错误代码: {result}"
            
    except Exception as e:
        return False, f"断开驱动器失败: {str(e)}"


def delete_network_location(name):
    """
    删除网络位置
    
    Args:
        name: 网络位置名称
    
    Returns:
        tuple: (成功与否, 消息)
    """
    try:
        shortcuts_path = get_network_shortcuts_path()
        location_folder = os.path.join(shortcuts_path, name)
        
        if not os.path.exists(location_folder):
            return False, f"网络位置 '{name}' 不存在"
        
        # 移除只读属性以便删除
        ctypes.windll.kernel32.SetFileAttributesW(location_folder, 0)
        
        # 删除文件夹
        shutil.rmtree(location_folder)
        
        return True, f"已删除网络位置: {name}"
        
    except Exception as e:
        return False, f"删除网络位置失败: {str(e)}"


def convert_drive_to_network_location(drive_letter, location_name=None, force=False):
    """
    将映射驱动器转换为网络位置
    
    Args:
        drive_letter: 驱动器盘符
        location_name: 网络位置名称（可选，默认使用UNC路径的共享名）
        force: 是否强制断开驱动器
    
    Returns:
        tuple: (成功与否, 消息)
    """
    # 获取UNC路径
    unc_path = drive_to_unc(drive_letter)
    if not unc_path:
        return False, f"无法获取驱动器 {drive_letter} 的UNC路径"
    
    # 生成网络位置名称
    if not location_name:
        # 从UNC路径提取共享名作为名称
        parts = unc_path.replace("/", "\\").lstrip("\\").split("\\")
        if len(parts) >= 2:
            location_name = f"{parts[0]}_{parts[1]}"
        else:
            location_name = unc_path.replace("\\", "_").strip("_")
    
    # 创建网络位置
    success, msg = create_network_location(location_name, unc_path)
    if not success:
        return False, msg
    
    # 断开驱动器
    success, disconnect_msg = disconnect_drive(drive_letter, force)
    if not success:
        # 如果断开失败，删除刚创建的网络位置
        delete_network_location(location_name)
        return False, disconnect_msg
    
    return True, f"成功！\n• 已创建网络位置: {location_name}\n• UNC路径: {unc_path}\n• 已断开驱动器: {drive_letter}"


def get_available_drive_letters():
    """
    获取所有可用的（未使用的）驱动器盘符
    
    Returns:
        list: 可用的驱动器盘符列表，如 ['D:', 'E:', 'F:']
    """
    available = []
    
    # 获取所有逻辑驱动器
    drives_bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    
    for i, letter in enumerate(string.ascii_uppercase):
        # 跳过A和B（软驱）
        if letter in ('A', 'B'):
            continue
        
        if not (drives_bitmask & (1 << i)):
            available.append(f"{letter}:")
    
    return available


def map_network_drive(drive_letter, unc_path, persistent=True):
    """
    映射网络驱动器
    
    Args:
        drive_letter: 驱动器盘符，如 "Z:" 或 "Z"
        unc_path: UNC路径，如 "\\\\server\\share"
        persistent: 是否持久化（重启后保留）
    
    Returns:
        tuple: (成功与否, 消息)
    """
    try:
        # 标准化驱动器盘符
        drive = drive_letter.upper().rstrip(":\\")
        drive_path = f"{drive}:"
        
        # 定义 NETRESOURCEW 结构体
        class NETRESOURCEW(ctypes.Structure):
            _fields_ = [
                ('dwScope', wintypes.DWORD),
                ('dwType', wintypes.DWORD),
                ('dwDisplayType', wintypes.DWORD),
                ('dwUsage', wintypes.DWORD),
                ('lpLocalName', wintypes.LPWSTR),
                ('lpRemoteName', wintypes.LPWSTR),
                ('lpComment', wintypes.LPWSTR),
                ('lpProvider', wintypes.LPWSTR),
            ]
        
        # 创建网络资源结构
        net_resource = NETRESOURCEW()
        net_resource.dwType = RESOURCETYPE_DISK
        net_resource.lpLocalName = drive_path
        net_resource.lpRemoteName = unc_path
        net_resource.lpProvider = None
        
        # 设置标志
        flags = CONNECT_UPDATE_PROFILE if persistent else 0
        
        # 调用 WNetAddConnection2W
        result = ctypes.windll.mpr.WNetAddConnection2W(
            ctypes.byref(net_resource),
            None,  # 密码
            None,  # 用户名
            flags
        )
        
        if result == 0:  # NO_ERROR
            return True, f"已将 {unc_path} 映射到 {drive_path}"
        elif result == 85:  # ERROR_ALREADY_ASSIGNED
            return False, f"驱动器 {drive_path} 已被占用"
        elif result == 53:  # ERROR_BAD_NETPATH
            return False, f"找不到网络路径: {unc_path}"
        elif result == 67:  # ERROR_BAD_NET_NAME
            return False, f"无效的网络名称: {unc_path}"
        elif result == 1219:  # ERROR_SESSION_CREDENTIAL_CONFLICT
            return False, f"凭据冲突，可能已有其他连接使用不同凭据连接到该服务器"
        else:
            return False, f"映射驱动器失败，错误代码: {result}"
            
    except Exception as e:
        return False, f"映射驱动器失败: {str(e)}"


def convert_network_location_to_drive(location_name, drive_letter):
    """
    将网络位置转换为映射驱动器
    
    Args:
        location_name: 网络位置名称
        drive_letter: 目标驱动器盘符
    
    Returns:
        tuple: (成功与否, 消息)
    """
    # 获取网络位置的UNC路径
    locations = get_network_locations()
    unc_path = None
    
    for name, path in locations:
        if name == location_name:
            unc_path = path
            break
    
    if not unc_path:
        return False, f"找不到网络位置: {location_name}"
    
    # 检查驱动器盘符是否可用
    available = get_available_drive_letters()
    drive = drive_letter.upper().rstrip(":\\") + ":"
    
    if drive not in available:
        return False, f"驱动器 {drive} 不可用（已被占用）"
    
    # 映射驱动器
    success, msg = map_network_drive(drive, unc_path)
    if not success:
        return False, msg
    
    # 删除网络位置
    success, delete_msg = delete_network_location(location_name)
    if not success:
        # 如果删除失败，也算成功（驱动器已映射）
        return True, f"成功！\n• 已映射驱动器: {drive} → {unc_path}\n• ⚠️ 网络位置删除失败: {delete_msg}"
    
    return True, f"成功！\n• 已映射驱动器: {drive}\n• UNC路径: {unc_path}\n• 已删除网络位置: {location_name}"


if __name__ == "__main__":
    # 测试代码
    print("=== 映射的网络驱动器 ===")
    drives = get_mapped_drives()
    if drives:
        for drive, unc in drives:
            print(f"  {drive} -> {unc}")
    else:
        print("  未检测到映射的网络驱动器")
    
    print("\n=== 网络位置 ===")
    locations = get_network_locations()
    if locations:
        for name, path in locations:
            print(f"  {name} -> {path}")
    else:
        print("  未检测到网络位置")
    
    print("\n=== 可用的驱动器盘符 ===")
    available = get_available_drive_letters()
    print(f"  {', '.join(available[:10])}...")

