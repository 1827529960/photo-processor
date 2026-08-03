#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
证件照批量处理工具
功能：批量处理证件照，支持像素缩放、文件大小限制、格式转换等
"""

import os
import sys
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

from PIL import Image, ExifTags
import io

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue


class OutputFormat(Enum):
    JPG = "JPG"
    PNG = "PNG"
    BMP = "BMP"
    KEEP = "保持原格式"


class DuplicateStrategy(Enum):
    OVERWRITE = "覆盖"
    RENAME = "重命名"
    SKIP = "跳过"


class SizeUnit(Enum):
    KB = "KB"
    MB = "MB"


@dataclass
class ProcessingConfig:
    target_size: float = 500.0
    size_unit: SizeUnit = SizeUnit.KB
    max_width: int = 0
    max_height: int = 0
    fixed_width: int = 0
    fixed_height: int = 0
    enable_crop: bool = False
    min_quality: int = 30
    quality_step: int = 5
    dpi: int = 300
    output_format: OutputFormat = OutputFormat.KEEP
    duplicate_strategy: DuplicateStrategy = DuplicateStrategy.RENAME
    remove_exif: bool = False
    preserve_filename: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            'target_size': self.target_size,
            'size_unit': self.size_unit.value,
            'max_width': self.max_width,
            'max_height': self.max_height,
            'fixed_width': self.fixed_width,
            'fixed_height': self.fixed_height,
            'enable_crop': self.enable_crop,
            'min_quality': self.min_quality,
            'quality_step': self.quality_step,
            'dpi': self.dpi,
            'output_format': self.output_format.value,
            'duplicate_strategy': self.duplicate_strategy.value,
            'remove_exif': self.remove_exif,
            'preserve_filename': self.preserve_filename
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProcessingConfig':
        return cls(
            target_size=data.get('target_size', 500.0),
            size_unit=SizeUnit(data.get('size_unit', 'KB')),
            max_width=data.get('max_width', 0),
            max_height=data.get('max_height', 0),
            fixed_width=data.get('fixed_width', 0),
            fixed_height=data.get('fixed_height', 0),
            enable_crop=data.get('enable_crop', False),
            min_quality=data.get('min_quality', 30),
            quality_step=data.get('quality_step', 5),
            dpi=data.get('dpi', 300),
            output_format=OutputFormat(data.get('output_format', '保持原格式')),
            duplicate_strategy=DuplicateStrategy(data.get('duplicate_strategy', '重命名')),
            remove_exif=data.get('remove_exif', False),
            preserve_filename=data.get('preserve_filename', True)
        )


PRESETS = {
    "一寸证件照": {
        "target_size": 100.0, "size_unit": "KB",
        "max_width": 0, "max_height": 0,
        "fixed_width": 295, "fixed_height": 413,
        "enable_crop": True, "min_quality": 30, "quality_step": 5,
        "dpi": 300, "output_format": "JPG",
        "duplicate_strategy": "重命名", "remove_exif": True,
        "preserve_filename": True
    },
    "二寸证件照": {
        "target_size": 150.0, "size_unit": "KB",
        "max_width": 0, "max_height": 0,
        "fixed_width": 413, "fixed_height": 579,
        "enable_crop": True, "min_quality": 30, "quality_step": 5,
        "dpi": 300, "output_format": "JPG",
        "duplicate_strategy": "重命名", "remove_exif": True,
        "preserve_filename": True
    },
    "小二寸证件照": {
        "target_size": 120.0, "size_unit": "KB",
        "max_width": 0, "max_height": 0,
        "fixed_width": 413, "fixed_height": 531,
        "enable_crop": True, "min_quality": 30, "quality_step": 5,
        "dpi": 300, "output_format": "JPG",
        "duplicate_strategy": "重命名", "remove_exif": True,
        "preserve_filename": True
    },
    "五寸照片": {
        "target_size": 2.0, "size_unit": "MB",
        "max_width": 0, "max_height": 0,
        "fixed_width": 1050, "fixed_height": 1500,
        "enable_crop": False, "min_quality": 50, "quality_step": 5,
        "dpi": 300, "output_format": "JPG",
        "duplicate_strategy": "重命名", "remove_exif": False,
        "preserve_filename": True
    },
    "网络头像": {
        "target_size": 200.0, "size_unit": "KB",
        "max_width": 400, "max_height": 400,
        "fixed_width": 0, "fixed_height": 0,
        "enable_crop": False, "min_quality": 40, "quality_step": 5,
        "dpi": 72, "output_format": "JPG",
        "duplicate_strategy": "重命名", "remove_exif": True,
        "preserve_filename": True
    }
}


class PhotoProcessor:
    def __init__(self, config: ProcessingConfig = None):
        self.config = config or ProcessingConfig()
        self.logger = logging.getLogger(__name__)
        self._setup_logger()

    def _setup_logger(self):
        """配置日志文件，保存到 ~/.photo_processor 目录"""
        user_home = os.path.expanduser("~")
        log_dir = os.path.join(user_home, ".photo_processor")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "photo_processor.log")

        # 配置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(formatter)

        # 配置根日志器
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

    def process_image(self, input_path: str, output_path: str) -> bool:
        try:
            with Image.open(input_path) as img:
                if self.config.remove_exif:
                    img = self._remove_exif(img)
                img = self._resize_image(img)
                self._save_image(img, output_path)
                self._compress_to_target(output_path)
                return True
        except Exception as e:
            self.logger.error(f"处理图片失败 {input_path}: {e}")
            return False

    def _remove_exif(self, img: Image.Image) -> Image.Image:
        data = list(img.getdata())
        new_img = Image.new(img.mode, img.size)
        new_img.putdata(data)
        return new_img

    def _resize_image(self, img: Image.Image) -> Image.Image:
        width, height = img.size

        if self.config.fixed_width > 0 and self.config.fixed_height > 0:
            if self.config.enable_crop:
                img = self._crop_image(img, self.config.fixed_width, self.config.fixed_height)
            else:
                img = img.resize((self.config.fixed_width, self.config.fixed_height),
                                 Image.Resampling.LANCZOS)
            return img

        new_width = width
        new_height = height

        if self.config.max_width > 0 and width > self.config.max_width:
            ratio = self.config.max_width / width
            new_width = self.config.max_width
            new_height = int(height * ratio)

        if self.config.max_height > 0 and new_height > self.config.max_height:
            ratio = self.config.max_height / new_height
            new_height = self.config.max_height
            new_width = int(new_width * ratio)

        if new_width != width or new_height != height:
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        return img

    def _crop_image(self, img: Image.Image, target_width: int, target_height: int) -> Image.Image:
        width, height = img.size
        target_ratio = target_width / target_height
        current_ratio = width / height

        if current_ratio > target_ratio:
            new_width = int(height * target_ratio)
            left = (width - new_width) // 2
            img = img.crop((left, 0, left + new_width, height))
        else:
            new_height = int(width / target_ratio)
            top = (height - new_height) // 2
            img = img.crop((0, top, width, top + new_height))

        return img.resize((target_width, target_height), Image.Resampling.LANCZOS)

    def _save_image(self, img: Image.Image, output_path: str):
        if self.config.output_format == OutputFormat.KEEP:
            ext = Path(output_path).suffix.lower()
            format_map = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.bmp': 'BMP'}
            img_format = format_map.get(ext, 'JPEG')
        else:
            format_map = {OutputFormat.JPG: 'JPEG', OutputFormat.PNG: 'PNG', OutputFormat.BMP: 'BMP'}
            img_format = format_map.get(self.config.output_format, 'JPEG')

        dpi = (self.config.dpi, self.config.dpi)

        if img_format == 'JPEG':
            img.save(output_path, format=img_format, quality=95, dpi=dpi, optimize=True)
        else:
            img.save(output_path, format=img_format, dpi=dpi)

    def _compress_to_target(self, file_path: str):
        target_bytes = self._get_target_bytes()
        current_size = os.path.getsize(file_path)

        if target_bytes > 0 and abs(current_size - target_bytes) / target_bytes < 0.1:
            return

        ext = Path(file_path).suffix.lower()
        if ext not in ('.jpg', '.jpeg'):
            if current_size > target_bytes:
                new_path = Path(file_path).with_suffix('.jpg')
                with Image.open(file_path) as img:
                    if img.mode in ('RGBA', 'LA', 'P'):
                        img = img.convert('RGB')
                    img.save(str(new_path), format='JPEG', quality=95,
                             dpi=(self.config.dpi, self.config.dpi), optimize=True)
                os.remove(file_path)
                file_path = str(new_path)
                current_size = os.path.getsize(file_path)
            else:
                return

        low = self.config.min_quality
        high = 95
        best_quality = 95

        if current_size > target_bytes:
            while low <= high:
                mid = (low + high) // 2
                with Image.open(file_path) as img:
                    img.save(file_path, format='JPEG', quality=mid,
                             dpi=(self.config.dpi, self.config.dpi), optimize=True)
                current_size = os.path.getsize(file_path)
                if abs(current_size - target_bytes) / target_bytes < 0.05:
                    best_quality = mid
                    break
                elif current_size > target_bytes:
                    high = mid - 1
                else:
                    low = mid + 1
                    best_quality = mid
        else:
            while low <= high:
                mid = (low + high) // 2
                with Image.open(file_path) as img:
                    img.save(file_path, format='JPEG', quality=mid,
                             dpi=(self.config.dpi, self.config.dpi), optimize=True)
                current_size = os.path.getsize(file_path)
                if abs(current_size - target_bytes) / target_bytes < 0.05:
                    best_quality = mid
                    break
                elif current_size < target_bytes:
                    low = mid + 1
                else:
                    high = mid - 1
                    best_quality = mid

        with Image.open(file_path) as img:
            img.save(file_path, format='JPEG', quality=best_quality,
                     dpi=(self.config.dpi, self.config.dpi), optimize=True)

    def _get_target_bytes(self) -> int:
        if self.config.size_unit == SizeUnit.KB:
            return int(self.config.target_size * 1024)
        else:
            return int(self.config.target_size * 1024 * 1024)

    def batch_process(self, input_paths: List[str], output_dir: str,
                      progress_callback=None) -> Dict[str, Any]:
        results = {'success': 0, 'failed': 0, 'skipped': 0, 'files': []}
        os.makedirs(output_dir, exist_ok=True)

        for i, input_path in enumerate(input_paths):
            if progress_callback:
                progress_callback(i + 1, len(input_paths), input_path)

            output_path = self._get_output_path(input_path, output_dir)
            if output_path is None:
                results['skipped'] += 1
                continue

            success = self.process_image(input_path, output_path)
            if success:
                results['success'] += 1
                results['files'].append({
                    'input': input_path,
                    'output': output_path,
                    'input_size': os.path.getsize(input_path),
                    'output_size': os.path.getsize(output_path)
                })
            else:
                results['failed'] += 1

        return results

    def _get_output_path(self, input_path: str, output_dir: str) -> Optional[str]:
        filename = Path(input_path).name

        if self.config.preserve_filename:
            output_path = os.path.join(output_dir, filename)
        else:
            stem = Path(input_path).stem
            ext = Path(input_path).suffix
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(output_dir, f"{stem}_{timestamp}{ext}")

        if os.path.exists(output_path):
            if self.config.duplicate_strategy == DuplicateStrategy.OVERWRITE:
                pass
            elif self.config.duplicate_strategy == DuplicateStrategy.SKIP:
                return None
            else:
                stem = Path(output_path).stem
                ext = Path(output_path).suffix
                counter = 1
                while os.path.exists(output_path):
                    output_path = os.path.join(output_dir, f"{stem}_{counter}{ext}")
                    counter += 1

        return output_path


class PhotoProcessorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("证件照批量处理工具 v1.0")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)

        self.config = ProcessingConfig()
        self.processor = PhotoProcessor(self.config)

        self._create_variables()
        self._create_ui()
        self._create_menu()

        self._show_startup_tip()

    def _create_variables(self):
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar(value="output")
        self.target_size_var = tk.DoubleVar(value=500.0)
        self.size_unit_var = tk.StringVar(value="KB")
        self.max_width_var = tk.IntVar(value=0)
        self.max_height_var = tk.IntVar(value=0)
        self.fixed_width_var = tk.IntVar(value=0)
        self.fixed_height_var = tk.IntVar(value=0)
        self.enable_crop_var = tk.BooleanVar(value=False)
        self.min_quality_var = tk.IntVar(value=30)
        self.quality_step_var = tk.IntVar(value=5)
        self.dpi_var = tk.IntVar(value=300)
        self.output_format_var = tk.StringVar(value="保持原格式")
        self.duplicate_var = tk.StringVar(value="重命名")
        self.remove_exif_var = tk.BooleanVar(value=False)
        self.preserve_filename_var = tk.BooleanVar(value=True)
        self.log_queue = queue.Queue()

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # 文件菜单
        self.file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=self.file_menu)

        # 最近打开文件夹
        self.recent_folders_menu = tk.Menu(self.file_menu, tearoff=0)
        self.file_menu.add_cascade(label="最近打开文件夹", menu=self.recent_folders_menu)
        self._update_recent_folders_menu()

        self.file_menu.add_separator()

        # 最近打开文件
        self.recent_files_menu = tk.Menu(self.file_menu, tearoff=0)
        self.file_menu.add_cascade(label="最近打开文件", menu=self.recent_files_menu)
        self._update_recent_files_menu()

        self.file_menu.add_separator()

        # 保存预设值
        self.file_menu.add_command(label="保存预设值", command=self._save_preset)

        # 加载预设值
        self.load_preset_menu = tk.Menu(self.file_menu, tearoff=0)
        self.file_menu.add_cascade(label="加载预设值", menu=self.load_preset_menu)
        self._update_load_preset_menu()

        self.file_menu.add_separator()

        # 最近保存预设值
        self.recent_presets_menu = tk.Menu(self.file_menu, tearoff=0)
        self.file_menu.add_cascade(label="最近保存预设值", menu=self.recent_presets_menu)
        self._update_recent_presets_menu()

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="使用说明", command=self._show_help)
        help_menu.add_separator()
        help_menu.add_command(label="关于", command=self._show_about)

    def _update_recent_folders_menu(self):
        self.recent_folders_menu.delete(0, tk.END)
        settings = self._load_settings()
        recent_folders = settings.get("recent_folders", [])

        if not recent_folders:
            self.recent_folders_menu.add_command(label="(无历史记录)", state=tk.DISABLED)
            return

        for folder in recent_folders:
            self.recent_folders_menu.add_command(
                label=folder,
                command=lambda f=folder: self._open_recent_folder(f)
            )

    def _update_recent_files_menu(self):
        self.recent_files_menu.delete(0, tk.END)
        settings = self._load_settings()
        recent_files = settings.get("recent_files", [])

        if not recent_files:
            self.recent_files_menu.add_command(label="(无历史记录)", state=tk.DISABLED)
            return

        for file_path in recent_files:
            self.recent_files_menu.add_command(
                label=file_path,
                command=lambda f=file_path: self._open_recent_file(f)
            )

    def _update_load_preset_menu(self):
        self.load_preset_menu.delete(0, tk.END)

        # 内置预设
        for name in PRESETS.keys():
            self.load_preset_menu.add_command(
                label=name,
                command=lambda n=name: self._quick_load_preset(n)
            )

        # 用户自定义预设
        settings = self._load_settings()
        custom_presets = settings.get("custom_presets", {})
        if custom_presets:
            self.load_preset_menu.add_separator()
            for name in custom_presets.keys():
                self.load_preset_menu.add_command(
                    label=f"[自定义] {name}",
                    command=lambda n=name: self._load_custom_preset(n)
                )

    def _update_recent_presets_menu(self):
        self.recent_presets_menu.delete(0, tk.END)
        settings = self._load_settings()
        recent_presets = settings.get("recent_presets", [])

        if not recent_presets:
            self.recent_presets_menu.add_command(label="(无历史记录)", state=tk.DISABLED)
            return

        for preset_name in recent_presets:
            self.recent_presets_menu.add_command(
                label=preset_name,
                command=lambda n=preset_name: self._load_recent_preset(n)
            )

    def _open_recent_folder(self, folder: str):
        if os.path.exists(folder):
            self.input_var.set(folder)
            self._log(f"已加载文件夹: {folder}")
        else:
            messagebox.showwarning("警告", f"文件夹不存在: {folder}")
            settings = self._load_settings()
            recent_folders = settings.get("recent_folders", [])
            if folder in recent_folders:
                recent_folders.remove(folder)
                settings["recent_folders"] = recent_folders
                self._save_settings(settings)
                self._update_recent_folders_menu()

    def _open_recent_file(self, file_path: str):
        if os.path.exists(file_path):
            self.input_var.set(file_path)
            self._log(f"已加载文件: {file_path}")
        else:
            messagebox.showwarning("警告", f"文件不存在: {file_path}")
            settings = self._load_settings()
            recent_files = settings.get("recent_files", [])
            if file_path in recent_files:
                recent_files.remove(file_path)
                settings["recent_files"] = recent_files
                self._save_settings(settings)
                self._update_recent_files_menu()

    def _save_preset(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("保存预设值")
        dialog.geometry("400x150")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="预设名称:").grid(row=0, column=0, padx=10, pady=20)
        name_var = tk.StringVar()
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=30)
        name_entry.grid(row=0, column=1, padx=10, pady=20)
        name_entry.focus_set()

        def on_save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("警告", "请输入预设名称")
                return

            self._update_config_from_ui()
            preset_data = self.config.to_dict()

            settings = self._load_settings()
            if "custom_presets" not in settings:
                settings["custom_presets"] = {}
            settings["custom_presets"][name] = preset_data

            # 更新最近保存预设值
            recent_presets = settings.get("recent_presets", [])
            if name in recent_presets:
                recent_presets.remove(name)
            recent_presets.insert(0, name)
            settings["recent_presets"] = recent_presets[:5]

            self._save_settings(settings)
            self._update_load_preset_menu()
            self._update_recent_presets_menu()
            self._log(f"已保存预设: {name}")
            dialog.destroy()

        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=1, column=0, columnspan=2, pady=10)
        ttk.Button(button_frame, text="保存", command=on_save).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=10)

    def _load_custom_preset(self, name: str):
        settings = self._load_settings()
        custom_presets = settings.get("custom_presets", {})
        preset_data = custom_presets.get(name)

        if preset_data:
            self.config = ProcessingConfig.from_dict(preset_data)
            self._load_config_to_ui()
            self._log(f"已加载自定义预设: {name}")
        else:
            messagebox.showwarning("警告", f"预设 '{name}' 不存在")

    def _load_recent_preset(self, name: str):
        # 先检查内置预设
        if name in PRESETS:
            self._quick_load_preset(name)
            return

        # 再检查自定义预设
        settings = self._load_settings()
        custom_presets = settings.get("custom_presets", {})
        if name in custom_presets:
            self._load_custom_preset(name)
        else:
            messagebox.showwarning("警告", f"预设 '{name}' 不存在")

    def _create_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        self._create_input_section(main_frame)
        self._create_size_section(main_frame)
        self._create_quality_section(main_frame)
        self._create_output_section(main_frame)
        self._create_action_section(main_frame)
        self._create_log_section(main_frame)

    def _create_input_section(self, parent):
        frame = ttk.LabelFrame(parent, text="输入设置", padding="5")
        frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        ttk.Label(frame, text="输入路径:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(frame, textvariable=self.input_var, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(frame, text="选择文件", command=self._select_files).grid(row=0, column=2, padx=2)
        ttk.Button(frame, text="选择文件夹", command=self._select_folder).grid(row=0, column=3)

    def _create_size_section(self, parent):
        frame = ttk.LabelFrame(parent, text="尺寸设置", padding="5")
        frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        ttk.Label(frame, text="目标大小:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(frame, textvariable=self.target_size_var, width=10).grid(row=0, column=1, padx=5)
        ttk.Combobox(frame, textvariable=self.size_unit_var, values=["KB", "MB"],
                     width=5, state='readonly').grid(row=0, column=2, padx=5)
        ttk.Label(frame, text="最大宽度:").grid(row=0, column=3, sticky=tk.W, padx=(20, 0))
        ttk.Entry(frame, textvariable=self.max_width_var, width=8).grid(row=0, column=4, padx=5)
        ttk.Label(frame, text="最大高度:").grid(row=0, column=5, sticky=tk.W)
        ttk.Entry(frame, textvariable=self.max_height_var, width=8).grid(row=0, column=6, padx=5)
        ttk.Label(frame, text="固定宽度:").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(frame, textvariable=self.fixed_width_var, width=10).grid(row=1, column=1, padx=5)
        ttk.Label(frame, text="固定高度:").grid(row=1, column=2, sticky=tk.W)
        ttk.Entry(frame, textvariable=self.fixed_height_var, width=10).grid(row=1, column=3, padx=5)
        ttk.Checkbutton(frame, text="启用裁剪", variable=self.enable_crop_var).grid(row=1, column=4, padx=5)

    def _create_quality_section(self, parent):
        frame = ttk.LabelFrame(parent, text="画质设置", padding="5")
        frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        ttk.Label(frame, text="最低画质:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(frame, textvariable=self.min_quality_var, width=8).grid(row=0, column=1, padx=5)
        ttk.Label(frame, text="画质步长:").grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        ttk.Entry(frame, textvariable=self.quality_step_var, width=8).grid(row=0, column=3, padx=5)
        ttk.Label(frame, text="DPI:").grid(row=0, column=4, sticky=tk.W, padx=(20, 0))
        ttk.Entry(frame, textvariable=self.dpi_var, width=8).grid(row=0, column=5, padx=5)

    def _create_output_section(self, parent):
        frame = ttk.LabelFrame(parent, text="输出设置", padding="5")
        frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        ttk.Label(frame, text="输出路径:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(frame, textvariable=self.output_var, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(frame, text="选择文件夹", command=self._select_output_folder).grid(row=0, column=2)
        ttk.Label(frame, text="输出格式:").grid(row=1, column=0, sticky=tk.W)
        ttk.Combobox(frame, textvariable=self.output_format_var,
                     values=["保持原格式", "JPG", "PNG", "BMP"],
                     width=15, state='readonly').grid(row=1, column=1, padx=5, sticky=tk.W)
        ttk.Label(frame, text="同名文件:").grid(row=1, column=2, sticky=tk.W, padx=(20, 0))
        ttk.Combobox(frame, textvariable=self.duplicate_var,
                     values=["覆盖", "重命名", "跳过"],
                     width=10, state='readonly').grid(row=1, column=3, padx=5, sticky=tk.W)
        ttk.Checkbutton(frame, text="移除EXIF", variable=self.remove_exif_var).grid(row=1, column=4, padx=10)
        ttk.Checkbutton(frame, text="保留文件名", variable=self.preserve_filename_var).grid(row=1, column=5)

    def _create_action_section(self, parent):
        frame = ttk.Frame(parent)
        frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        frame.columnconfigure(1, weight=1)

        quick_frame = ttk.LabelFrame(frame, text="常用预设（点击自动填充参数）", padding="5")
        quick_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 10))
        presets = [
            ("一寸 295x413", "一寸证件照"),
            ("二寸 413x579", "二寸证件照"),
            ("小二寸 413x531", "小二寸证件照"),
            ("五寸 1050x1500", "五寸照片"),
            ("头像 400x400", "网络头像")
        ]
        for i, (text, preset_name) in enumerate(presets):
            btn = ttk.Button(quick_frame, text=text,
                             command=lambda n=preset_name: self._quick_load_preset(n))
            btn.grid(row=0, column=i, padx=3, pady=2)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=0, column=1, sticky=(tk.E))
        self.start_button = ttk.Button(button_frame, text="开始处理",
                                       command=self._start_processing)
        self.start_button.grid(row=0, column=0, padx=(0, 5))
        ttk.Button(button_frame, text="清空日志",
                   command=self._clear_log).grid(row=0, column=1, padx=(0, 5))
        ttk.Button(button_frame, text="打开输出文件夹",
                   command=self._open_output_folder).grid(row=0, column=2)

    def _create_log_section(self, parent):
        frame = ttk.LabelFrame(parent, text="处理日志", padding="5")
        frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.log_text = scrolledtext.ScrolledText(frame, height=10, width=70)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        parent.rowconfigure(5, weight=1)

    def _select_files(self):
        files = filedialog.askopenfilenames(
            title="选择图片文件",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.bmp"), ("所有文件", "*.*")]
        )
        if files:
            self.input_var.set("; ".join(files))
            self._add_recent_files(list(files))

    def _select_folder(self):
        folder = filedialog.askdirectory(title="选择图片文件夹")
        if folder:
            self.input_var.set(folder)
            self._add_recent_folder(folder)

    def _select_output_folder(self):
        folder = filedialog.askdirectory(title="选择输出文件夹")
        if folder:
            self.output_var.set(folder)

    def _add_recent_folder(self, folder: str):
        settings = self._load_settings()
        recent_folders = settings.get("recent_folders", [])
        if folder in recent_folders:
            recent_folders.remove(folder)
        recent_folders.insert(0, folder)
        settings["recent_folders"] = recent_folders[:5]
        self._save_settings(settings)
        self._update_recent_folders_menu()

    def _add_recent_files(self, files: List[str]):
        settings = self._load_settings()
        recent_files = settings.get("recent_files", [])
        for file_path in files:
            if file_path in recent_files:
                recent_files.remove(file_path)
            recent_files.insert(0, file_path)
        settings["recent_files"] = recent_files[:5]
        self._save_settings(settings)
        self._update_recent_files_menu()

    def _update_config_from_ui(self):
        self.config.target_size = self.target_size_var.get()
        self.config.size_unit = SizeUnit(self.size_unit_var.get())
        self.config.max_width = self.max_width_var.get()
        self.config.max_height = self.max_height_var.get()
        self.config.fixed_width = self.fixed_width_var.get()
        self.config.fixed_height = self.fixed_height_var.get()
        self.config.enable_crop = self.enable_crop_var.get()
        self.config.min_quality = self.min_quality_var.get()
        self.config.quality_step = self.quality_step_var.get()
        self.config.dpi = self.dpi_var.get()
        self.config.remove_exif = self.remove_exif_var.get()
        self.config.preserve_filename = self.preserve_filename_var.get()
        self.config.output_format = OutputFormat(self.output_format_var.get())
        self.config.duplicate_strategy = DuplicateStrategy(self.duplicate_var.get())
        self.processor.config = self.config

    def _load_config_to_ui(self):
        self.target_size_var.set(self.config.target_size)
        self.size_unit_var.set(self.config.size_unit.value)
        self.max_width_var.set(self.config.max_width)
        self.max_height_var.set(self.config.max_height)
        self.fixed_width_var.set(self.config.fixed_width)
        self.fixed_height_var.set(self.config.fixed_height)
        self.enable_crop_var.set(self.config.enable_crop)
        self.min_quality_var.set(self.config.min_quality)
        self.quality_step_var.set(self.config.quality_step)
        self.dpi_var.set(self.config.dpi)
        self.remove_exif_var.set(self.config.remove_exif)
        self.preserve_filename_var.set(self.config.preserve_filename)
        self.output_format_var.set(self.config.output_format.value)
        self.duplicate_var.set(self.config.duplicate_strategy.value)

    def _quick_load_preset(self, name):
        preset = PRESETS.get(name)
        if preset:
            self.config = ProcessingConfig.from_dict(preset)
            self._load_config_to_ui()
            self._log(f"已加载预设：{name}")
        else:
            messagebox.showwarning("警告", f"预设 '{name}' 不存在")

    def _start_processing(self):
        input_path = self.input_var.get()
        if not input_path:
            messagebox.showwarning("警告", "请选择输入文件或文件夹")
            return

        self._update_config_from_ui()

        input_paths = []
        if os.path.isfile(input_path):
            input_paths = [input_path]
        elif os.path.isdir(input_path):
            for root, dirs, files in os.walk(input_path):
                for file in files:
                    if file.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
                        input_paths.append(os.path.join(root, file))

        if not input_paths:
            messagebox.showwarning("警告", "未找到图片文件")
            return

        output_dir = self.output_var.get()
        if not output_dir:
            output_dir = "output"

        self.start_button.config(state='disabled')
        thread = threading.Thread(target=self._process_thread,
                                  args=(input_paths, output_dir))
        thread.daemon = True
        thread.start()

    def _process_thread(self, input_paths: List[str], output_dir: str):
        def progress_callback(current, total, filename):
            self.log_queue.put(('progress', current, total, filename))

        try:
            results = self.processor.batch_process(input_paths, output_dir, progress_callback)
            self.log_queue.put(('complete', results))
        except Exception as e:
            self.log_queue.put(('error', str(e)))
        finally:
            self.log_queue.put(('enable_button',))

    def _log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    def _clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def _open_output_folder(self):
        output_dir = self.output_var.get()
        if os.path.exists(output_dir):
            os.startfile(output_dir)
        else:
            messagebox.showwarning("警告", "输出文件夹不存在")

    def _process_log_queue(self):
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                if msg[0] == 'progress':
                    current, total, filename = msg[1], msg[2], msg[3]
                    self._log(f"处理中 [{current}/{total}]: {os.path.basename(filename)}")
                elif msg[0] == 'complete':
                    results = msg[1]
                    self._log(f"处理完成！成功: {results['success']}, 失败: {results['failed']}")
                    messagebox.showinfo("完成",
                                        f"处理完成！\n成功: {results['success']}\n失败: {results['failed']}")
                elif msg[0] == 'error':
                    self._log(f"错误: {msg[1]}")
                    messagebox.showerror("错误", msg[1])
                elif msg[0] == 'enable_button':
                    self.start_button.config(state='normal')
            except queue.Empty:
                break
        self.root.after(100, self._process_log_queue)

    def _get_config_path(self):
        # 配置文件保存到用户主目录
        user_home = os.path.expanduser("~")
        config_dir = os.path.join(user_home, ".photo_processor")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "config.json")

    def _load_settings(self):
        config_path = self._get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"show_startup_tip": True}

    def _save_settings(self, settings: dict):
        config_path = self._get_config_path()
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _show_startup_tip(self):
        settings = self._load_settings()
        if settings.get("show_startup_tip", True):
            self._show_help_dialog(startup=True)

    def _show_help(self):
        self._show_help_dialog(startup=False)

    def _show_help_dialog(self, startup=False):
        dialog = tk.Toplevel(self.root)
        dialog.title("使用说明")
        dialog.geometry("600x500")
        dialog.transient(self.root)
        dialog.grab_set()

        text = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, padx=15, pady=15)
        text.pack(fill=tk.BOTH, expand=True)

        help_content = """
证件照批量处理工具 - 使用说明

【功能介绍】
本工具用于批量处理证件照，支持以下功能：
• 按目标文件大小压缩（二分查找精确匹配）
• 按固定尺寸裁剪（一寸、二寸等证件照规格）
• 按最大尺寸缩放
• 格式转换（JPG/PNG/BMP）
• 移除EXIF信息
• 批量处理

【快速开始】
1. 点击"选择文件"或"选择文件夹"选择要处理的图片
2. 在"常用预设"中点击对应按钮，自动填充证件照参数
3. 点击"开始处理"

【菜单栏说明】
• 文件 > 最近打开文件夹：快速选择之前打开过的文件夹
• 文件 > 最近打开文件：快速选择之前打开过的文件
• 文件 > 保存预设值：将当前参数设置保存为自定义预设
• 文件 > 加载预设值：加载内置或自定义预设
• 文件 > 最近保存预设值：快速加载最近保存的预设
• 帮助 > 使用说明：查看本帮助文档
• 帮助 > 关于：查看软件信息

【常用预设】
• 一寸证件照：295×413像素，约100KB
• 二寸证件照：413×579像素，约150KB
• 小二寸证件照：413×531像素，约120KB
• 五寸照片：1050×1500像素，约2MB
• 网络头像：400×400像素，约200KB

【参数说明】
• 目标大小：压缩后的文件大小（支持KB/MB）
• 最大宽度/高度：缩放时的最大尺寸
• 固定宽度/高度：证件照的精确尺寸
• 启用裁剪：按比例裁剪到目标尺寸
• 最低画质：压缩时的最低画质（1-100）
• DPI：输出图片的分辨率

【输出设置】
• 输出格式：保持原格式或转换为JPG/PNG/BMP
• 同名文件：覆盖、重命名或跳过
• 移除EXIF：删除图片的元数据信息
• 保留文件名：保持原文件名不变

【注意事项】
• 支持的图片格式：JPG、JPEG、PNG、BMP
• 压缩到目标大小时，非JPEG格式会自动转换为JPEG
• 建议先用少量图片测试参数效果

【运行时文件】
软件运行时会在用户主目录下生成 .photo_processor 文件夹，包含：
• config.json - 配置文件（启动提示、历史记录等）
• photo_processor.log - 运行日志文件

文件位置：
• Windows: C:\\Users\\用户名\\.photo_processor\\
• macOS/Linux: ~/.photo_processor/

⚠️ 卸载软件时，请同时删除该文件夹以完全清理软件数据。
"""

        text.insert(tk.END, help_content)
        text.config(state=tk.DISABLED)

        bottom_frame = ttk.Frame(dialog, padding="10")
        bottom_frame.pack(fill=tk.X)

        no_show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bottom_frame, text="不再弹出此对话框",
                        variable=no_show_var).pack(side=tk.LEFT)

        def on_close():
            if no_show_var.get():
                settings = self._load_settings()
                settings["show_startup_tip"] = False
                self._save_settings(settings)
            dialog.destroy()

        ttk.Button(bottom_frame, text="关闭", command=on_close).pack(side=tk.RIGHT)

        dialog.protocol("WM_DELETE_WINDOW", on_close)

    def _show_about(self):
        messagebox.showinfo("关于",
                            "证件照批量处理工具 v1.0\n\n"
                            "功能：批量处理证件照，支持像素缩放、文件大小限制、格式转换等\n\n"
                            "作者：Alpha")

    def run(self):
        self._process_log_queue()
        self.root.mainloop()


def main():
    app = PhotoProcessorGUI()
    app.run()


if __name__ == "__main__":
    main()
