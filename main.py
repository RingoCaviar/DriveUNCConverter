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
    drive_to_unc
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
        "window_title": "驱动器 ↔ 网络位置 转换器",
        "main_title": "🔄 驱动器 ↔ 网络位置 转换器",
        "subtitle": "在映射驱动器和网络位置之间双向转换",
        "tab_drive_to_loc": "驱动器 → 网络位置",
        "tab_loc_to_drive": "网络位置 → 驱动器",
        "mapped_drives": "💿 映射的网络驱动器",
        "network_locations": "📁 网络位置",
        "refresh": "🔄 刷新",
        "convert_to_location": "转换为网络位置",
        "convert_to_drive": "映射为驱动器",
        "drive_letter": "盘符:",
        "no_drives": "未检测到映射的网络驱动器",
        "no_locations": "未检测到网络位置\n\n网络位置可通过\"驱动器 → 网络位置\"转换创建",
        "tip_drive_to_loc": "💡 点击\"转换为网络位置\"后，将在Windows的网络位置中创建快捷方式，并断开驱动器映射",
        "tip_loc_to_drive": "💡 选择一个可用的盘符，点击\"映射为驱动器\"后，将创建驱动器映射并删除网络位置",
        "ready": "就绪",
        "refreshed": "列表已刷新",
        "converting": "正在转换...",
        "confirm_drive_to_loc": "确定要将驱动器 {drive} 转换为网络位置吗？\n\nUNC路径: {unc}\n\n⚠️ 此操作将：\n• 创建网络位置快捷方式\n• 断开驱动器 {drive} 的映射\n\n请确保没有正在使用该驱动器的文件！",
        "confirm_loc_to_drive": "确定要将网络位置转换为驱动器映射吗？\n\n网络位置: {name}\nUNC路径: {unc}\n目标盘符: {drive}\n\n此操作将：\n• 映射 {drive} 到 {unc}\n• 删除网络位置 {name}",
        "confirm_title": "确认转换",
        "success": "转换成功",
        "error": "转换失败",
        "error_no_drive": "请选择一个驱动器盘符",
        "files_in_use": "文件占用",
        "force_disconnect": "{msg}\n\n是否强制断开？（可能导致未保存数据丢失）",
        "lang_btn": "EN",
    },
    "en": {
        "window_title": "Drive ↔ Network Location Converter",
        "main_title": "🔄 Drive ↔ Network Location Converter",
        "subtitle": "Bidirectional conversion between mapped drives and network locations",
        "tab_drive_to_loc": "Drive → Network Location",
        "tab_loc_to_drive": "Network Location → Drive",
        "mapped_drives": "💿 Mapped Network Drives",
        "network_locations": "📁 Network Locations",
        "refresh": "🔄 Refresh",
        "convert_to_location": "Convert to Location",
        "convert_to_drive": "Map as Drive",
        "drive_letter": "Drive:",
        "no_drives": "No mapped network drives detected",
        "no_locations": "No network locations detected\n\nNetwork locations can be created via \"Drive → Network Location\" conversion",
        "tip_drive_to_loc": "💡 Click \"Convert to Location\" to create a shortcut in Windows Network Locations and disconnect the drive mapping",
        "tip_loc_to_drive": "💡 Select an available drive letter, click \"Map as Drive\" to create drive mapping and delete the network location",
        "ready": "Ready",
        "refreshed": "List refreshed",
        "converting": "Converting...",
        "confirm_drive_to_loc": "Are you sure you want to convert drive {drive} to a network location?\n\nUNC Path: {unc}\n\n⚠️ This will:\n• Create a network location shortcut\n• Disconnect drive {drive} mapping\n\nMake sure no files are in use on this drive!",
        "confirm_loc_to_drive": "Are you sure you want to convert the network location to a drive mapping?\n\nNetwork Location: {name}\nUNC Path: {unc}\nTarget Drive: {drive}\n\nThis will:\n• Map {drive} to {unc}\n• Delete network location {name}",
        "confirm_title": "Confirm Conversion",
        "success": "Conversion Successful",
        "error": "Conversion Failed",
        "error_no_drive": "Please select a drive letter",
        "files_in_use": "Files In Use",
        "force_disconnect": "{msg}\n\nForce disconnect? (May cause unsaved data loss)",
        "lang_btn": "中文",
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
        
        # 创建两个选项卡
        self.tab_drive_to_loc = self.tabview.add(self.get_text("tab_drive_to_loc"))
        self.tab_loc_to_drive = self.tabview.add(self.get_text("tab_loc_to_drive"))
        
        # 构建选项卡内容
        self.create_drive_to_location_tab()
        self.create_location_to_drive_tab()
        
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
            messagebox.showinfo(self.get_text("success"), message)
        else:
            self.set_status(f"❌ {message}", color="red")
            messagebox.showerror(self.get_text("error"), message)
    
    # ==================== 通用方法 ====================
    
    def on_refresh(self):
        """刷新所有数据"""
        self.refresh_data()
        self.update_drives_list()
        self.update_locations_list()
        self.set_status(self.get_text("refreshed"), color="green")
    
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
