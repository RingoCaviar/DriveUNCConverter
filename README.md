# Drive ↔ Network Location Converter

[中文](#中文说明) | [English](#english)

---

## 中文说明

### 📋 简介

一个 Windows 工具，用于在**映射网络驱动器**和 **Windows 网络位置**之间进行双向转换。

### ✨ 功能

- 🔄 **驱动器 → 网络位置**：将映射的网络驱动器转换为 Windows 网络位置快捷方式
- 🔄 **网络位置 → 驱动器**：将网络位置转换回映射的网络驱动器（可选择盘符）
- 🌐 **多语言支持**：中文/英文界面切换
- 🎨 **现代界面**：CustomTkinter 深色主题
- 💻 **兼容性**：支持 Windows 7/10/11

### 📸 截图

![主界面](screenshots/main.png)

### 🚀 使用方法

#### 方式一：下载 EXE（推荐）

1. 从 [Releases](../../releases) 下载最新的 `DriveUNCConverter.exe`
2. 双击运行

#### 方式二：从源码运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
python main.py
```

### 🔨 编译打包

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name DriveUNCConverter main.py
```

编译后的 EXE 位于 `dist/DriveUNCConverter.exe`

### 📁 项目结构

```
DriveUNCConverter/
├── main.py           # GUI 主程序
├── drive_utils.py    # 核心转换逻辑
├── requirements.txt  # 依赖列表
└── README.md         # 说明文档
```

### ⚠️ 注意事项

- 转换前请确保没有正在使用相关驱动器或网络位置的文件
- 驱动器断开前会提示确认，支持强制断开选项

---

## English

### 📋 Introduction

A Windows utility for bidirectional conversion between **mapped network drives** and **Windows Network Locations**.

### ✨ Features

- 🔄 **Drive → Network Location**: Convert mapped network drives to Windows Network Location shortcuts
- 🔄 **Network Location → Drive**: Convert network locations back to mapped drives (with selectable drive letter)
- 🌐 **Multi-language**: Chinese/English interface toggle
- 🎨 **Modern UI**: CustomTkinter dark theme
- 💻 **Compatibility**: Supports Windows 7/10/11

### 🚀 Usage

#### Option 1: Download EXE (Recommended)

1. Download the latest `DriveUNCConverter.exe` from [Releases](../../releases)
2. Double-click to run

#### Option 2: Run from Source

```bash
# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

### 🔨 Build

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name DriveUNCConverter main.py
```

The compiled EXE will be in `dist/DriveUNCConverter.exe`

### ⚠️ Caution

- Make sure no files are in use on the drive or network location before conversion
- A confirmation dialog will appear before disconnecting drives

---

## License

MIT License
