import ast
import math
import json

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

VALID_SHAPES = ('s', 'si', 'so', 'b')

def _shape_x(shape, X1, X2, k):
    """按缓动形状求 k(0..1) 处的 X 坐标"""
    if shape == 's':      # Straight 直线
        return X1 + (X2 - X1) * k
    if shape == 'si':     # Sine In 先快后慢
        return X1 + (X2 - X1) * math.sin(k * math.pi / 2)
    if shape == 'so':     # Sine Out 先慢后快
        return X1 + (X2 - X1) * (1 - math.cos(k * math.pi / 2))
    if shape == 'b':      # Bezier 慢-快-慢
        return X1 + (X2 - X1) * ((1 - math.cos(k * math.pi)) / 2)
    raise ValueError(f"未知的形状类型：{shape}（应为 s / si / so / b）")

def drawslide(w, density, x, t, type_tuple, amplitude=0, serrated=None):
    """
    根据节点和形状生成 Malody Slide 文本。

    type_tuple : 每一「段」的形状简写序列，长度 = 节点数 - 1
    amplitude  : 锯齿幅度（所有锯齿段共用）
    serrated   : 布尔列表，与 type_tuple 等长，标记「每一段」是否加锯齿；
                 锯齿段内部每隔一个 seg 抬高 amplitude（每段独立计数）。
    """
    abs_t = [timetrans(node_t) for node_t in t]
    start_abs_time = abs_t[0]
    start_abs_x = x[0]

    n_seg = len(type_tuple)
    if serrated is None:
        serrated = [False] * n_seg
    if len(serrated) != n_seg:
        raise ValueError("锯齿标记数量与形状数量不一致")

    slide_data = {
        "beat": t[0],
        "x": start_abs_x,
        "w": w,
        "seg": []
    }

    step = 96.0 / density
    meta = []  # 每个 seg 记录 (所属段序号, 段内序号)

    for i in range(n_seg):
        T1, T2 = abs_t[i], abs_t[i + 1]
        X1, X2 = x[i], x[i + 1]
        shape = type_tuple[i]

        current_t = T1 + step
        local = 0
        while True:
            if current_t >= T2 or math.isclose(current_t, T2, abs_tol=1e-5):
                current_t = T2

            k = (current_t - T1) / (T2 - T1)
            curr_x = _shape_x(shape, X1, X2, k)

            rel_time_int = math.floor(current_t) - start_abs_time
            rel_x_int = math.floor(curr_x) - start_abs_x

            slide_data["seg"].append({
                "beat": ast.literal_eval(transtime_rev(rel_time_int)),
                "x": rel_x_int
            })
            meta.append((i, local))
            local += 1

            if current_t == T2:
                break
            current_t += step

    # 分段锯齿：只对标记为锯齿的段生效，段内偶数序号的 seg 抬高 amplitude
    if any(serrated):
        for idx, (seg_i, local_i) in enumerate(meta):
            if serrated[seg_i] and local_i % 2 == 0:
                slide_data["seg"][idx]["x"] += amplitude

    slide_text = json.dumps(slide_data, separators=(',', ':'))

    # 预览点：由最终 seg 反推绝对坐标，因此预览也能反映锯齿效果
    plot_points = [(start_abs_x, start_abs_time)]
    for seg in slide_data["seg"]:
        plot_points.append((start_abs_x + seg["x"], start_abs_time + timetrans(seg["beat"])))

    return slide_text, plot_points

# ==================== Android (Chaquopy) 桥接层 ====================
# 说明：文件读取/写入（SAF 内容 URI、生成 .bak 备份）由 Kotlin 侧完成，
# 这里只负责纯粹的参数校验与算法计算。

def generate(params_json):
    """
    接收 UI 传来的 JSON 参数，返回 JSON 结果。
    输入示例:
      {"w":256,"density":8,
       "nodes":[{"t":[4,1,4],"x":0},{"t":[8,0,1],"x":128}, ...],
       "segs":[{"shape":"s","serrated":false}, ...],   # 长度 = 节点数-1
       "amplitude":"6"}
    输出(成功): {"ok":true,"slide":"{...}","points":[[x,t],...]}
    输出(失败): {"ok":false,"error":"..."}
    """
    try:
        p = json.loads(params_json)

        # 节点时间与位置
        t_list = []
        x_list = []
        for node in p["nodes"]:
            tv = node["t"]
            if isinstance(tv, str):
                tv = ast.literal_eval(tv)
            t_list.append([int(tv[0]), int(tv[1]), int(tv[2])])
            x_list.append(int(node["x"]))

        if len(t_list) < 2:
            raise ValueError("请至少填写两个节点。")
        if len(t_list) > 15:
            raise ValueError("节点最多 15 个。")

        # 每一段的形状与锯齿标记
        segs = p["segs"]
        if len(segs) != len(t_list) - 1:
            raise ValueError(f"分段数量不匹配，应为 {len(t_list) - 1} 段。")
        type_list = [str(s["shape"]) for s in segs]
        serrated = [bool(s.get("serrated", False)) for s in segs]

        density = int(p["density"])
        w = int(p["w"])

        amplitude = 0
        if any(serrated):
            amp_str = str(p.get("amplitude", "")).strip()
            if amp_str == "":
                raise ValueError("有分段开启了锯齿，请填写锯齿幅度。")
            amplitude = int(amp_str)

        slide_text, plot_points = drawslide(
            w, density, x_list, t_list, type_list, amplitude, serrated
        )

        points = [[int(a), int(b)] for (a, b) in plot_points]
        return json.dumps({"ok": True, "slide": slide_text, "points": points})
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})
