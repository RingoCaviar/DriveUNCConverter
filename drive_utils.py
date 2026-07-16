"""
驱动器工具模块 - 处理Windows映射驱动器与网络位置的转换
"""

import os
import string
import ctypes
from ctypes import wintypes
import shutil
import subprocess
import re


# Windows API 常量
CONNECT_UPDATE_PROFILE = 0x1
RESOURCETYPE_DISK = 0x1


def get_network_shortcuts_path():
    """获取网络位置快捷方式目录"""
    return os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Network Shortcuts')


def normalize_drive_letter(drive_letter):
    """
    标准化驱动器盘符为 "X:" 形式。

    Args:
        drive_letter: 如 "Z", "Z:", "Z:\\", "z:/"

    Returns:
        str | None: 标准化后的盘符（如 "Z:"），无效时返回 None
    """
    if drive_letter is None:
        return None

    text = str(drive_letter).strip().upper().replace("/", "\\")
    if not text:
        return None

    # 只保留盘符字母，避免出现 "Z::" 这类错误路径
    letter = text.rstrip(":\\")
    if len(letter) != 1 or letter not in string.ascii_uppercase:
        return None

    return f"{letter}:"


def get_mapped_drives():
    """
    获取所有映射的网络驱动器

    Returns:
        list: 包含 (驱动器盘符, UNC路径) 元组的列表
    """
    mapped_drives = []

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
                try:
                    import win32com.client
                    shell = win32com.client.Dispatch("WScript.Shell")
                    shortcut = shell.CreateShortcut(target_lnk)
                    target_path = shortcut.TargetPath
                    if target_path:
                        locations.append((name, target_path))
                except Exception:
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
    drive = normalize_drive_letter(drive_letter)
    if not drive:
        return None

    buffer_size = 512
    buffer = ctypes.create_unicode_buffer(buffer_size)
    size = wintypes.DWORD(buffer_size)

    result = ctypes.windll.mpr.WNetGetConnectionW(
        drive,
        buffer,
        ctypes.byref(size)
    )

    if result == 0:
        return buffer.value
    return None


def create_network_location(name, unc_path):
    """
    创建网络位置快捷方式

    Args:
        name: 网络位置名称
        unc_path: UNC 路径，如 "\\\\server\\share"

    Returns:
        tuple: (成功与否, 消息)
    """
    try:
        shortcuts_path = get_network_shortcuts_path()
        os.makedirs(shortcuts_path, exist_ok=True)

        location_folder = os.path.join(shortcuts_path, name)
        if os.path.exists(location_folder):
            return False, f"网络位置 '{name}' 已存在"

        os.makedirs(location_folder)

        desktop_ini_path = os.path.join(location_folder, 'desktop.ini')
        with open(desktop_ini_path, 'w', encoding='utf-8') as f:
            f.write('[.ShellClassInfo]\n')
            f.write('CLSID2={0AFACED1-E828-11D1-9187-B532F1E9575D}\n')
            f.write('Flags=2\n')

        # 设置文件夹属性：只读 + 系统
        ctypes.windll.kernel32.SetFileAttributesW(location_folder, 0x06)

        target_lnk_path = os.path.join(location_folder, 'target.lnk')
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(target_lnk_path)
        shortcut.TargetPath = unc_path
        shortcut.Save()

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
        drive = normalize_drive_letter(drive_letter)
        if not drive:
            return False, "无效的驱动器盘符"

        drive_path = drive
        result = ctypes.windll.mpr.WNetCancelConnection2W(
            drive_path,
            0,
            force
        )

        if result == 0:
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

        for root, dirs, files in os.walk(location_folder):
            for d in dirs:
                try:
                    ctypes.windll.kernel32.SetFileAttributesW(os.path.join(root, d), 0x80)
                except Exception:
                    pass
            for f in files:
                try:
                    ctypes.windll.kernel32.SetFileAttributesW(os.path.join(root, f), 0x80)
                except Exception:
                    pass
        try:
            ctypes.windll.kernel32.SetFileAttributesW(location_folder, 0x80)
        except Exception:
            pass

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
    unc_path = drive_to_unc(drive_letter)
    if not unc_path:
        return False, f"无法获取驱动器 {drive_letter} 的 UNC 路径"

    if not location_name:
        parts = [p for p in unc_path.replace("/", "\\").strip("\\").split("\\") if p]
        location_name = parts[-1] if parts else "NetworkLocation"

    success, msg = create_network_location(location_name, unc_path)
    if not success:
        return False, msg

    ok, disconnect_msg = disconnect_drive(drive_letter, force=force)
    if not ok:
        return False, f"已创建网络位置，但断开驱动器失败: {disconnect_msg}"

    return True, (
        f"成功！\n"
        f"- 已创建网络位置: {location_name}\n"
        f"- UNC路径: {unc_path}\n"
        f"- 已断开驱动器: {drive_letter}"
    )


def get_available_drive_letters():
    """
    获取所有可用的（未使用的）驱动器盘符

    Returns:
        list: 可用的驱动器盘符列表，如 ['D:', 'E:', 'F:']
    """
    available = []
    drives_bitmask = ctypes.windll.kernel32.GetLogicalDrives()

    for i, letter in enumerate(string.ascii_uppercase):
        if letter == 'A' or letter == 'B':
            continue
        if not (drives_bitmask & (1 << i)):
            available.append(f"{letter}:")

    return available


def normalize_unc_path(path):
    """
    标准化用户输入为 UNC 路径。

    Args:
        path: 原始路径，如 \\\\server\\share 或 //server/share

    Returns:
        str | None: 标准化后的 UNC 路径，无效时返回 None
    """
    if path is None:
        return None

    raw = str(path).strip()
    if not raw:
        return None

    lower = raw.lower()
    if lower.startswith("file:"):
        raw = raw[5:]
        while raw.startswith("/"):
            raw = raw[1:]

    raw = raw.replace("/", "\\").strip()

    if not raw.startswith("\\\\"):
        # 允许用户输入 server\\share
        if "\\" in raw:
            raw = "\\\\" + raw.lstrip("\\")
        else:
            return None

    unc = raw.rstrip("\\")
    parts = [p for p in unc[2:].split("\\") if p]
    if len(parts) < 2:
        return None

    return "\\\\" + "\\".join(parts)


def suggest_location_name(unc_path):
    """
    根据 UNC 路径建议网络位置名称。

    Args:
        unc_path: UNC 路径

    Returns:
        str: 建议名称
    """
    unc = normalize_unc_path(unc_path) or str(unc_path or "").replace("/", "\\")
    parts = [p for p in unc.replace("/", "\\").strip("\\").split("\\") if p]
    if not parts:
        return "NetworkLocation"
    return parts[-1] if len(parts) >= 1 else "NetworkLocation"


def map_network_drive(drive_letter, unc_path, persistent=True):
    """
    映射网络驱动器。

    Args:
        drive_letter: 驱动器盘符，如 "Z:" 或 "Z"
        unc_path: UNC 路径，如 "\\\\server\\share"
        persistent: 是否在重启后保持连接

    Returns:
        tuple: (成功与否, 消息)
    """
    return map_network_drive_with_credentials(
        drive_letter,
        unc_path,
        username=None,
        password=None,
        persistent=persistent,
    )


def map_network_drive_with_credentials(
    drive_letter,
    unc_path,
    username=None,
    password=None,
    persistent=True,
):
    """
    使用可选凭据映射网络驱动器。

    Args:
        drive_letter: 驱动器盘符，如 "Z:" 或 "Z"
        unc_path: UNC 路径，如 "\\\\server\\share"
        username: 可选用户名
        password: 可选密码
        persistent: 是否在重启后保持连接

    Returns:
        tuple: (成功与否, 消息)
    """
    try:
        unc_path = normalize_unc_path(unc_path)
        if not unc_path:
            return False, '无效的网络路径，请使用 \\\\server\\share 格式'

        drive = normalize_drive_letter(drive_letter)
        if not drive:
            return False, "无效的驱动器盘符"
        drive_path = drive

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

        net_resource = NETRESOURCEW()
        net_resource.dwType = RESOURCETYPE_DISK
        net_resource.lpLocalName = drive_path
        net_resource.lpRemoteName = unc_path
        net_resource.lpProvider = None

        flags = CONNECT_UPDATE_PROFILE if persistent else 0

        user = username.strip() if username else None
        pwd = password if password not in (None, "") else None
        if user == "":
            user = None

        result = ctypes.windll.mpr.WNetAddConnection2W(
            ctypes.byref(net_resource),
            pwd,
            user,
            flags
        )

        if result == 0:
            return True, f"已将 {unc_path} 映射到 {drive_path}"
        elif result == 85:  # ERROR_ALREADY_ASSIGNED
            return False, f"驱动器 {drive_path} 已被占用"
        else:
            # 统一给出可诊断的详细失败信息（Win11 常见：能 ping 但不能匿名访问）
            return False, build_share_access_error_message(
                unc_path,
                error_code=result,
                username=username,
                password=password,
                extra=f"映射目标: {unc_path} -> {drive_path}",
            )

    except Exception as e:
        return False, f"映射网络驱动器失败: {str(e)}"


def add_network_drive(
    unc_path,
    drive_letter,
    username=None,
    password=None,
    persistent=True,
):
    """
    添加映射网络驱动器。

    Returns:
        tuple: (成功与否, 消息)
    """
    unc_path = normalize_unc_path(unc_path)
    if not unc_path:
        return False, '无效的网络路径，请使用 \\\\server\\share 格式'

    if not drive_letter:
        return False, "请选择驱动器盘符"

    drive = normalize_drive_letter(drive_letter)
    if not drive:
        return False, "无效的驱动器盘符"
    available = get_available_drive_letters()
    if drive not in available:
        return False, f"驱动器 {drive} 不可用（已被占用）"

    return map_network_drive_with_credentials(
        drive,
        unc_path,
        username=username,
        password=password,
        persistent=persistent,
    )


def add_network_location(unc_path, location_name=None):
    """
    添加网络位置。

    Returns:
        tuple: (成功与否, 消息, 名称)
    """
    unc_path = normalize_unc_path(unc_path)
    if not unc_path:
        return False, '无效的网络路径，请使用 \\\\server\\share 格式', None

    name = (location_name or "").strip() or suggest_location_name(unc_path)
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    name = name.strip(" .")
    if not name:
        name = "NetworkLocation"

    success, msg = create_network_location(name, unc_path)
    return success, msg, (name if success else None)


def add_network_drive_or_location(
    unc_path,
    mode="drive",
    drive_letter=None,
    location_name=None,
    username=None,
    password=None,
    persistent=True,
):
    """
    添加网络驱动器或/和网络位置。

    Args:
        unc_path: UNC 路径
        mode: drive / location / both
        drive_letter: mode 为 drive/both 时需要
        location_name: 可选网络位置名称
        username: 映射驱动器时可选用户名
        password: 映射驱动器时可选密码
        persistent: 是否保持连接

    Returns:
        tuple: (成功与否, 消息)
    """
    mode = (mode or "drive").strip().lower()
    if mode not in {"drive", "location", "both"}:
        return False, f"不支持的模式: {mode}"

    unc_path = normalize_unc_path(unc_path)
    if not unc_path:
        return False, '无效的网络路径，请使用 \\\\server\\share 格式'

    results = []

    if mode in {"drive", "both"}:
        ok, msg = add_network_drive(
            unc_path,
            drive_letter,
            username=username,
            password=password,
            persistent=persistent,
        )
        if not ok:
            return False, msg
        results.append(msg)

    if mode in {"location", "both"}:
        ok, msg, _name = add_network_location(unc_path, location_name=location_name)
        if not ok:
            if mode == "both" and results:
                return False, (
                    "部分成功\n"
                    + "\n".join(f"- {item}" for item in results)
                    + f"\n- 网络位置创建失败: {msg}"
                )
            return False, msg
        results.append(msg)

    return True, "成功！\n" + "\n".join(f"- {item}" for item in results)


def extract_unc_server(unc_path):
    """
    从 UNC 路径提取服务器名/IP。

    Returns:
        str | None
    """
    unc = normalize_unc_path(unc_path)
    if not unc:
        raw = str(unc_path or "").strip().replace("/", "\\")
        if not raw:
            return None
        if not raw.startswith("\\\\"):
            raw = "\\\\" + raw.lstrip("\\")
        unc = raw.rstrip("\\")

    parts = [p for p in unc[2:].split("\\") if p]
    if not parts:
        return None
    return parts[0]


def _format_win32_error(error_code):
    """把 Windows 错误码格式化为可读说明。"""
    try:
        code = int(error_code)
    except Exception:
        return str(error_code)

    known = {
        5: "拒绝访问（通常需要账号密码，或当前账户无权枚举共享）",
        53: "找不到网络路径（主机可达时，常见于 SMB 未开放/被防火墙拦截/需要认证）",
        67: "找不到网络名（共享名不存在或路径错误）",
        86: "密码无效",
        87: "参数错误",
        1203: "找不到网络路径（无法解析目标）",
        1219: "凭据冲突：该服务器已使用其他用户身份连接",
        1326: "用户名或密码不正确",
        1327: "账户限制（可能禁止空密码或仅允许特定登录方式）",
        1331: "账户当前被禁用",
        1907: "用户必须在下次登录时更改密码",
        1909: "引用的账户当前被锁定，可能因登录失败次数过多",
        2202: "用户名格式不正确",
        1222: "网络未连接或不可用",
        1231: "网络位置无法访问",
        1240: "尝试登录的账户类型错误",
        1244: "未提供有效凭据，服务器拒绝了未认证访问",
        1245: "登录失败：未授予用户在此计算机上的请求登录类型",
        1265: "安全上下文不可用",
        1271: "由于关机/策略原因，网络连接被拒绝",
        1722: "RPC 服务器不可用（目标在线但相关服务未响应）",
        1753: "没有可用的终结点（目标服务未监听）",
        6118: "该工作组的服务器列表当前不可用",
        58: "指定的服务器无法运行请求的操作（常见于需要登录或共享策略限制）",
        64: "指定的网络名不再可用",
        59: "发生意外的网络错误",
    }
    if code in known:
        return f"{known[code]} (错误码 {code})"

    try:
        FORMAT_MESSAGE_ALLOCATE_BUFFER = 0x00000100
        FORMAT_MESSAGE_FROM_SYSTEM = 0x00001000
        FORMAT_MESSAGE_IGNORE_INSERTS = 0x00000200
        buf = wintypes.LPWSTR()
        n = ctypes.windll.kernel32.FormatMessageW(
            FORMAT_MESSAGE_ALLOCATE_BUFFER
            | FORMAT_MESSAGE_FROM_SYSTEM
            | FORMAT_MESSAGE_IGNORE_INSERTS,
            None,
            code,
            0,
            ctypes.byref(buf),
            0,
            None,
        )
        if n and buf:
            try:
                msg = buf.value.strip()
            finally:
                ctypes.windll.kernel32.LocalFree(buf)
            if msg:
                return f"{msg} (错误码 {code})"
    except Exception:
        pass
    return f"Windows 错误码 {code}"


def _ping_host(host, timeout_ms=1200):
    """检测主机是否 ICMP 可达。返回 (ok, detail)。"""
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            ["ping", "-n", "1", "-w", str(int(timeout_ms)), str(host)],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
            timeout=max(3, int(timeout_ms / 1000) + 2),
            creationflags=creationflags,
        )
        out = (completed.stdout or "") + (completed.stderr or "")
        ok = completed.returncode == 0 and (
            "TTL=" in out or "ttl=" in out or "时间=" in out or "time=" in out or "time<" in out
        )
        if ok:
            return True, "Ping 成功（主机在线）"
        if "无法访问目标主机" in out or "Destination host unreachable" in out:
            return False, "Ping 失败：无法访问目标主机（路由/防火墙/关机）"
        if "请求超时" in out or "Request timed out" in out:
            return False, "Ping 失败：请求超时（可能禁 ping，不代表 SMB 一定不通）"
        return False, "Ping 失败（目标可能禁 ping）"
    except Exception as e:
        return False, f"Ping 检测异常: {e}"


def _tcp_port_open(host, port, timeout=1.5):
    """检测 TCP 端口是否开放。"""
    import socket

    sock = None
    try:
        sock = socket.create_connection((str(host), int(port)), timeout=timeout)
        return True
    except Exception:
        return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def diagnose_server_access(server_or_path, username=None, password=None):
    """
    诊断访问服务器共享失败的常见原因。
    """
    server = normalize_server_name(server_or_path)
    info = {
        "server": server,
        "ping_ok": None,
        "ping_detail": "",
        "smb445": None,
        "smb139": None,
        "has_credentials": bool((username or "").strip() or (password not in (None, ""))),
        "summary_lines": [],
    }
    if not server:
        info["summary_lines"] = ["未识别到服务器地址"]
        return info

    ping_ok, ping_detail = _ping_host(server)
    info["ping_ok"] = ping_ok
    info["ping_detail"] = ping_detail
    info["smb445"] = _tcp_port_open(server, 445)
    info["smb139"] = _tcp_port_open(server, 139)

    # 显示为标准 UNC 服务器形式：\\server
    lines_out = ["目标: \\\\" + server, ping_detail]
    if info["smb445"]:
        lines_out.append("SMB 端口 445: 开放")
    else:
        lines_out.append("SMB 端口 445: 未开放/被拦截")
    if info["smb139"]:
        lines_out.append("NetBIOS 端口 139: 开放")
    else:
        lines_out.append("NetBIOS 端口 139: 未开放/被拦截")
    if info["has_credentials"]:
        lines_out.append("已提供用户名/密码")
    else:
        lines_out.append("未提供用户名/密码")
    info["summary_lines"] = lines_out
    return info


def build_share_access_error_message(
    server_or_path,
    error_code=None,
    username=None,
    password=None,
    extra=None,
):
    """
    生成面向用户的详细失败说明（多行）。
    """
    server = normalize_server_name(server_or_path) or str(server_or_path or "").strip()
    diag = diagnose_server_access(server, username=username, password=password)
    has_creds = diag["has_credentials"]

    reason = None
    suggestions = []

    code = None
    try:
        code = int(error_code) if error_code is not None else None
    except Exception:
        code = None

    if code in (1326, 86, 2202, 1909, 1331, 1907, 1327):
        reason = _format_win32_error(code)
        suggestions = [
            "请检查用户名、密码是否正确",
            "用户名可尝试: 用户名 或 计算机名\\用户名 或 .\\用户名",
            "若账户被锁定/禁用，请先在对方电脑解锁",
        ]
    elif code == 67:
        reason = _format_win32_error(code)
        suggestions = [
            "请确认共享文件夹名称是否正确",
            "可先点“浏览共享”查看对方实际共享了哪些文件夹",
            "完整路径格式应为 \\\\服务器\\共享名",
        ]
    elif code in (5, 1244, 1245, 1240) or (
        code == 53 and not has_creds and (diag["smb445"] or diag["ping_ok"])
    ):
        reason = (
            "当前未通过身份验证，服务器拒绝了匿名/来宾访问"
            if not has_creds
            else _format_win32_error(code or 5)
        )
        if not has_creds:
            suggestions = [
                "请填写对方电脑的用户名和密码后再点“浏览共享”",
                "Windows 10/11 默认常禁用来宾（Guest）访问，仅凭 IP 往往无法列出共享",
                "也可先在资源管理器访问 \\\\IP 并登录一次，再回来浏览",
            ]
        else:
            suggestions = [
                "确认该账户对共享有读取权限",
                "确认对方开启了“文件和打印机共享”",
                "若仍失败，可尝试用户名格式: 计算机名\\用户名",
            ]
    elif code == 1219:
        reason = _format_win32_error(code)
        suggestions = [
            "请先断开该服务器上已有的网络连接/映射驱动器",
            "或勾选删除凭据后重连，再使用同一组账号密码",
            "也可在命令提示符执行: net use * /delete",
        ]
    elif not diag["smb445"] and not diag["smb139"]:
        reason = "主机可能在线，但 SMB 文件共享端口不可达"
        suggestions = [
            "检查对方是否开启“文件和打印机共享”",
            "检查双方防火墙是否放行 445 端口",
            "确认是否在同一网络/是否需要 VPN",
            "某些公共网络配置会阻止设备发现与文件共享",
        ]
        if diag["ping_ok"] is False:
            suggestions.insert(0, "注意：Ping 失败不一定代表主机离线（可能禁 ping）")
    elif code in (53, 58, 59, 64, 1203, 1231, 1222) and (diag["ping_ok"] or diag["smb445"]) and not has_creds:
        reason = "可以 Ping 通/端口可达，但未登录时无法访问共享（常见于 Win11）"
        suggestions = [
            "请输入用户名和密码后重试",
            "这通常不是 IP 错误，而是共享访问需要认证",
            "对方若关闭了来宾访问/密码保护共享，匿名访问会失败",
            "若共享名不确定，请先用“浏览共享”查看实际共享文件夹",
        ]
    elif code in (53, 1203, 1231, 1722, 1753):
        reason = _format_win32_error(code)
        suggestions = [
            "确认对方已开启 SMB/文件共享服务",
            "确认防火墙放行 445",
            "若仅主机名失败，可改用 IP 地址重试",
        ]
    elif code is not None:
        reason = _format_win32_error(code)
        suggestions = [
            "若目标需要登录，请填写正确的用户名和密码",
            "确认对方共享权限与网络配置",
        ]
    else:
        reason = "无法访问该服务器的共享列表"
        if not has_creds:
            suggestions = [
                "请先填写用户名和密码再试",
                "Win11 上“能 Ping 通但无法访问”多数是需要登录，不是 IP 不通",
            ]
        else:
            suggestions = [
                "请确认账号权限与对方共享设置",
                "可检查防火墙、SMB 服务是否开启",
            ]

    if extra:
        suggestions.append(str(extra))

    out = []
    out.append(("无法访问服务器: \\\\" + server) if server else "无法访问服务器")
    out.append("")
    out.append(f"原因: {reason}")
    out.append("")
    out.append("诊断信息:")
    for item in diag["summary_lines"]:
        out.append(f"  - {item}")
    if code is not None:
        out.append(f"  - 系统错误: {_format_win32_error(code)}")
    out.append("")
    out.append("建议:")
    for i, tip in enumerate(suggestions, 1):
        out.append(f"  {i}. {tip}")
    return "\n".join(out)


def normalize_server_name(server_or_path):
    """
    从 IP/主机名/UNC 输入中提取服务器名。

    支持:
        192.168.1.1
        \\\\192.168.1.1
        \\\\192.168.1.1\\share
        //server/share
        server
    """
    if server_or_path is None:
        return None

    raw = str(server_or_path).strip()
    if not raw:
        return None

    lower = raw.lower()
    if lower.startswith("file:"):
        raw = raw[5:]
        while raw.startswith("/"):
            raw = raw[1:]

    raw = raw.replace("/", "\\").strip()

    if raw.startswith("\\\\") or "\\" in raw:
        server = extract_unc_server(raw if raw.startswith("\\\\") else ("\\\\" + raw.lstrip("\\")))
        if server:
            return server

    server = raw.strip("\\").split("\\")[0].strip()
    if not server:
        return None
    if any(ch.isspace() for ch in server):
        return None
    return server


def _server_unc(server):
    """构造服务器 UNC：\\\\server（避免 f-string 反斜杠错误）。"""
    return "\\\\" + str(server).lstrip("\\")


def _connect_to_server_for_enum(server, username=None, password=None):
    """
    可选：先用凭据连接 \\\\server，便于枚举共享。

    Returns:
        (connected: bool, remote: str, error_code: int|None)
    """
    remote = _server_unc(server)
    user = username.strip() if username else None
    pwd = password if password not in (None, "") else None
    if user == "":
        user = None
    if not user and not pwd:
        return False, remote, None

    class NETRESOURCEW(ctypes.Structure):
        _fields_ = [
            ("dwScope", wintypes.DWORD),
            ("dwType", wintypes.DWORD),
            ("dwDisplayType", wintypes.DWORD),
            ("dwUsage", wintypes.DWORD),
            ("lpLocalName", wintypes.LPWSTR),
            ("lpRemoteName", wintypes.LPWSTR),
            ("lpComment", wintypes.LPWSTR),
            ("lpProvider", wintypes.LPWSTR),
        ]

    net_resource = NETRESOURCEW()
    net_resource.dwType = RESOURCETYPE_DISK
    net_resource.lpLocalName = None
    net_resource.lpRemoteName = remote
    net_resource.lpProvider = None

    result = ctypes.windll.mpr.WNetAddConnection2W(
        ctypes.byref(net_resource),
        pwd,
        user,
        0,
    )
    if result == 0:
        return True, remote, 0
    if result == 85:
        return True, remote, 85
    if result == 1219:
        return False, remote, 1219
    return False, remote, result


def _disconnect_server_connection(remote):
    try:
        ctypes.windll.mpr.WNetCancelConnection2W(remote, 0, True)
    except Exception:
        pass


def list_server_shares(
    server_or_path,
    username=None,
    password=None,
    include_hidden=False,
    include_special=False,
):
    """
    列出指定服务器上的共享文件夹。

    Returns:
        tuple: (成功与否, 消息, shares)
    """
    server = normalize_server_name(server_or_path)
    if not server:
        return False, "请输入服务器 IP 或主机名", []

    connected = False
    remote = _server_unc(server)
    connect_error = None
    enum_error = None

    try:
        connected, remote, connect_error = _connect_to_server_for_enum(
            server, username, password
        )

        # 用户提供了凭据但连接明确失败
        if (username or password) and connect_error not in (None, 0, 85) and not connected:
            msg = build_share_access_error_message(
                server,
                error_code=connect_error,
                username=username,
                password=password,
                extra="凭据连接阶段失败",
            )
            return False, msg, []

        class SHARE_INFO_1(ctypes.Structure):
            _fields_ = [
                ("shi1_netname", wintypes.LPWSTR),
                ("shi1_type", wintypes.DWORD),
                ("shi1_remark", wintypes.LPWSTR),
            ]

        buf = ctypes.c_void_p()
        entries_read = wintypes.DWORD(0)
        total_entries = wintypes.DWORD(0)
        resume_handle = wintypes.DWORD(0)
        MAX_PREFERRED_LENGTH = 0xFFFFFFFF

        STYPE_DISKTREE = 0x00000000
        STYPE_IPC = 0x00000003
        STYPE_SPECIAL = 0x80000000

        result = ctypes.windll.netapi32.NetShareEnum(
            ctypes.c_wchar_p(remote),
            1,
            ctypes.byref(buf),
            MAX_PREFERRED_LENGTH,
            ctypes.byref(entries_read),
            ctypes.byref(total_entries),
            ctypes.byref(resume_handle),
        )
        # 某些环境 \\\\server 失败但裸主机名可成功
        if result != 0:
            result_alt = ctypes.windll.netapi32.NetShareEnum(
                ctypes.c_wchar_p(server),
                1,
                ctypes.byref(buf),
                MAX_PREFERRED_LENGTH,
                ctypes.byref(entries_read),
                ctypes.byref(total_entries),
                ctypes.byref(resume_handle),
            )
            if result_alt == 0:
                result = result_alt
        enum_error = result

        if result != 0:
            shares, msg = _list_shares_via_net_view(server)
            if shares:
                return True, msg, shares
            detail = build_share_access_error_message(
                server,
                error_code=result,
                username=username,
                password=password,
                extra=(f"net view 后备也失败: {msg}" if msg else None),
            )
            return False, detail, []

        shares = []
        try:
            if entries_read.value > 0 and buf:
                arr_type = SHARE_INFO_1 * entries_read.value
                arr = ctypes.cast(buf, ctypes.POINTER(arr_type)).contents
                for i in range(entries_read.value):
                    name = arr[i].shi1_netname or ""
                    share_type = int(arr[i].shi1_type or 0)
                    remark = arr[i].shi1_remark or ""
                    if not name:
                        continue

                    is_hidden = name.endswith("$")
                    base_type = share_type & 0x0FFFFFFF
                    is_special = bool(share_type & STYPE_SPECIAL)
                    is_disk = base_type == STYPE_DISKTREE
                    is_ipc = base_type == STYPE_IPC

                    if is_ipc and not include_special:
                        continue
                    if is_special and not include_special and is_hidden and not include_hidden:
                        continue
                    if is_hidden and not include_hidden:
                        continue
                    if not is_disk and not include_special:
                        continue

                    unc = "\\\\" + server + "\\" + name
                    shares.append(
                        {
                            "name": name,
                            "unc": unc,
                            "type": share_type,
                            "remark": remark,
                            "is_hidden": is_hidden,
                            "is_disk": is_disk,
                        }
                    )
        finally:
            if buf:
                ctypes.windll.netapi32.NetApiBufferFree(buf)

        shares.sort(key=lambda s: (not s["is_disk"], s["name"].lower()))

        if not shares:
            return (
                True,
                f"服务器 {server} 上未发现可用共享文件夹（可能都是隐藏共享，可勾选“显示隐藏共享”）",
                [],
            )

        return True, f"找到 {len(shares)} 个共享", shares

    except Exception as e:
        shares, msg = _list_shares_via_net_view(server)
        if shares:
            return True, msg, shares
        detail = build_share_access_error_message(
            server,
            error_code=enum_error or connect_error,
            username=username,
            password=password,
            extra=f"异常: {e}",
        )
        return False, detail, []
    finally:
        if connected:
            _disconnect_server_connection(remote)


def _list_shares_via_net_view(server):
    """使用 net view \\\\server 作为后备方案。"""
    try:
        creationflags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW

        completed = None
        remote = _server_unc(server)
        for enc in ("gbk", "utf-8", "mbcs"):
            try:
                completed = subprocess.run(
                    ["net", "view", remote],
                    capture_output=True,
                    text=True,
                    encoding=enc,
                    errors="replace",
                    timeout=20,
                    creationflags=creationflags,
                )
                if completed.returncode == 0 and completed.stdout:
                    break
            except Exception:
                continue

        if not completed or completed.returncode != 0:
            err = ""
            if completed:
                err = (completed.stderr or completed.stdout or "").strip()
            return [], (err or f"net view 失败: {server}")

        shares = []
        lines = completed.stdout.splitlines()
        in_table = False
        for line in lines:
            if set(line.strip()) == {"-"} or line.strip().startswith("----"):
                in_table = True
                continue
            if not in_table:
                continue
            if "The command completed" in line or "命令成功完成" in line:
                break
            if not line.strip():
                continue

            m = re.match(r"^(.+?)\s{2,}(\S+)(?:\s{2,}(.*))?$", line.rstrip())
            if not m:
                parts = line.split()
                if len(parts) < 2:
                    continue
                name = parts[0]
                type_name = parts[1]
                remark = " ".join(parts[2:]) if len(parts) > 2 else ""
            else:
                name = m.group(1).strip()
                type_name = m.group(2).strip()
                remark = (m.group(3) or "").strip()

            type_l = type_name.lower()
            is_disk = type_l in {"disk", "磁盘"} or type_name in {"Disk", "磁盘"}
            if not is_disk:
                if type_l not in {"disk"}:
                    continue

            if name.endswith("$"):
                continue

            shares.append(
                {
                    "name": name,
                    "unc": "\\\\" + server + "\\" + name,
                    "type": 0,
                    "remark": remark,
                    "is_hidden": False,
                    "is_disk": True,
                }
            )

        shares.sort(key=lambda s: s["name"].lower())
        if not shares:
            return [], f"服务器 {server} 上未发现可用共享文件夹"
        return shares, f"找到 {len(shares)} 个共享"
    except Exception as e:
        return [], f"net view 失败: {e}"


def _run_cmdkey(args):
    """运行 cmdkey，隐藏控制台窗口。"""
    creationflags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW

    return subprocess.run(
        ["cmdkey"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )


def list_saved_credentials_for_server(server):
    """
    列出与指定服务器相关的已保存 Windows 凭据目标名。

    Returns:
        list[str]: 可传给 cmdkey /delete 的目标名列表
    """
    if not server:
        return []

    server_l = str(server).strip().lower()
    targets = []
    seen = set()

    try:
        result = _run_cmdkey(["/list"])
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        for line in output.splitlines():
            m = re.search(r"(?i)Target\s*:\s*(.+)$", line)
            if not m:
                m = re.search(r"目标\s*[:：]\s*(.+)$", line)
            if not m:
                continue
            target = m.group(1).strip()
            target_l = target.lower()
            bare = target_l
            for prefix in ("domain:target=", "legacygeneric:target=", "windowslive:target="):
                if bare.startswith(prefix):
                    bare = bare[len(prefix):]
            bare = bare.split("=", 1)[-1]
            bare = bare.replace("/", "\\")
            if server_l in bare or bare.rstrip("\\").endswith(server_l) or bare == server_l:
                if target not in seen:
                    seen.add(target)
                    targets.append(target)
    except Exception:
        pass

    try:
        import win32cred
        creds = win32cred.CredEnumerate(None, 0)
        for cred in creds:
            candidate = cred.get("TargetName") or ""
            if not candidate:
                continue
            target_l = candidate.lower()
            if server_l in target_l:
                if candidate not in seen:
                    seen.add(candidate)
                    targets.append(candidate)
    except Exception:
        pass

    return targets


def delete_credentials_for_unc(unc_path):
    """
    删除与 UNC 路径对应服务器相关的已保存凭据。

    Returns:
        tuple: (成功与否, 消息, 已删除目标列表)
    """
    server = normalize_server_name(unc_path) or extract_unc_server(unc_path)
    if not server:
        return False, "无法从路径解析服务器名称，未能删除凭据", []

    targets = list_saved_credentials_for_server(server)
    deleted = []
    failed = []

    for target in targets:
        try:
            result = _run_cmdkey([f"/delete:{target}"])
            out = ((result.stdout or "") + " " + (result.stderr or "")).lower()
            if result.returncode == 0 or "success" in out or "成功" in out:
                deleted.append(target)
            else:
                raise RuntimeError(out.strip() or f"cmdkey exit {result.returncode}")
        except Exception:
            try:
                import win32cred
                removed = False
                for cred_type in (
                    getattr(win32cred, "CRED_TYPE_DOMAIN_PASSWORD", 2),
                    getattr(win32cred, "CRED_TYPE_GENERIC", 1),
                    getattr(win32cred, "CRED_TYPE_DOMAIN_VISIBLE_PASSWORD", 4),
                ):
                    candidates = [
                        target,
                        f"Domain:target={server}",
                        f"LegacyGeneric:target=Microsoft_Network:{server}",
                        f"LegacyGeneric:target={server}",
                        server,
                    ]
                    for cand in candidates:
                        try:
                            win32cred.CredDelete(cand, cred_type)
                            deleted.append(cand)
                            removed = True
                            break
                        except Exception:
                            continue
                    if removed:
                        break
                if not removed:
                    failed.append(target)
            except Exception:
                failed.append(target)

    deleted = list(dict.fromkeys(deleted))
    failed = [f for f in failed if f not in deleted]

    if deleted and not failed:
        return True, f"已删除相关凭据 ({len(deleted)}): {', '.join(deleted)}", deleted
    if deleted and failed:
        return True, (
            f"已删除部分凭据 ({len(deleted)}): {', '.join(deleted)}"
            f"；失败 ({len(failed)}): {', '.join(failed)}"
        ), deleted
    if not deleted and not targets:
        return True, f"未找到与服务器 {server} 相关的已保存凭据", []
    return False, f"删除凭据失败: {', '.join(failed) if failed else server}", []


def remove_network_drive(drive_letter, force=False, delete_credentials=False):
    """
    删除（断开）映射的网络驱动器。

    Args:
        drive_letter: 驱动器盘符，如 "Z:" 或 "Z"
        force: 是否强制断开
        delete_credentials: 是否同时删除相关 Windows 凭据

    Returns:
        tuple: (成功与否, 消息)
    """
    if not drive_letter:
        return False, "请选择一个驱动器盘符"

    drive = normalize_drive_letter(drive_letter)
    if not drive:
        return False, "无效的驱动器盘符"
    mapped = {d: unc for d, unc in get_mapped_drives()}
    if drive not in mapped:
        return False, f"驱动器 {drive} 不是已映射的网络驱动器"

    unc = mapped[drive]
    success, msg = disconnect_drive(drive, force=force)
    if not success:
        return success, msg

    message = f"已删除网络驱动器: {drive} → {unc}"
    if delete_credentials:
        cred_ok, cred_msg, _deleted = delete_credentials_for_unc(unc)
        if cred_ok:
            message += f"\n- {cred_msg}"
        else:
            message += f"\n- 凭据删除失败: {cred_msg}"
    return True, message


def remove_network_location_item(location_name, delete_credentials=False):
    """
    删除网络位置。

    Args:
        location_name: 网络位置名称
        delete_credentials: 是否同时删除相关 Windows 凭据

    Returns:
        tuple: (成功与否, 消息)
    """
    if not location_name:
        return False, "请选择一个网络位置"

    locations = {name: unc for name, unc in get_network_locations()}
    if location_name not in locations:
        return False, f"找不到网络位置: {location_name}"

    unc = locations[location_name]
    success, msg = delete_network_location(location_name)
    if not success:
        return success, msg

    message = f"已删除网络位置: {location_name} ({unc})"
    if delete_credentials:
        cred_ok, cred_msg, _deleted = delete_credentials_for_unc(unc)
        if cred_ok:
            message += f"\n- {cred_msg}"
        else:
            message += f"\n- 凭据删除失败: {cred_msg}"
    return True, message


def convert_network_location_to_drive(location_name, drive_letter):
    """
    将网络位置转换为映射驱动器

    Args:
        location_name: 网络位置名称
        drive_letter: 目标驱动器盘符

    Returns:
        tuple: (成功与否, 消息)
    """
    locations = get_network_locations()
    unc_path = None

    for name, path in locations:
        if name == location_name:
            unc_path = path
            break

    if not unc_path:
        return False, f"找不到网络位置: {location_name}"

    available = get_available_drive_letters()
    drive = normalize_drive_letter(drive_letter)
    if not drive:
        return False, "无效的驱动器盘符"
    if drive not in available:
        return False, f"驱动器 {drive} 不可用（已被占用）"

    success, msg = map_network_drive(drive, unc_path)
    if not success:
        return False, msg

    delete_ok, delete_msg = delete_network_location(location_name)
    if not delete_ok:
        return True, (
            f"成功！\n"
            f"- 已映射驱动器: {drive} → {unc_path}\n"
            f"- 网络位置删除失败: {delete_msg}"
        )

    return True, (
        f"成功！\n"
        f"- 已映射驱动器: {drive}\n"
        f"- UNC路径: {unc_path}\n"
        f"- 已删除网络位置: {location_name}"
    )


if __name__ == "__main__":
    print("Mapped drives:")
    for drive, unc in get_mapped_drives():
        print(f"  {drive} -> {unc}")
    print("Network locations:")
    for name, path in get_network_locations():
        print(f"  {name} -> {path}")
    print("Available:", ", ".join(get_available_drive_letters()))
