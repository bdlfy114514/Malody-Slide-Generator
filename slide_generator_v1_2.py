#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Malody Slide 生成器 —— 桌面版 v1.2

与安卓版（android/ 工程）功能对齐：
  * 节点 2–15 个，可动态增删
  * 锯齿「按段」可选（每段独立开关），幅度为所有锯齿段共用
  * 预览反映锯齿效果，并标注各节点
  * 原生文件选择（tkinter 文件对话框），不再需要手动复制粘贴路径
  * 写回原文件前自动生成 .bak 备份

算法核心**不在本文件中**，而是与安卓版共用同一份源码：
    src/main/python/slide_core.py
本脚本只负责界面与文件读写；`drawslide / timetrans / transtime_rev` 全部从那里导入，
因此桌面版与手机版永远算出一模一样的结果（不会像 v1.1 那样分叉）。

依赖：仅 Python 标准库（tkinter）。需要 Python 3.8 或更高版本。
"""

import os
import sys
import json
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox

# ==================== 定位并导入共用的算法核心 ====================

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))

# 候选顺序：
#   ① 本脚本同目录（PC 版压缩包解压后的样子，也是仓库根目录的样子）
#   ② 仓库的 src/main/python/、以及历史版本的 android/ 路径（兼容旧检出）
_CORE_CANDIDATES = [
    os.path.join(_THIS_DIR, "slide_core.py"),
    os.path.join(_THIS_DIR, "src", "main", "python", "slide_core.py"),
    os.path.join(_THIS_DIR, "android", "app", "src", "main", "python", "slide_core.py"),
]


def _load_core():
    for path in _CORE_CANDIDATES:
        if os.path.isfile(path):
            core_dir = os.path.dirname(path)
            if core_dir not in sys.path:
                sys.path.insert(0, core_dir)
            import slide_core  # noqa: E402
            return slide_core, path
    raise SystemExit(
        "找不到算法核心 slide_core.py。\n\n"
        "它必须和本脚本放在同一个文件夹里。请确认解压后目录结构为：\n"
        "  你的文件夹\\\n"
        "  ├─ slide_generator_v1_2.py\n"
        "  └─ slide_core.py\n\n"
        "已尝试过的位置：\n  " + "\n  ".join(_CORE_CANDIDATES)
    )


core, CORE_PATH = _load_core()

MAX_NODES = 15
MIN_NODES = 2

# 形状：代号 → 界面显示名（与手机端可选列表一致）
SHAPES = (
    ("s", "直线"),
    ("si", "先快后慢"),
    ("so", "先慢后快"),
    ("b", "S 形"),
)
SHAPE_LABEL = dict(SHAPES)
SHAPE_BY_LABEL = {v: k for k, v in SHAPES}

# 配色
BG = "#1e1e1e"
CARD_BG = "#2b2b2b"
FG = "#e8e8e8"
MUTED = "#9a9a9a"
ACCENT = "#2196F3"
GREEN = "#4CAF50"
CANVAS_BG = "#121212"


# ==================== 状态与工具函数 ====================

class NodeState:
    """一个节点的编辑状态。

    文本/形状/锯齿都用 tkinter 变量承载，因此「重建界面」不会丢输入，
    界面与数据天然同步（不需要手动回读每个 Entry）。
    """

    def __init__(self, t="", x="", shape="s", serrated=False):
        self.var_t = tk.StringVar(value=t)
        self.var_x = tk.StringVar(value=x)
        self.var_shape = tk.StringVar(value=SHAPE_LABEL.get(shape, "直线"))
        self.var_serrated = tk.BooleanVar(value=serrated)

    @property
    def t(self):
        return self.var_t.get().strip()

    @property
    def x(self):
        return self.var_x.get().strip()

    @property
    def shape(self):
        """界面显示名 → 算法代号（s / si / so / b）"""
        return SHAPE_BY_LABEL.get(self.var_shape.get(), "s")

    @property
    def serrated(self):
        return bool(self.var_serrated.get())

    def is_blank(self):
        return self.t == "" and self.x == ""


def _as_int(text, name, empty_ok=False, default=0):
    s = str(text).strip()
    if s == "":
        if empty_ok:
            return default
        raise ValueError(f"{name}不能为空。")
    if not _is_int(s):
        raise ValueError(f"{name}必须是整数（可正可负可为 0）。")
    return int(s)


def _is_int(s):
    s = str(s).strip()
    if not s:
        return False
    body = s[1:] if s[0] in "+-" else s
    return body.isdigit()


def _parse_time(text):
    """把 '[4,1,4]' 解析成 [4,1,4]；兼容 '(4,1,4)' 与 '4,1,4'。"""
    s = str(text).strip()
    if s == "":
        raise ValueError("节点时间不能为空。")
    if s[0] in "[(" and s[-1] in "])":
        s = s[1:-1]
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 3:
        raise ValueError(f"时间格式应为 [拍,线,细分]，例如 [4,1,4]；收到的是：{text}")
    out = []
    for p in parts:
        if not _is_int(p):
            raise ValueError(f"时间的三个值都必须是整数；收到的是：{text}")
        out.append(int(p))
    if out[2] == 0:
        raise ValueError("节拍细分数（第三个值）不能为 0。")
    return out


# ==================== 预览绘制 ====================

def draw_preview(canvas, points, nodes_xy=None):
    """在 Canvas 上绘制预览。

    points   : [(x, t), ...] 由算法给出的轨迹点（已含锯齿）
    nodes_xy : [(x, t), ...] 可选，节点位置，用于画节点方块与序号
    """
    canvas.delete("all")
    cw = max(int(canvas.winfo_width()), 2)
    ch = max(int(canvas.winfo_height()), 2)

    # 基线（x=0 / x=256），与旧版一致的虚线参考线
    margin = 24
    def base_x(x_val):
        return margin + (x_val / 256.0) * max(cw - 2 * margin, 1)

    for xv in (0, 256):
        cx = base_x(xv)
        canvas.create_line(cx, 0, cx, ch, fill="#333333", dash=(4, 4))

    if not points:
        canvas.create_text(cw / 2, 24, text="（填写节点后自动预览）",
                           fill="#555555", font=("Microsoft YaHei UI", 9))
        return

    times = [p[1] for p in points]
    min_t, max_t = min(times), max(times)
    t_range = (max_t - min_t) if max_t != min_t else 1

    top_pad, bottom_pad = 30.0, 26.0
    def transform(x_val, t_val):
        cx = base_x(x_val)
        usable = max(ch - top_pad - bottom_pad, 1)
        cy = (ch - bottom_pad) - ((t_val - min_t) / t_range) * usable
        return cx, cy

    # 轨迹
    prev = None
    for x_val, t_val in points:
        cur = transform(x_val, t_val)
        if prev is not None:
            canvas.create_line(prev[0], prev[1], cur[0], cur[1],
                               fill="#FF5722", width=2)
        prev = cur

    # 节点方块 + 序号
    marks = nodes_xy if nodes_xy else [points[0], points[-1]]
    font = ("Microsoft YaHei UI", 8, "bold")
    for idx, (x_val, t_val) in enumerate(marks):
        cx, cy = transform(x_val, t_val)
        canvas.create_rectangle(cx - 4, cy - 4, cx + 4, cy + 4,
                                fill=GREEN, outline="white")
        canvas.create_text(cx, cy - 12, text=str(idx + 1), fill="#cfcfcf", font=font)

    # 刻度信息
    canvas.create_text(6, 8, anchor="nw", fill="#666666",
                       font=("Microsoft YaHei UI", 8),
                       text=f"t {min_t} → {max_t}")


# ==================== 主界面 ====================

class App:
    def __init__(self, root):
        self.root = root
        self.nodes = [NodeState(), NodeState()]     # 默认 2 个空节点
        self.chart_path = None                      # 当前谱面文件绝对路径
        self.last_points = None
        self.last_nodes_xy = None
        self._resize_job = None
        self._last_written = None                   # 防止重复写入同一份 Slide

        root.title("Malody Slide 生成器 v1.2")
        root.configure(bg=BG)
        root.geometry("1020x780")
        root.minsize(880, 620)

        self._build_vars()
        self._build_menu()
        self._build_layout()

        self.rebuild_node_list()
        self.schedule_preview()
        self.set_status("就绪。请先选择谱面文件，再填写节点。")

    # ---------- 顶部参数 ----------
    def _build_vars(self):
        self.var_density = tk.StringVar(value="8")
        self.var_width = tk.StringVar(value="256")
        self.var_amplitude = tk.StringVar(value="")

    # ---------- 菜单栏 ----------
    def _build_menu(self):
        menubar = tk.Menu(self.root)

        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="打开谱面文件…", accelerator="Ctrl+O",
                           command=self.pick_chart_file)
        m_file.add_separator()
        m_file.add_command(label="退出", command=self.root.destroy)
        menubar.add_cascade(label="文件", menu=m_file)

        m_node = tk.Menu(menubar, tearoff=0)
        m_node.add_command(label="添加节点", accelerator="Ctrl+N", command=self.add_node)
        m_node.add_separator()
        m_node.add_command(label="全部勾选锯齿", command=lambda: self.set_all_serrated(True))
        m_node.add_command(label="全部不选锯齿", command=lambda: self.set_all_serrated(False))
        menubar.add_cascade(label="节点", menu=m_node)

        m_gen = tk.Menu(menubar, tearoff=0)
        m_gen.add_command(label="生成并写入谱面", accelerator="Ctrl+Enter",
                          command=self.generate)
        m_gen.add_command(label="仅预览（不写入）",
                          command=lambda: self.generate(write=False))
        menubar.add_cascade(label="生成", menu=m_gen)

        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="关于", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=m_help)

        self.root.config(menu=menubar)
        self.root.bind("<Control-o>", lambda e: self.pick_chart_file())
        self.root.bind("<Control-n>", lambda e: self.add_node())
        self.root.bind("<Control-Return>", lambda e: self.generate())

    # ---------- 界面骨架 ----------
    def _build_layout(self):
        # ---- 底部状态栏（先 pack，保证始终可见）----
        self.var_status = tk.StringVar(value="")
        self.lbl_status = tk.Label(self.root, textvariable=self.var_status, anchor="w",
                                   bg="#111111", fg=MUTED, padx=12, pady=6)
        self.lbl_status.pack(side="bottom", fill="x")

        body = tk.Frame(self.root, bg=BG)
        body.pack(side="top", fill="both", expand=True, padx=10, pady=(10, 4))

        # ---- 左侧：参数 + 节点列表 ----
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=False)

        # 文件选择卡片
        card_file = tk.LabelFrame(left, text=" 谱面文件 ", bg=BG, fg=FG,
                                  font=("Microsoft YaHei UI", 9, "bold"),
                                  padx=10, pady=8, bd=1, relief="groove")
        card_file.pack(fill="x", pady=(0, 8))

        self.var_file = tk.StringVar(value="未选择文件")
        tk.Label(card_file, textvariable=self.var_file, bg=BG, fg=MUTED, anchor="w",
                 justify="left", wraplength=380,
                 font=("Microsoft YaHei UI", 9)).pack(fill="x", pady=(0, 6))

        row_btns = tk.Frame(card_file, bg=BG)
        row_btns.pack(fill="x")
        tk.Button(row_btns, text="📂 选择谱面文件", command=self.pick_chart_file,
                  bg=ACCENT, fg="white", activebackground="#1976D2", activeforeground="white",
                  font=("Microsoft YaHei UI", 9, "bold"), padx=10, pady=3,
                  relief="flat", cursor="hand2").pack(side="left")
        tk.Button(row_btns, text="清除", command=self.clear_chart_file,
                  bg="#444444", fg="white", activebackground="#555555", activeforeground="white",
                  font=("Microsoft YaHei UI", 9), padx=10, pady=3,
                  relief="flat", cursor="hand2").pack(side="left", padx=6)

        # 其他参数卡片
        card_par = tk.LabelFrame(left, text=" 其他参数 ", bg=BG, fg=FG,
                                 font=("Microsoft YaHei UI", 9, "bold"),
                                 padx=10, pady=8, bd=1, relief="groove")
        card_par.pack(fill="x", pady=(0, 8))

        grid = tk.Frame(card_par, bg=BG)
        grid.pack(fill="x")
        for r, (label, var) in enumerate((
            ("节点密度", self.var_density),
            ("宽度 w", self.var_width),
            ("锯齿幅度", self.var_amplitude),
        )):
            tk.Label(grid, text=label, bg=BG, fg=FG, width=9, anchor="e",
                     font=("Microsoft YaHei UI", 9)).grid(row=r, column=0, sticky="e", pady=3)
            ent = tk.Entry(grid, textvariable=var, width=16, bg="#3a3a3a", fg=FG,
                           insertbackground=FG, relief="flat", bd=0, highlightthickness=4,
                           highlightbackground=BG, highlightcolor=ACCENT,
                           font=("Microsoft YaHei UI", 9))
            ent.grid(row=r, column=1, sticky="w", padx=(6, 0), pady=3)
            if label == "锯齿幅度":
                ent.configure(validate="key",
                              validatecommand=(self.root.register(self._validate_amp), "%P"))
                self.ent_amplitude = ent

        tk.Label(card_par, justify="left", wraplength=380, bg=BG, fg=MUTED,
                 font=("Microsoft YaHei UI", 8),
                 text=("锯齿幅度为所有锯齿段共用，只有勾选了锯齿才需要填写。\n"
                       "形状：直线 / 先快后慢 / 先慢后快 / S 形。")
                 ).pack(fill="x", pady=(6, 0))

        # 节点列表卡片（可滚动）
        card_nodes = tk.LabelFrame(left, text=" 节点（2–15 个，可增删） ", bg=BG, fg=FG,
                                   font=("Microsoft YaHei UI", 9, "bold"),
                                   padx=6, pady=6, bd=1, relief="groove")
        card_nodes.pack(fill="both", expand=True)

        head = tk.Frame(card_nodes, bg=BG)
        head.pack(fill="x", pady=(0, 4))
        self.var_count = tk.StringVar(value="节点 2 / 15")
        tk.Label(head, textvariable=self.var_count, bg=BG, fg=FG,
                 font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")

        wrap_scroll = tk.Frame(card_nodes, bg=BG)
        wrap_scroll.pack(fill="both", expand=True)

        self.canvas_nodes = tk.Canvas(wrap_scroll, bg=BG, highlightthickness=0,
                                      width=400, height=330)
        self.canvas_nodes.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(wrap_scroll, orient="vertical", command=self.canvas_nodes.yview)
        sb.pack(side="right", fill="y")
        self.canvas_nodes.configure(yscrollcommand=sb.set)

        self.frame_nodes = tk.Frame(self.canvas_nodes, bg=BG)
        self._nodes_window = self.canvas_nodes.create_window(
            (0, 0), window=self.frame_nodes, anchor="nw")
        self.frame_nodes.bind(
            "<Configure>",
            lambda e: self.canvas_nodes.configure(scrollregion=self.canvas_nodes.bbox("all")))
        self.canvas_nodes.bind(
            "<Configure>",
            lambda e: self.canvas_nodes.itemconfigure(self._nodes_window, width=e.width))
        self.canvas_nodes.bind("<Enter>", lambda e: self._bind_wheel(True))
        self.canvas_nodes.bind("<Leave>", lambda e: self._bind_wheel(False))

        add_row = tk.Frame(card_nodes, bg=BG)
        add_row.pack(fill="x", pady=(6, 0))
        self.btn_add = tk.Button(add_row, text="＋ 添加节点", command=self.add_node,
                                 bg="#3c3c3c", fg="white", activebackground="#4a4a4a",
                                 activeforeground="white", relief="flat", cursor="hand2",
                                 font=("Microsoft YaHei UI", 9), padx=10, pady=3)
        self.btn_add.pack(side="left")
        tk.Button(add_row, text="全选锯齿", command=lambda: self.set_all_serrated(True),
                  bg="#3c3c3c", fg="white", activebackground="#4a4a4a",
                  activeforeground="white", relief="flat", cursor="hand2",
                  font=("Microsoft YaHei UI", 9), padx=8, pady=3).pack(side="left", padx=6)
        tk.Button(add_row, text="全不选锯齿", command=lambda: self.set_all_serrated(False),
                  bg="#3c3c3c", fg="white", activebackground="#4a4a4a",
                  activeforeground="white", relief="flat", cursor="hand2",
                  font=("Microsoft YaHei UI", 9), padx=8, pady=3).pack(side="left")

        # ---- 右侧：预览 + 生成 ----
        right = tk.Frame(body, bg=BG, bd=0)
        right.pack(side="right", fill="both", expand=True, padx=(12, 0))

        card_prev = tk.LabelFrame(right, text=" 预览 ", bg=BG, fg=FG,
                                  font=("Microsoft YaHei UI", 9, "bold"),
                                  padx=8, pady=8, bd=1, relief="groove")
        card_prev.pack(fill="both", expand=True)

        self.canvas_preview = tk.Canvas(card_prev, bg=CANVAS_BG, highlightthickness=0)
        self.canvas_preview.pack(fill="both", expand=True)
        self.canvas_preview.bind("<Configure>", lambda e: self.schedule_preview(0))

        action = tk.Frame(right, bg=BG)
        action.pack(fill="x", pady=(8, 0))
        tk.Button(action, text="生成 Slide 并写入谱面", command=self.generate,
                  bg=GREEN, fg="white", activebackground="#43A047", activeforeground="white",
                  font=("Microsoft YaHei UI", 11, "bold"), relief="flat",
                  cursor="hand2", padx=16, pady=8).pack(side="left", fill="x", expand=True)
        tk.Button(action, text="仅预览", command=lambda: self.generate(write=False),
                  bg="#555555", fg="white", activebackground="#666666", activeforeground="white",
                  font=("Microsoft YaHei UI", 10), relief="flat",
                  cursor="hand2", padx=14, pady=8).pack(side="left", padx=(8, 0))

    def _validate_amp(self, proposed):
        if proposed in ("", "-", "+"):
            return True
        return _is_int(proposed)

    def _bind_wheel(self, on):
        if on:
            self.root.bind_all("<MouseWheel>", self._on_wheel)
        else:
            self.root.unbind_all("<MouseWheel>")

    def _on_wheel(self, event):
        self.canvas_nodes.yview_scroll(int(-event.delta / 120), "units")

    # ---------- 状态栏 ----------
    def set_status(self, msg, kind=""):
        colors = {"ok": "#8BC34A", "err": "#EF5350", "warn": "#FFB74D"}
        self.lbl_status.configure(fg=colors.get(kind, MUTED))
        self.var_status.set(msg)

    # ---------- 节点列表渲染 ----------
    def rebuild_node_list(self):
        """按 self.nodes 重建整个节点列表（结构变化时调用）。

        输入内容通过 StringVar / BooleanVar 双向绑定，所以重建不会丢数据。
        """
        for child in self.frame_nodes.winfo_children():
            child.destroy()

        n = len(self.nodes)
        for i, nd in enumerate(self.nodes):
            self._build_node_card(i, nd, n)

        self.var_count.set(f"节点 {n} / {MAX_NODES}")
        at_max = n >= MAX_NODES
        self.btn_add.configure(state="disabled" if at_max else "normal",
                               text="已达上限 15 个节点" if at_max else "＋ 添加节点",
                               disabledforeground="#777777")

    def _build_node_card(self, i, nd, n):
        card = tk.Frame(self.frame_nodes, bg=CARD_BG, padx=8, pady=6)
        card.pack(fill="x", pady=3)

        head = tk.Frame(card, bg=CARD_BG)
        head.pack(fill="x")
        tk.Label(head, text=f"节点 {i + 1}", bg=CARD_BG, fg=FG,
                 font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        if n > MIN_NODES:
            tk.Button(head, text="删除", command=lambda k=i: self.remove_node(k),
                      bg="#5a2b2b", fg="#ffd9d9", activebackground="#7a3b3b",
                      activeforeground="white", relief="flat", cursor="hand2",
                      font=("Microsoft YaHei UI", 8), padx=6, pady=0).pack(side="right")

        fields = tk.Frame(card, bg=CARD_BG)
        fields.pack(fill="x", pady=(4, 0))
        tk.Label(fields, text="时间", bg=CARD_BG, fg=MUTED,
                 font=("Microsoft YaHei UI", 8)).pack(side="left")
        tk.Entry(fields, textvariable=nd.var_t, width=11, bg="#3a3a3a", fg=FG,
                 insertbackground=FG, relief="flat", bd=0, borderwidth=0,
                 highlightthickness=4,
                 highlightbackground=CARD_BG, highlightcolor=ACCENT,
                 font=("Consolas", 9)).pack(side="left", padx=(4, 10))
        tk.Label(fields, text="位置", bg=CARD_BG, fg=MUTED,
                 font=("Microsoft YaHei UI", 8)).pack(side="left")
        tk.Entry(fields, textvariable=nd.var_x, width=7, bg="#3a3a3a", fg=FG,
                 insertbackground=FG, relief="flat", bd=0, borderwidth=0,
                 highlightthickness=4,
                 highlightbackground=CARD_BG, highlightcolor=ACCENT,
                 font=("Consolas", 9)).pack(side="left", padx=4)

        # 段：节点 i → i+1（最后一行没有）
        if i < n - 1:
            seg = tk.Frame(card, bg=CARD_BG)
            seg.pack(fill="x", pady=(4, 0))
            tk.Label(seg, text=f"↳ 到节点{i + 2}", bg=CARD_BG, fg=MUTED,
                     font=("Microsoft YaHei UI", 8)).pack(side="left")
            opt = tk.OptionMenu(seg, nd.var_shape, *[v for _, v in SHAPES])
            opt.configure(bg="#3a3a3a", fg=FG, activebackground="#4a4a4a",
                          activeforeground="white", relief="flat", bd=0,
                          highlightthickness=0,
                          font=("Microsoft YaHei UI", 8), width=7, anchor="w")
            opt["menu"].configure(bg="#3a3a3a", fg=FG, activebackground=ACCENT,
                                  activeforeground="white", font=("Microsoft YaHei UI", 8))
            opt.pack(side="left", padx=(6, 10))

            cb = tk.Checkbutton(seg, text="锯齿", variable=nd.var_serrated, bg=CARD_BG,
                                fg=FG, selectcolor="#3a3a3a", activebackground=CARD_BG,
                                activeforeground=FG, font=("Microsoft YaHei UI", 8),
                                relief="flat", bd=0, highlightthickness=0,
                                command=self.schedule_preview, cursor="hand2")
            cb.pack(side="left")

        # 末节点补一条分隔线，视觉上分组
        if i < n - 1:
            tk.Frame(self.frame_nodes, bg="#3a3a3a", height=1).pack(fill="x")

    def add_node(self):
        if len(self.nodes) >= MAX_NODES:
            return
        self.nodes.append(NodeState())
        self.rebuild_node_list()
        self._scroll_nodes_to_bottom()
        self.schedule_preview()

    def remove_node(self, k):
        if len(self.nodes) <= MIN_NODES:
            return
        del self.nodes[k]
        self.rebuild_node_list()
        self.schedule_preview()

    def set_all_serrated(self, value):
        for nd in self.nodes:
            nd.var_serrated.set(bool(value))
        self.schedule_preview()

    def _scroll_nodes_to_bottom(self):
        self.canvas_nodes.update_idletasks()
        self.canvas_nodes.yview_moveto(1.0)

    # ---------- 文件选择 ----------
    def pick_chart_file(self):
        path = filedialog.askopenfilename(
            title="选择 Malody 谱面文件",
            filetypes=[("Malody 谱面", "*.mc"), ("所有文件", "*.*")],
        )
        if not path:
            self.set_status("已取消文件选择。")
            return
        self.chart_path = os.path.abspath(path)
        self.var_file.set(f"已选择：{os.path.basename(self.chart_path)}\n{self.chart_path}")
        self.set_status("已选择谱面文件：" + os.path.basename(self.chart_path), "ok")
        self._last_written = None

    def clear_chart_file(self):
        self.chart_path = None
        self.var_file.set("未选择文件")
        self.set_status("已清除文件选择（仍可预览，不会写入）。")
        self._last_written = None

    # ---------- 从界面收集参数 ----------
    def _raw_nodes(self):
        out = []
        for nd in self.nodes:
            out.append((nd.var_t.get().strip(), nd.var_x.get().strip()))
        return out

    def collect(self):
        """严格收集 + 校验，用于「生成」。返回 (payload, segs, node_xy)。"""
        raws = self._raw_nodes()

        # 裁掉尾部完全为空的多余节点
        while len(raws) > MIN_NODES and raws[-1] == ("", ""):
            raws.pop()
        if len(raws) < MIN_NODES:
            raise ValueError("请至少填写两个节点。")
        if len(raws) > MAX_NODES:
            raise ValueError(f"节点最多 {MAX_NODES} 个。")

        t_list, x_list = [], []
        for i, (tv, xv) in enumerate(raws):
            if not tv and not xv:
                raise ValueError(f"节点 {i + 1} 未填写（请填写或删除该节点）。")
            if not tv:
                raise ValueError(f"节点 {i + 1} 缺少时间。")
            if not xv:
                raise ValueError(f"节点 {i + 1} 缺少位置。")
            if not _is_int(xv):
                raise ValueError(f"节点 {i + 1} 的位置必须是整数。")
            t_list.append(_parse_time(tv))
            x_list.append(int(xv))

        segs = [{"shape": nd.shape, "serrated": nd.serrated}
                for nd in self.nodes[:len(raws) - 1]]

        density = _as_int(self.var_density.get(), "节点密度")
        if density <= 0:
            raise ValueError("节点密度必须是正整数。")
        w = _as_int(self.var_width.get(), "宽度")

        amplitude = "0"
        if any(s["serrated"] for s in segs):
            amp = self.var_amplitude.get().strip()
            if amp == "":
                raise ValueError("有分段开启了锯齿，请填写锯齿幅度。")
            if not _is_int(amp):
                raise ValueError("锯齿幅度必须是整数（可正可负可为 0）。")
            amplitude = amp

        payload = {
            "w": w,
            "density": density,
            "nodes": [{"t": t, "x": x} for t, x in zip(t_list, x_list)],
            "segs": segs,
            "amplitude": amplitude,
        }
        node_xy = list(zip(x_list, [core.timetrans(t) for t in t_list]))
        return payload, segs, node_xy

    def collect_lenient(self):
        """宽松收集，仅用于「自动预览」：能填多少算多少，不弹错误。"""
        raws = self._raw_nodes()
        while len(raws) > MIN_NODES and raws[-1] == ("", ""):
            raws.pop()
        pairs = []
        for tv, xv in raws:
            if not tv or not xv:
                break
            if not _is_int(xv):
                return None
            try:
                t = _parse_time(tv)
            except ValueError:
                return None
            pairs.append((t, int(xv)))
        if len(pairs) < MIN_NODES:
            return None
        try:
            density = _as_int(self.var_density.get(), "节点密度", empty_ok=True, default=8)
            w = _as_int(self.var_width.get(), "宽度", empty_ok=True, default=256)
        except ValueError:
            return None
        if density <= 0:
            return None

        segs = [{"shape": nd.shape, "serrated": nd.serrated}
                for nd in self.nodes[:len(pairs) - 1]]
        amp = self.var_amplitude.get().strip()
        amplitude = int(amp) if _is_int(amp) else 0
        return {
            "w": w,
            "density": density,
            "t_list": [p[0] for p in pairs],
            "x_list": [p[1] for p in pairs],
            "segs": segs,
            "amplitude": amplitude,
        }

    # ---------- 预览调度 ----------
    def schedule_preview(self, delay=250):
        if self._resize_job is not None:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.root.after(delay, self.update_preview)

    def update_preview(self):
        self._resize_job = None
        data = self.collect_lenient()
        if data is None:
            self.last_points = None
            self.last_nodes_xy = None
            draw_preview(self.canvas_preview, None)
            return
        try:
            _, points = core.drawslide(
                data["w"], data["density"], data["x_list"], data["t_list"],
                [s["shape"] for s in data["segs"]], data["amplitude"],
                [s["serrated"] for s in data["segs"]],
            )
        except ValueError:
            return
        self.last_points = points
        self.last_nodes_xy = list(zip(data["x_list"],
                                     [core.timetrans(t) for t in data["t_list"]]))
        draw_preview(self.canvas_preview, points, self.last_nodes_xy)

    # ---------- 生成 / 写入 ----------
    def generate(self, write=True):
        self.set_status("")
        try:
            payload, segs, node_xy = self.collect()
        except ValueError as e:
            self.set_status("错误：" + str(e), "err")
            messagebox.showerror("参数有误", str(e))
            return

        chain = [payload["nodes"][0]["t"]] + [s["shape"] for s in segs]
        print("\n===== 生成的 Slide 参数 =====")
        print(json.dumps({**payload, "segments": len(segs)}, ensure_ascii=False))
        print("=============================\n")

        try:
            slide_text, points = core.drawslide(
                payload["w"], payload["density"],
                [n["x"] for n in payload["nodes"]],
                [n["t"] for n in payload["nodes"]],
                [s["shape"] for s in segs],
                int(payload["amplitude"]),
                [s["serrated"] for s in segs],
            )
        except ValueError as e:
            self.set_status("错误：" + str(e), "err")
            messagebox.showerror("生成失败", str(e))
            return

        self.last_points = points
        self.last_nodes_xy = node_xy
        draw_preview(self.canvas_preview, points, node_xy)

        print("===== 生成的 Slide 文本 =====")
        print(slide_text)
        print("=============================\n")

        if not write:
            self.set_status("预览已刷新（未写入文件）。", "ok")
            return

        if not self.chart_path:
            self.set_status("预览已刷新。未选择谱面文件，因此没有写入。", "warn")
            messagebox.showinfo(
                "仅预览",
                "预览已刷新。\n\n你还没有选择谱面文件，所以没有写入。\n"
                "点左上角「📂 选择谱面文件」即可选择 .mc 文件。",
            )
            return

        try:
            bak_path, inserted = self.write_to_mc(self.chart_path, slide_text)
        except Exception as e:
            self.set_status("写入失败：" + str(e), "err")
            messagebox.showerror("写入失败", str(e))
            return

        self._last_written = slide_text
        msg = (f"已成功写入谱面！\n\n文件：{self.chart_path}\n"
               f"备份：{bak_path}\n新增节点数：{inserted}")
        self.set_status(f"已写入 {os.path.basename(self.chart_path)}（备份 {os.path.basename(bak_path)}，新增 {inserted} 个节点）", "ok")
        messagebox.showinfo("成功", msg)

    def write_to_mc(self, path, slide_text):
        """把 Slide 文本插入谱面的 "note":[ 之后，写回原文件（先备份）。"""
        if not os.path.isfile(path):
            raise FileNotFoundError(f"找不到谱面文件：\n{path}")
        if not path.lower().endswith(".mc"):
            raise ValueError("必须是 .mc 格式的谱面文件。")

        with open(path, "r", encoding="utf-8", newline="") as f:
            content = f.read()

        marker = '"note":['
        if marker not in content:
            raise ValueError('未在谱面文件中找到 "note":[ 标记，这不是有效的 Malody 谱面？')

        new_content = content.replace(marker, marker + slide_text + ",", 1)
        if new_content == content:
            raise ValueError("写入内容没有变化，已中止以免损坏文件。")

        # 备份：.bak 已存在时依次用 .bak.1 / .bak.2 …，绝不覆盖旧备份
        bak_path = self._unique_backup_path(path)
        shutil.copyfile(path, bak_path)

        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new_content)

        return bak_path, slide_text.count('"beat"')

    @staticmethod
    def _unique_backup_path(path):
        base = path + ".bak"
        if not os.path.exists(base):
            return base
        n = 1
        while True:
            cand = f"{base}.{n}"
            if not os.path.exists(cand):
                return cand
            n += 1

    # ---------- 关于 ----------
    def show_about(self):
        messagebox.showinfo(
            "关于",
            "Malody Slide 生成器 —— 桌面版 v1.2\n\n"
            "· 节点 2–15 个，可动态增删\n"
            "· 锯齿按段独立开关，幅度各段共用\n"
            "· 预览反映锯齿并标注节点序号\n"
            "· 原生文件选择，写回前自动 .bak 备份\n\n"
            "算法核心与安卓版共用同一份源码：\n"
            f"{os.path.relpath(CORE_PATH, _THIS_DIR)}",
        )


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
