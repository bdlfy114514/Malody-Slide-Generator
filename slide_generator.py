import tkinter as tk
from tkinter import messagebox
import ast
import math
import json
import os
import shutil

# ==================== 时间转换算法 ====================

def timetrans(t0):
    a, b, c = t0[0], t0[1], t0[2]
    if c == 0:
        raise ValueError("节拍细分数 c 不能为 0")
    t = math.floor(a * 96 + b * (96 / c))
    return t

def transtime_rev(t0):
    a = t0 // 96
    b = t0 % 96
    c = 96
    return f"[{a},{b},{c}]"

# ==================== 核心 Slide 生成算法 ====================

def drawslide(w, density, x, t, type_tuple):
    abs_t = [timetrans(node_t) for node_t in t]
    start_abs_time = abs_t[0]
    start_abs_x = x[0]
    
    slide_data = {
        "beat": t[0],
        "x": start_abs_x,
        "w": w,
        "seg": []
    }
    
    step = 96.0 / density
    
    # 额外记录一个用于绘图的绝对坐标列表 [(x1, t1), (x2, t2), ...]
    plot_points = [(start_abs_x, start_abs_time)]
    
    for i in range(len(type_tuple)):
        T1, T2 = abs_t[i], abs_t[i+1]
        X1, X2 = x[i], x[i+1]
        shape = type_tuple[i]
        
        current_t = T1 + step
        
        while True:
            if current_t >= T2 or math.isclose(current_t, T2, abs_tol=1e-5):
                current_t = T2
            
            k = (current_t - T1) / (T2 - T1)
            
            if shape == 's':
                curr_x = X1 + (X2 - X1) * k
            elif shape == 'si':
                curr_x = X1 + (X2 - X1) * math.sin(k * math.pi / 2)
            elif shape == 'so':
                curr_x = X1 + (X2 - X1) * (1 - math.cos(k * math.pi / 2))
            elif shape == 'b':
                curr_x = X1 + (X2 - X1) * ((1 - math.cos(k * math.pi)) / 2)
            else:
                curr_x = X1
                
            rel_time_int = math.floor(current_t) - start_abs_time
            rel_x_int = math.floor(curr_x) - start_abs_x
            
            slide_data["seg"].append({
                "beat": ast.literal_eval(transtime_rev(rel_time_int)),
                "x": rel_x_int
            })
            
            plot_points.append((math.floor(curr_x), math.floor(current_t)))
            
            if current_t == T2:
                break
                
            current_t += step
            
    slide_text = json.dumps(slide_data, separators=(',', ':'))
    return slide_text, plot_points

# ==================== 绘图预览逻辑 ====================

def update_preview(plot_points, w):
    """
    在 Canvas 上绘制 Slide 轨迹
    """
    canvas.delete("all")  # 清空画布
    
    if not plot_points:
        return
        
    times = [p[1] for p in plot_points]
    min_t, max_t = min(times), max(times)
    t_range = max_t - min_t if max_t != min_t else 1
    
    canvas_w = 200
    canvas_h = 400
    
    # 转换坐标系函数 (上下翻转 Y 轴)
    def transform(x_val, t_val):
        # X 映射: 0->20, 256->180
        cx = 20 + (x_val / 256.0) * (canvas_w - 40)
        # Y 映射翻转: min_t 对应底部 370，max_t 对应顶部 30 (实现下底上顶)
        cy = 370 - ((t_val - min_t) / t_range) * (canvas_h - 60)
        return cx, cy

    # 1. 绘制主体折线
    for i in range(len(plot_points) - 1):
        x1, t1 = plot_points[i]
        x2, t2 = plot_points[i+1]
        
        cx1, cy1 = transform(x1, t1)
        cx2, cy2 = transform(x2, t2)
        
        canvas.create_line(cx1, cy1, cx2, cy2, fill="#FF5722", width=3)
        
    # 2. 标出关键控制点（绿色方块）
    for x_val, t_val in [plot_points[0], plot_points[-1]]:
        cx, cy = transform(x_val, t_val)
        canvas.create_rectangle(cx-4, cy-4, cx+4, cy+4, fill="#4CAF50", outline="white")

# ==================== 文件写入逻辑 ====================

def write_to_mc(file_path, slide_text):
    file_path = file_path.strip().strip("'").strip('"')
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到谱面文件：\n{file_path}")
    if not file_path.endswith('.mc'):
        raise ValueError("必须是 .mc 格式文件。")

    bak_path = file_path + ".bak"
    shutil.copyfile(file_path, bak_path)

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    target_marker = '"note":['
    if target_marker not in content:
        raise ValueError("未在谱面文件中找到 '\"note\":[' 标记。")

    new_content = content.replace(target_marker, target_marker + slide_text + ",", 1)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

# ==========================================================

def generate_data():
    try:
        t_list = []
        x_list = []
        
        for i in range(5):
            t_val = t_entries[i].get().strip()
            x_val = x_entries[i].get().strip()
            if not t_val and not x_val: continue
            if (t_val and not x_val) or (not t_val and x_val):
                raise ValueError(f"节点 {i+1} 信息不完整。")
            
            val_list = ast.literal_eval(t_val)
            val_int = int(x_val)
            t_list.append(val_list)
            x_list.append(val_int)
        
        node_count = len(t_list)
        if node_count < 2: raise ValueError("请至少完整填写两个节点。")
            
        type_list = []
        for i in range(4):
            type_val = type_entries[i].get().strip()
            if type_val: type_list.append(type_val)
                
        if len(type_list) != (node_count - 1):
            raise ValueError(f"形状数量不匹配，应为 {node_count - 1} 个。")

        density = int(density_entry.get().strip())
        w = int(w_entry.get().strip())

        slide_result, plot_points = drawslide(w, density, x_list, t_list, type_list)

        # 刷新画布预览
        update_preview(plot_points, w)

        path_input = path_entry.get().strip()
        if path_input:
            write_to_mc(path_input, slide_result)
            messagebox.showinfo("成功", "Slide 已生成并成功写入谱面！")
        else:
            messagebox.showinfo("成功", "预览刷新成功！（未填写路径，未写入文件）")

    except Exception as e:
        messagebox.showerror("错误", str(e))

# ==================== GUI 布局 ====================

root = tk.Tk()
root.title("slide生成器")
root.geometry("800x540")

# 左侧：参数输入面板
left_frame = tk.Frame(root)
left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=10, pady=10)

tk.Label(left_frame, text="谱面文件路径 (.mc, 选填):", font=('Arial', 10, 'bold')).grid(row=0, column=0, padx=5, pady=5, sticky="e")
path_entry = tk.Entry(left_frame, width=35)
path_entry.grid(row=0, column=1, columnspan=3, padx=5, pady=5, sticky="w")

tk.Label(left_frame, text="五个节点信息 (选填，至少2个):", font=('Arial', 10, 'bold')).grid(row=1, column=0, columnspan=4, pady=10, sticky="w")

t_entries = []
x_entries = []
for i in range(5):
    tk.Label(left_frame, text=f"节点 {i+1} 时间:").grid(row=i+2, column=0, padx=5, pady=5, sticky="e")
    t_entry = tk.Entry(left_frame, width=12)
    t_entry.grid(row=i+2, column=1, padx=2, pady=5)
    t_entries.append(t_entry)
    
    tk.Label(left_frame, text="位置:").grid(row=i+2, column=2, padx=2, pady=5, sticky="e")
    x_entry = tk.Entry(left_frame, width=8)
    x_entry.grid(row=i+2, column=3, padx=5, pady=5)
    x_entries.append(x_entry)

tk.Label(left_frame, text="其他参数设置:", font=('Arial', 11, 'bold')).grid(row=7, column=0, columnspan=3, pady=10, sticky="w")

tk.Label(left_frame, text="节点密度:").grid(row=8, column=0, padx=5, pady=5, sticky="e")
density_entry = tk.Entry(left_frame, width=12)
density_entry.grid(row=8, column=1, sticky="w")

tk.Label(left_frame, text="宽度:").grid(row=9, column=0, padx=5, pady=5, sticky="e")
w_entry = tk.Entry(left_frame, width=12)
w_entry.grid(row=9, column=1, sticky="w")

tk.Label(left_frame, text="形状 (s/si/so/b):").grid(row=10, column=0, padx=5, pady=5, sticky="e")
type_frame = tk.Frame(left_frame)
type_frame.grid(row=10, column=1, columnspan=3, sticky="w")
type_entries = []
for i in range(4):
    te = tk.Entry(type_frame, width=4)
    te.pack(side=tk.LEFT, padx=3)
    type_entries.append(te)

btn_generate = tk.Button(left_frame, text="生成并预览", command=generate_data, bg="#4CAF50", fg="white", font=('Arial', 10, 'bold'))
btn_generate.grid(row=11, column=0, columnspan=4, pady=20)

# 右侧：预览面板
right_frame = tk.Frame(root, bd=2, relief=tk.SUNKEN, bg="#212121")
right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=15, pady=15)

# 标题更名为“预览”
tk.Label(right_frame, text="预览", bg="#212121", fg="white", font=('Arial', 11, 'bold')).pack(pady=5)

canvas = tk.Canvas(right_frame, width=200, height=410, bg="#121212", highlightthickness=0)
canvas.pack(padx=10, pady=5, expand=True)

canvas.create_line(20, 0, 20, 410, fill="#333333", dash=(4, 4))
canvas.create_line(180, 0, 180, 410, fill="#333333", dash=(4, 4))

root.mainloop()