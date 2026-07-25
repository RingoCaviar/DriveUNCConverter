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
import json
from dataclasses import dataclass, field


# Windows API 常量
CONNECT_UPDATE_PROFILE = 0x1
RESOURCETYPE_DISK = 0x1

# Windows Network Shortcut attributes. Explorer processes desktop.ini when
# the location folder is read-only; hiding that folder makes it disappear from
# "This PC".
FILE_ATTRIBUTE_READONLY = 0x01
FILE_ATTRIBUTE_HIDDEN = 0x02
FILE_ATTRIBUTE_SYSTEM = 0x04

# Shell change notification constants used to refresh Explorer.
SHCNE_MKDIR = 0x00000008
SHCNE_RMDIR = 0x00000010
SHCNE_UPDATEITEM = 0x00002000
SHCNF_PATHW = 0x0005

RESOURCE_CONNECTED = 0x00000001
RESOURCEUSAGE_ALL = 0x00000000
ERROR_NO_MORE_ITEMS = 259


@dataclass
class DriveReconnectDiagnosis:
    """Structured diagnosis for one persistent mapped-drive connection."""

    drive_letter: str
    unc_path: str
    server: str
    persistent: bool
    saved_credential_targets: list[str] = field(default_factory=list)
    saved_credential_users: list[str] = field(default_factory=list)
    credential_target_match: bool = False
    active_identities: list[str] = field(default_factory=list)
    conflicting_identities: list[str] = field(default_factory=list)
    other_server_drives: list[str] = field(default_factory=list)
    smb445_open: bool | None = None
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    @property
    def healthy(self):
        return not self.issues

    def format_report(self):
        status = "正常" if self.healthy else "需要修复"
        lines = [
            f"重连诊断: {self.drive_letter} → {self.unc_path}",
            f"状态: {status}",
            f"持久映射: {'是' if self.persistent else '否'}",
            f"SMB 445: {'开放' if self.smb445_open else '不可达'}",
            "匹配凭据: " + (
                ", ".join(self.saved_credential_targets)
                if self.credential_target_match
                else "未找到"
            ),
            "当前 SMB 身份: " + (
                ", ".join(self.active_identities) if self.active_identities else "未报告"
            ),
        ]
        if self.saved_credential_users:
            lines.append("保存的用户名: " + ", ".join(self.saved_credential_users))
        if self.other_server_drives:
            lines.append("同服务器其他映射: " + ", ".join(self.other_server_drives))
        if self.issues:
            lines.extend(["", "发现的问题:"])
            lines.extend(f"- {item}" for item in self.issues)
        if self.recommendations:
            lines.extend(["", "建议:"])
            lines.extend(f"- {item}" for item in self.recommendations)
        return "\n".join(lines)


class _CONNECTED_NETRESOURCEW(ctypes.Structure):
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


def get_network_shortcuts_path():
    """获取网络位置快捷方式目录"""
    return os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Network Shortcuts')


def open_windows_credential_manager():
    """打开 Windows 凭据管理器。返回 ``(success, message)``。"""
    if os.name != "nt":
        return False, "凭据管理器仅在 Windows 系统上可用"

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    commands = (
        ["control.exe", "/name", "Microsoft.CredentialManager"],
        ["rundll32.exe", "keymgr.dll,KRShowKeyMgr"],
    )
    errors = []

    for command in commands:
        try:
            subprocess.Popen(command, creationflags=creationflags)
            return True, "已打开 Windows 凭据管理器"
        except OSError as exc:
            errors.append(str(exc))

    detail = "; ".join(errors) if errors else "未知错误"
    return False, f"无法打开 Windows 凭据管理器: {detail}"


def _notify_explorer(event, path):
    """Best-effort notification that a Network Shortcut changed."""
    try:
        ctypes.windll.shell32.SHChangeNotify(
            event,
            SHCNF_PATHW,
            ctypes.c_wchar_p(path),
            None,
        )
    except Exception:
        # The filesystem operation already succeeded. A refresh failure should
        # not make the whole operation fail.
        pass


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
                    # Repair shortcuts made by older versions, which marked
                    # the entire location folder hidden + system.
                    folder_attrs = ctypes.windll.kernel32.GetFileAttributesW(folder_path)
                    needs_repair = (
                        bool(folder_attrs & FILE_ATTRIBUTE_HIDDEN)
                        or not bool(folder_attrs & FILE_ATTRIBUTE_READONLY)
                    )
                    desktop_ini_path = os.path.join(folder_path, 'desktop.ini')
                    if os.path.exists(desktop_ini_path):
                        ctypes.windll.kernel32.SetFileAttributesW(
                            desktop_ini_path,
                            FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM,
                        )
                    ctypes.windll.kernel32.SetFileAttributesW(
                        folder_path,
                        FILE_ATTRIBUTE_READONLY,
                    )
                    if needs_repair:
                        _notify_explorer(SHCNE_UPDATEITEM, folder_path)

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
        # Explorer's documented desktop.ini format is Unicode (UTF-16 LE with
        # a BOM), rather than UTF-8.
        with open(desktop_ini_path, 'w', encoding='utf-16') as f:
            f.write('[.ShellClassInfo]\n')
            f.write('CLSID2={0AFACED1-E828-11D1-9187-B532F1E9575D}\n')
            f.write('Flags=2\n')

        target_lnk_path = os.path.join(location_folder, 'target.lnk')
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(target_lnk_path)
        shortcut.TargetPath = unc_path
        shortcut.Save()

        # Explorer only treats desktop.ini as folder metadata when the folder
        # has the read-only attribute. desktop.ini itself is hidden + system;
        # the location folder must not be hidden.
        ctypes.windll.kernel32.SetFileAttributesW(
            desktop_ini_path,
            FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM,
        )
        ctypes.windll.kernel32.SetFileAttributesW(
            location_folder,
            FILE_ATTRIBUTE_READONLY,
        )
        _notify_explorer(SHCNE_MKDIR, location_folder)

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
            CONNECT_UPDATE_PROFILE,
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
        _notify_explorer(SHCNE_RMDIR, location_folder)
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
    save_credential=False,
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
        save_credential: 是否将凭据保存到当前用户的 Windows 凭据管理器

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
        if save_credential and (not (username or "").strip() or password in (None, "")):
            return False, "保存凭据需要同时填写用户名和密码"

        server = extract_unc_server(unc_path)
        old_credential = _read_windows_credential(server) if save_credential else None
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

        if save_credential:
            cred_ok, cred_msg = save_windows_credential(server, username, password)
            if not cred_ok:
                disconnect_drive(drive_letter, force=False)
                _restore_windows_credential(server, old_credential)
                return False, f"映射已撤销：{cred_msg}"
            results.append(cred_msg)

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


def _get_smb_connections_for_server(server):
    """使用 Windows SMB 客户端查询指定服务器的当前连接和实际身份。"""
    if not server:
        return [], "服务器为空"

    ps_script = r"""
$target = $env:DRIVEUNC_DIAG_SERVER
$items = @(Get-SmbConnection -ErrorAction SilentlyContinue |
    Where-Object { $_.ServerName -ieq $target } |
    ForEach-Object {
        [PSCustomObject]@{
            ServerName = [string]$_.ServerName
            ShareName  = [string]$_.ShareName
            UserName   = [string]$_.UserName
            Credential = [string]$_.Credential
            Dialect    = [string]$_.Dialect
            NumOpens   = [int]$_.NumOpens
        }
    })
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
ConvertTo-Json -InputObject $items -Compress
"""
    env = os.environ.copy()
    env["DRIVEUNC_DIAG_SERVER"] = str(server)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                ps_script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8-sig",
            errors="replace",
            timeout=12,
            creationflags=creationflags,
            env=env,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            return [], detail or f"PowerShell 退出码 {completed.returncode}"
        raw = (completed.stdout or "").strip()
        if not raw:
            return [], None
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = [parsed]
        return list(parsed or []), None
    except Exception as exc:
        return [], str(exc)


def get_active_smb_sessions():
    """Return client SMB connections visible to Get-SmbConnection."""
    ps_script = r"""
$items = @(Get-SmbConnection -ErrorAction SilentlyContinue | ForEach-Object {
    [PSCustomObject]@{
        ServerName = [string]$_.ServerName
        ShareName  = [string]$_.ShareName
        UserName   = [string]$_.UserName
        Credential = [string]$_.Credential
        Dialect    = [string]$_.Dialect
        NumOpens   = [int]$_.NumOpens
    }
})
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
ConvertTo-Json -InputObject $items -Compress
"""
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            encoding="utf-8-sig",
            errors="replace",
            timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            return [], (completed.stderr or completed.stdout or "").strip()
        raw = (completed.stdout or "").strip()
        if not raw:
            return [], None
        parsed = json.loads(raw)
        return ([parsed] if isinstance(parsed, dict) else list(parsed or [])), None
    except Exception as exc:
        return [], str(exc)


def get_clearable_smb_connections():
    """Merge SMB connections exposed by PowerShell, WNet, and ``net use``."""
    merged = {}
    errors = []

    def add(remote, server="", share="", identity="", source=""):
        remote = str(remote or "").strip().rstrip("\\")
        if not remote.startswith("\\\\"):
            return
        parts = [p for p in remote[2:].split("\\") if p]
        server = str(server or (parts[0] if parts else "")).strip()
        share = str(share or ("\\".join(parts[1:]) if len(parts) > 1 else "(server)"))
        key = remote.casefold()
        item = merged.setdefault(key, {
            "ServerName": server,
            "ShareName": share,
            "RemoteName": remote,
            "UserName": identity,
            "Credential": "",
            "Dialect": "",
            "NumOpens": 0,
            "Sources": [],
            "LocalName": "",
        })
        if identity and not item.get("UserName"):
            item["UserName"] = identity
        if source and source not in item["Sources"]:
            item["Sources"].append(source)

    smb_items, smb_error = get_active_smb_sessions()
    if smb_error:
        errors.append("Get-SmbConnection: " + smb_error)
    for item in smb_items:
        server = str(item.get("ServerName") or "")
        share = str(item.get("ShareName") or "")
        remote = _server_unc(server) + (("\\" + share) if share else "")
        add(remote, server, share, item.get("UserName") or item.get("Credential"), "Get-SmbConnection")
        current = merged.get(remote.rstrip("\\").casefold())
        if current:
            current.update({k: item.get(k, current.get(k)) for k in ("Credential", "Dialect", "NumOpens")})

    enum_handle = wintypes.HANDLE()
    try:
        result = ctypes.windll.mpr.WNetOpenEnumW(
            RESOURCE_CONNECTED, RESOURCETYPE_DISK, RESOURCEUSAGE_ALL, None, ctypes.byref(enum_handle)
        )
        if result == 0:
            try:
                while True:
                    size = wintypes.DWORD(64 * 1024)
                    buffer = ctypes.create_string_buffer(size.value)
                    count = wintypes.DWORD(0xFFFFFFFF)
                    result = ctypes.windll.mpr.WNetEnumResourceW(enum_handle, ctypes.byref(count), buffer, ctypes.byref(size))
                    if result == ERROR_NO_MORE_ITEMS:
                        break
                    if result != 0:
                        errors.append(f"WNet: Windows error {result}")
                        break
                    resources = ctypes.cast(buffer, ctypes.POINTER(_CONNECTED_NETRESOURCEW))
                    for index in range(count.value):
                        remote = resources[index].lpRemoteName or ""
                        add(remote, source="WNet")
                        key = remote.rstrip("\\").casefold()
                        if key in merged:
                            merged[key]["LocalName"] = resources[index].lpLocalName or ""
            finally:
                ctypes.windll.mpr.WNetCloseEnum(enum_handle)
        else:
            errors.append(f"WNet: Windows error {result}")
    except Exception as exc:
        errors.append("WNet: " + str(exc))

    try:
        completed = subprocess.run(
            ["net", "use"], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        # UNC text itself is language-independent. Two-or-more spaces delimit
        # the provider/status columns while allowing spaces inside share names.
        for line in output.splitlines():
            match = re.search(r"(\\\\[^\\\s]+\\.+?)(?=\s{2,}\S|$)", line.rstrip())
            if match:
                add(match.group(1).strip(), source="net use")
    except Exception as exc:
        errors.append("net use: " + str(exc))

    items = sorted(merged.values(), key=lambda i: (i["ServerName"].casefold(), i["ShareName"].casefold()))
    return items, ("; ".join(errors) if errors else None)


def diagnose_share_browse_identity(server_or_path):
    """
    诊断不输入账号密码时仍可浏览共享的原因。

    该函数只读取连接/凭据状态并执行一次无显式凭据的共享枚举，
    不会删除或断开任何连接。
    """
    server = normalize_server_name(server_or_path)
    if not server:
        return False, "请输入有效的服务器 IP 或主机名"

    before, before_error = _get_smb_connections_for_server(server)
    saved_credentials = list_saved_credentials_for_server(server)
    browse_ok, browse_message, shares = list_server_shares(
        server,
        username=None,
        password=None,
        include_hidden=False,
        include_special=False,
    )
    after, after_error = _get_smb_connections_for_server(server)

    lines = [f"SMB 浏览身份排查: \\{server}", ""]
    lines.append("1. 排查前的活动 SMB 连接")
    if before:
        for item in before:
            share = item.get("ShareName") or "(服务器会话)"
            identity = item.get("UserName") or item.get("Credential") or "(未报告)"
            dialect = item.get("Dialect") or "?"
            lines.append(f"  - \\{server}\\{share} | 身份: {identity} | SMB {dialect}")
    elif before_error:
        lines.append(f"  - 无法读取: {before_error}")
    else:
        lines.append("  - 未发现")

    lines.extend(["", "2. Windows 凭据管理器"])
    if saved_credentials:
        lines.extend(f"  - {target}" for target in saved_credentials)
    else:
        lines.append("  - 未发现该服务器的已保存凭据")

    lines.extend(["", "3. 不提供用户名/密码的共享枚举"])
    if browse_ok:
        names = ", ".join(item.get("name", "") for item in shares) or "(无可见共享)"
        lines.append(f"  - 枚举成功: {names}")
    else:
        first_line = (browse_message or "枚举失败").splitlines()[0]
        lines.append(f"  - 枚举失败: {first_line}")

    new_connections = []
    before_keys = {
        ((item.get("ServerName") or "").casefold(), (item.get("ShareName") or "").casefold())
        for item in before
    }
    for item in after:
        key = ((item.get("ServerName") or "").casefold(), (item.get("ShareName") or "").casefold())
        if key not in before_keys:
            new_connections.append(item)

    lines.extend(["", "4. 结论"])
    if before and browse_ok:
        identities = sorted({
            item.get("UserName") or item.get("Credential") or "未知身份"
            for item in before
        })
        lines.append("原因: Windows 复用了排查前已存在的 SMB 会话。")
        lines.append("当前身份: " + ", ".join(identities))
    elif new_connections and browse_ok:
        identities = sorted({
            item.get("UserName") or item.get("Credential") or "未知身份"
            for item in new_connections
        })
        lines.append("原因: 枚举共享时 Windows 自动建立了 SMB 会话。")
        lines.append("实际身份: " + ", ".join(identities))
        if saved_credentials:
            lines.append("可能来源: 已保存凭据，或当前 Windows 登录身份自动通过验证。")
        else:
            lines.append("可能来源: 当前 Windows 登录身份被服务器接受，或服务器将其转为 Guest。")
    elif browse_ok:
        lines.append("原因: 在未检测到可见 SMB 会话的情况下仍可枚举共享。")
        lines.append("服务器很可能允许 Guest/匿名用户查看共享名称。")
        lines.append("注意: 能看到共享名称不代表能访问共享内容。")
    else:
        lines.append("当前无法在不提供凭据的情况下枚举共享。")

    if after_error and not after:
        lines.append(f"补充: 枚举后 SMB 身份查询失败: {after_error}")
    lines.extend([
        "",
        "说明: 本排查不会断开会话或删除凭据。",
        "共享列表的可见性与具体文件夹的读写权限是两项独立检查。",
    ])
    return True, "\n".join(lines)


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


def test_share_credentials(unc_path, username, password):
    """Test credentials against one concrete share without saving them.

    The temporary connection is removed before returning.  A server root is
    deliberately rejected because successful share enumeration does not prove
    that the account can open a particular share.
    """
    unc = normalize_unc_path(unc_path)
    user = (username or "").strip()
    if not unc or len([part for part in unc.lstrip("\\").split("\\") if part]) < 2:
        return False, "请输入完整共享路径，例如：\\\\192.168.1.10\\B"
    if not user:
        return False, "请输入要测试的用户名"

    server = normalize_server_name(unc)
    before, before_error = _get_smb_connections_for_server(server)
    if before:
        current = sorted({
            str(item.get("UserName") or item.get("Credential") or "未知身份")
            for item in before
        })
        return False, "\n".join([
            f"凭证测试目标: {unc}",
            f"提交的用户名: {user}",
            "",
            "结果: 检测到这台服务器已有 SMB 会话，未执行测试。",
            "Windows 可能直接复用旧会话，从而产生“密码正确”的假结果。",
            "当前连接身份: " + ", ".join(current),
            "请先在删除页面清理该服务器的残留 SMB 会话，再重新测试。",
        ])

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

    resource = NETRESOURCEW()
    resource.dwType = RESOURCETYPE_DISK
    resource.lpRemoteName = unc
    result = ctypes.windll.mpr.WNetAddConnection2W(
        ctypes.byref(resource),
        password if password is not None else "",
        user,
        0,
    )

    created = result == 0
    try:
        after, after_error = _get_smb_connections_for_server(server)
        lines = [
            f"凭证测试目标: {unc}",
            f"提交的用户名: {user}",
            "凭证不会保存。",
            "",
        ]

        if result == 0:
            identities = sorted({
                str(item.get("UserName") or item.get("Credential") or "").strip()
                for item in after
                if item.get("UserName") or item.get("Credential")
            })
            guest = any(name.lower().endswith(("\\guest", "/guest")) or name.lower() == "guest" for name in identities)
            if guest:
                lines.extend([
                    "结果: 连接成功，但服务器实际使用 Guest（来宾）身份。",
                    "这不能证明输入的用户名和密码正确；服务器可能启用了来宾回退。",
                ])
                ok = False
            else:
                lines.extend([
                    "结果: 凭证验证成功，并且该账号可以连接此共享。",
                    "实际 SMB 身份: " + (", ".join(identities) if identities else "系统未返回身份；连接 API 已确认成功"),
                ])
                ok = True
        elif result == 1219:
            lines.extend([
                "结果: 无法独立测试（Windows 错误 1219）。",
                "当前 Windows 会话已经用另一套身份连接了这台服务器。请先在删除页面清理该服务器的残留 SMB 会话，再测试。",
            ])
            if before:
                current = sorted({str(item.get("UserName") or item.get("Credential") or "未知身份") for item in before})
                lines.append("当前连接身份: " + ", ".join(current))
            ok = False
        elif result in (86, 1326, 1909):
            lines.extend([
                f"结果: 用户名或密码不正确（Windows 错误 {result}）。",
                "也可能是账号被锁定、禁用，或不允许网络登录。",
            ])
            ok = False
        elif result == 5:
            lines.extend([
                "结果: 服务器拒绝访问（Windows 错误 5）。",
                "账号可能存在，但没有该共享的共享权限或 NTFS 权限；这不等同于密码一定错误。",
            ])
            ok = False
        elif result in (53, 67):
            lines.extend([
                f"结果: 找不到服务器或共享（Windows 错误 {result}）。",
                "请检查 IP、共享名和 SMB 服务。",
            ])
            ok = False
        else:
            lines.extend([
                f"结果: 测试失败（Windows 错误 {result}）。",
                build_share_access_error_message(unc, error_code=result, username=user, password=password),
            ])
            ok = False

        if before_error or after_error:
            lines.extend(["", "身份读取提示: " + (after_error or before_error)])
        return ok, "\n".join(lines)
    finally:
        if created:
            _disconnect_server_connection(unc)


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


def _read_windows_credential(server):
    """Read the exact server credential for rollback; never formats its secret."""
    if not server:
        return None
    try:
        import win32cred

        return win32cred.CredRead(
            str(server),
            getattr(win32cred, "CRED_TYPE_DOMAIN_PASSWORD", 2),
            0,
        )
    except Exception:
        return None


def _restore_windows_credential(server, credential):
    """Best-effort restore/delete used by transactional mapping operations."""
    try:
        import win32cred

        cred_type = getattr(win32cred, "CRED_TYPE_DOMAIN_PASSWORD", 2)
        if credential:
            restored = {
                key: credential[key]
                for key in (
                    "Type",
                    "TargetName",
                    "Comment",
                    "CredentialBlob",
                    "Persist",
                    "Attributes",
                    "TargetAlias",
                    "UserName",
                )
                if key in credential
            }
            win32cred.CredWrite(restored, 0)
        else:
            try:
                win32cred.CredDelete(str(server), cred_type, 0)
            except Exception:
                pass
        return True
    except Exception:
        return False


def save_windows_credential(server, username, password):
    """Save an SMB credential for the exact UNC server in the current profile."""
    target = str(server or "").strip().strip("\\/")
    user = str(username or "").strip()
    if not target:
        return False, "无法保存凭据：服务器名称为空"
    if not user or password in (None, ""):
        return False, "无法保存凭据：用户名和密码不能为空"

    try:
        import win32cred

        credential = {
            "Type": getattr(win32cred, "CRED_TYPE_DOMAIN_PASSWORD", 2),
            "TargetName": target,
            "UserName": user,
            "CredentialBlob": str(password),
            "Persist": getattr(win32cred, "CRED_PERSIST_LOCAL_MACHINE", 2),
            "Comment": "DriveUNCConverter persistent SMB mapping",
        }
        win32cred.CredWrite(credential, 0)
        saved = win32cred.CredRead(
            target,
            getattr(win32cred, "CRED_TYPE_DOMAIN_PASSWORD", 2),
            0,
        )
        if str(saved.get("TargetName") or "").casefold() != target.casefold():
            return False, "Windows 凭据管理器未返回刚写入的目标"
        if str(saved.get("UserName") or "").casefold() != user.casefold():
            return False, "Windows 凭据管理器中的用户名与写入值不一致"
        return True, f"已将 {target} 的凭据保存到 Windows 凭据管理器"
    except Exception as exc:
        return False, f"保存 Windows 凭据失败: {exc}"


def _credential_details_for_server(server):
    """Return target/user metadata only; credential blobs are never exposed."""
    details = []
    server_key = str(server or "").strip().casefold()
    if not server_key:
        return details
    try:
        import win32cred

        for cred in win32cred.CredEnumerate(None, 0):
            target = str(cred.get("TargetName") or "")
            bare = target.casefold()
            for prefix in ("domain:target=", "legacygeneric:target="):
                if bare.startswith(prefix):
                    bare = bare[len(prefix):]
            if bare.strip("\\/") == server_key:
                details.append({
                    "target": target,
                    "username": str(cred.get("UserName") or ""),
                    "exact": True,
                })
    except Exception:
        pass

    known_targets = list_saved_credentials_for_server(server)
    existing = {item["target"].casefold() for item in details}
    for target in known_targets:
        if target.casefold() not in existing:
            bare = target.casefold()
            for prefix in ("domain:target=", "legacygeneric:target="):
                if bare.startswith(prefix):
                    bare = bare[len(prefix):]
            details.append({
                "target": target,
                "username": "",
                "exact": bare.strip("\\/") == server_key,
            })
    return details


def _persistent_mapping_details(drive_letter):
    drive = normalize_drive_letter(drive_letter)
    if not drive:
        return False, None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Network\{drive[0]}") as key:
            remote, _ = winreg.QueryValueEx(key, "RemotePath")
            return True, normalize_unc_path(remote)
    except Exception:
        return False, None


def diagnose_drive_reconnect(drive_letter):
    """Diagnose persistence, credentials, connectivity and SMB identity."""
    drive = normalize_drive_letter(drive_letter)
    if not drive:
        return False, "无效的驱动器盘符"
    persistent, profile_unc = _persistent_mapping_details(drive)
    unc = drive_to_unc(drive)
    if not unc:
        for mapped_drive, mapped_unc in get_mapped_drives():
            if normalize_drive_letter(mapped_drive) == drive:
                unc = mapped_unc
                break
    if not unc:
        unc = profile_unc
    unc = normalize_unc_path(unc)
    if not unc:
        return False, f"无法读取驱动器 {drive} 的 UNC 映射"
    server = extract_unc_server(unc)
    if persistent and profile_unc and profile_unc.casefold() != unc.casefold():
        persistent = False

    credential_details = _credential_details_for_server(server)
    exact_details = [item for item in credential_details if item["exact"]]
    smb_connections, _ = _get_smb_connections_for_server(server)
    identities = sorted({
        str(item.get("UserName") or item.get("Credential") or "").strip()
        for item in smb_connections
        if item.get("UserName") or item.get("Credential")
    })
    saved_users = sorted({item["username"] for item in exact_details if item["username"]})
    conflicts = []
    if len({item.casefold() for item in identities}) > 1:
        conflicts = identities
    elif identities and saved_users and not any(
        active.casefold() == saved.casefold()
        for active in identities
        for saved in saved_users
    ):
        conflicts = identities

    other_drives = []
    for other_drive, other_unc in get_mapped_drives():
        normalized_other = normalize_drive_letter(other_drive)
        other_server = extract_unc_server(other_unc)
        if (
            normalized_other != drive
            and other_server
            and other_server.casefold() == server.casefold()
        ):
            other_drives.append(f"{normalized_other} → {other_unc}")

    diagnosis = DriveReconnectDiagnosis(
        drive_letter=drive,
        unc_path=unc,
        server=server,
        persistent=persistent,
        saved_credential_targets=[item["target"] for item in exact_details],
        saved_credential_users=saved_users,
        credential_target_match=bool(exact_details),
        active_identities=identities,
        conflicting_identities=conflicts,
        other_server_drives=other_drives,
        smb445_open=_tcp_port_open(server, 445),
    )
    if not diagnosis.persistent:
        diagnosis.issues.append("该盘符没有与当前 UNC 一致的持久映射配置")
    if not diagnosis.credential_target_match:
        diagnosis.issues.append(f"未找到目标精确为 {server} 的 Windows 凭据")
    if not diagnosis.smb445_open:
        diagnosis.issues.append("服务器 SMB 445 端口当前不可达")
    if diagnosis.conflicting_identities:
        diagnosis.issues.append("当前 SMB 身份与保存凭据不一致，可能触发错误 1219")
    if diagnosis.other_server_drives:
        diagnosis.recommendations.append("修复前确认同服务器的其他映射盘使用相同账号")
    if diagnosis.persistent and diagnosis.credential_target_match and not diagnosis.conflicting_identities:
        diagnosis.recommendations.append(
            "配置看起来正常；若仅开机暂时显示红叉，可能是网络初始化较慢，可启用“计算机启动和登录时始终等待网络”"
        )
    else:
        diagnosis.recommendations.append("输入正确账号密码后执行重连修复")
    return True, diagnosis


def _disconnect_drive_for_repair(drive_letter):
    """Disconnect a drive, including stale persistent mappings shown with a red X."""
    ok, message = disconnect_drive(drive_letter, force=False)
    if ok:
        return ok, message
    if "文件正在使用" in message or "错误代码: 2401" in message:
        forced_ok, forced_message = disconnect_drive(drive_letter, force=True)
        if forced_ok:
            return True, f"{forced_message}（检测到文件占用，已强制断开）"
        return False, f"{message}\n强制断开也失败: {forced_message}"
    if "错误代码: 2250" not in message and "未连接" not in message:
        return ok, message
    drive = normalize_drive_letter(drive_letter)
    try:
        completed = subprocess.run(
            ["net", "use", drive, "/delete", "/y"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode == 0:
            return True, f"已移除断开状态的持久映射 {drive}"
    except Exception:
        pass
    return False, message


def repair_drive_reconnect(drive_letter, username, password, save_credential=True):
    """Transactionally rebuild one drive mapping and its exact-server credential."""
    user = str(username or "").strip()
    if not user or password in (None, ""):
        return False, "修复重连需要同时填写用户名和密码"
    ok, diagnosis_or_message = diagnose_drive_reconnect(drive_letter)
    if not ok:
        return False, diagnosis_or_message
    diagnosis = diagnosis_or_message

    entered_identity_conflict = (
        diagnosis.active_identities
        and not any(identity.casefold() == user.casefold() for identity in diagnosis.active_identities)
    )
    if diagnosis.other_server_drives and (
        diagnosis.conflicting_identities or entered_identity_conflict
    ):
        return False, (
            "检测到同服务器其他映射盘和身份冲突。为避免中断其他盘符，未执行修复。\n"
            + "\n".join(f"- {item}" for item in diagnosis.other_server_drives)
        )

    old_credential = _read_windows_credential(diagnosis.server)
    steps = []
    disconnected, disconnect_msg = _disconnect_drive_for_repair(diagnosis.drive_letter)
    if not disconnected:
        return False, disconnect_msg
    steps.append(disconnect_msg)

    sessions_ok, sessions_msg, _ = disconnect_server_sessions(diagnosis.unc_path, force=True)
    steps.append(sessions_msg)
    if not sessions_ok:
        map_network_drive_with_credentials(
            diagnosis.drive_letter,
            diagnosis.unc_path,
            username=None,
            password=None,
            persistent=diagnosis.persistent,
        )
        return False, "\n".join(steps + ["修复已停止，并已尝试恢复原映射"])

    if save_credential:
        cred_ok, cred_msg = save_windows_credential(diagnosis.server, user, password)
        steps.append(cred_msg)
        if not cred_ok:
            _restore_windows_credential(diagnosis.server, old_credential)
            map_network_drive_with_credentials(
                diagnosis.drive_letter,
                diagnosis.unc_path,
                username=None,
                password=None,
                persistent=diagnosis.persistent,
            )
            return False, "\n".join(steps + ["凭据保存失败，已尝试恢复原配置"])

    mapped, map_msg = map_network_drive_with_credentials(
        diagnosis.drive_letter,
        diagnosis.unc_path,
        username=user,
        password=password,
        persistent=True,
    )
    steps.append(map_msg)
    if not mapped:
        if save_credential:
            _restore_windows_credential(diagnosis.server, old_credential)
        restored, restore_msg = map_network_drive_with_credentials(
            diagnosis.drive_letter,
            diagnosis.unc_path,
            username=None,
            password=None,
            persistent=diagnosis.persistent,
        )
        steps.append(
            ("已恢复原映射: " if restored else "原映射恢复失败: ") + restore_msg
        )
        return False, "\n".join(steps)

    verify_ok, verify_result = diagnose_drive_reconnect(diagnosis.drive_letter)
    if not verify_ok or not verify_result.persistent or (
        save_credential and not verify_result.credential_target_match
    ):
        disconnect_drive(diagnosis.drive_letter, force=False)
        if save_credential:
            _restore_windows_credential(diagnosis.server, old_credential)
        restored, restore_msg = map_network_drive_with_credentials(
            diagnosis.drive_letter,
            diagnosis.unc_path,
            username=None,
            password=None,
            persistent=diagnosis.persistent,
        )
        steps.append("持久配置验证未通过，已撤销本次修复")
        steps.append(
            ("已恢复原映射: " if restored else "原映射恢复失败: ") + restore_msg
        )
        return False, "\n".join(steps)
    steps.append("验证成功：持久映射和精确服务器凭据均已就绪")
    return True, "\n".join(steps)


def disconnect_server_sessions(unc_path, force=True):
    """断开指定服务器上没有绑定盘符的 SMB 连接。

    同一服务器上的其他映射驱动器会保留，避免清理凭据时误断用户的
    其他盘符。

    Returns:
        tuple: (成功与否, 消息, 已断开的远程路径列表)
    """
    server = normalize_server_name(unc_path) or extract_unc_server(unc_path)
    if not server:
        return False, "无法从路径解析服务器名称，未能断开 SMB 会话", []

    server_root = _server_unc(server).rstrip("\\")
    server_prefix = server_root.casefold() + "\\"
    exact_unc = normalize_unc_path(unc_path)
    enum_handle = wintypes.HANDLE()
    open_result = ctypes.windll.mpr.WNetOpenEnumW(
        RESOURCE_CONNECTED,
        RESOURCETYPE_DISK,
        RESOURCEUSAGE_ALL,
        None,
        ctypes.byref(enum_handle),
    )
    if open_result != 0:
        return False, f"枚举服务器 SMB 会话失败，错误代码: {open_result}", []

    candidates = []
    protected_remotes = set()
    try:
        while True:
            buffer_size = wintypes.DWORD(64 * 1024)
            buffer = ctypes.create_string_buffer(buffer_size.value)
            count = wintypes.DWORD(0xFFFFFFFF)
            result = ctypes.windll.mpr.WNetEnumResourceW(
                enum_handle,
                ctypes.byref(count),
                buffer,
                ctypes.byref(buffer_size),
            )
            if result == ERROR_NO_MORE_ITEMS:
                break
            if result != 0:
                return False, f"枚举服务器 SMB 会话失败，错误代码: {result}", []

            resources = ctypes.cast(
                buffer,
                ctypes.POINTER(_CONNECTED_NETRESOURCEW),
            )
            for index in range(count.value):
                local_name = resources[index].lpLocalName
                remote_name = resources[index].lpRemoteName
                if not remote_name:
                    continue
                remote_key = remote_name.rstrip("\\").casefold()
                if local_name:
                    protected_remotes.add(remote_key)
                    continue
                if remote_key == server_root.casefold() or remote_key.startswith(server_prefix):
                    candidates.append(remote_name.rstrip("\\"))
    finally:
        ctypes.windll.mpr.WNetCloseEnum(enum_handle)

    # Root/IPC$ connections are the common credential-bearing sessions. Add
    # them as best-effort targets even if the provider omitted them from the
    # connected-resource enumeration.
    # Get-SmbConnection can see connections that WNetEnumResource omits. Add
    # their exact share paths, while preserving connections backed by a drive.
    smb_connections, _smb_error = _get_smb_connections_for_server(server)
    for item in smb_connections:
        share = str(item.get("ShareName") or "").strip("\\")
        if share:
            remote = server_root + "\\" + share
            if remote.casefold() not in protected_remotes:
                candidates.append(remote)

    # The redirector may retain a connection for one exact share while neither
    # Get-SmbConnection nor WNetEnumResource exposes it.  Include the original
    # full UNC supplied by the user so paths with spaces/non-ASCII names are
    # cancelled directly.
    if exact_unc and exact_unc.casefold() not in protected_remotes:
        candidates.append(exact_unc)
    candidates.extend([server_root + "\\IPC$", server_root])
    candidates = list(dict.fromkeys(candidates))

    disconnected = []
    failed = []
    for remote in candidates:
        result = ctypes.windll.mpr.WNetCancelConnection2W(remote, 0, force)
        if result == 0:
            disconnected.append(remote)
        elif result == 2250:
            # Some redirector-only connections cause ERROR_SESSION_CREDENTIAL_CONFLICT
            # but are invisible to WNet enumeration/cancellation. `net use` can
            # still remove them when addressed by their exact UNC.
            try:
                completed = subprocess.run(
                    ["net", "use", remote, "/delete", "/y"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=12,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if completed.returncode == 0:
                    disconnected.append(remote)
            except Exception:
                pass
        else:
            failed.append((remote, result))

    if failed:
        details = ", ".join(f"{path} (错误码 {code})" for path, code in failed)
        if disconnected:
            return True, (
                f"已断开 {len(disconnected)} 个残留 SMB 会话；"
                f"部分断开失败: {details}"
            ), disconnected
        return False, f"断开残留 SMB 会话失败: {details}", []
    if disconnected:
        return True, f"已断开 {len(disconnected)} 个残留 SMB 会话", disconnected
    return True, f"未发现服务器 {server} 的残留 SMB 会话", []


def clear_server_authentication_state(unc_path):
    """断开无盘符 SMB 会话并删除与服务器相关的已保存凭据。"""
    session_ok, session_msg, _sessions = disconnect_server_sessions(unc_path)
    cred_ok, cred_msg, _credentials = delete_credentials_for_unc(unc_path)
    return session_ok and cred_ok, session_msg + "\n- " + cred_msg


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
        cleanup_ok, cleanup_msg = clear_server_authentication_state(unc)
        if cleanup_ok:
            message += f"\n- {cleanup_msg}"
        else:
            message += f"\n- SMB 会话/凭据清理不完整: {cleanup_msg}"
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
        cleanup_ok, cleanup_msg = clear_server_authentication_state(unc)
        if cleanup_ok:
            message += f"\n- {cleanup_msg}"
        else:
            message += f"\n- SMB 会话/凭据清理不完整: {cleanup_msg}"
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
