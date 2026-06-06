"""
ui_skybox.py — AutoToon Studio Skybox Version 2.1
Material preview + Multiple Skybox + Multi-shape + Camera + Style presets + Screenshot + UE5 integration
"""
import os
import time
import json
import numpy as np
import cv2
import dearpygui.dearpygui as dpg

# UE5 客户端
try:
    from ue_client import UE5Client
    ue_client = UE5Client()
except Exception as e:
    ue_client = None
    print(f"[UE5] Client not available: {e}")

# WebSocket 客户端
try:
    from ws_client import UE5WebSocketClient
    ws_client = UE5WebSocketClient()
except Exception as e:
    ws_client = None
    print(f"[WS] WebSocket client not available: {e}")

VIEWER_SIZE = 400

# 全局状态
ref_image = None
mask_image = None
engine = None
brush_mode = 0
brush_size = 20
current_skybox = 0
current_shape = "sphere"
auto_rotate = False  # Auto rotation flag
rotation_angle = 0.0  # Current rotation angle (Y axis, for light rotation)
rotation_speed = 30.0  # Degrees per second

# 多形状预览模式
preview_mode = "single"  # "single", "2x2", "1x3"
PREVIEW_MODES = ["single", "2x2", "1x3"]
PREVIEW_MODE_LABELS = {"single": "Single", "2x2": "2x2 Grid", "1x3": "1x3 Row"}

# 摄像机状态
camera_pitch = 0.0  # X axis rotation (degrees)
camera_yaw = 0.0    # Y axis rotation (degrees)
camera_roll = 0.0   # Z axis rotation (degrees)
camera_distance = 1.0  # Zoom level (1.0 = normal)
camera_pan_x = 0.0  # Pan offset X
camera_pan_y = 0.0  # Pan offset Y

# 鼠标状态
mouse_dragging = False
mouse_button = -1
last_mouse_x = 0
last_mouse_y = 0

# 预计算数据缓存
_sphere_data = None
_cube_data = None
_cylinder_data = None
_torus_data = None
_cone_data = None
_icosahedron_data = None
_skybox_cache = {}


material = {
    "shadow_r": 0.35, "shadow_g": 0.35, "shadow_b": 0.4,
    "specular": 0.6, "rim": 0.5, "outline": 2.0, "levels": 3,
    "sss": 0.3,        # Subsurface scattering intensity
    "aniso": 0.2,      # Anisotropic specular
    "metallic": 0.0,   # Metallic factor
    "roughness": 0.5,  # Roughness factor
}

# 形状列表
SHAPE_NAMES = ["sphere", "cube", "cylinder", "torus", "cone", "icosa"]
SHAPE_LABELS = {
    "sphere": "Sphere",
    "cube": "Cube",
    "cylinder": "Cylinder",
    "torus": "Torus",
    "cone": "Cone",
    "icosa": "Icosa"
}

# 对比视图状态
compare_mode = False  # 是否显示对比视图
compare_shape_a = "sphere"
compare_shape_b = "cube"

# 实时联动状态
realtime_sync = False  # 实时联动开关
_updating_from_ue5 = False  # 防止循环触发标志
ws_latency = 0  # WebSocket 延迟 (ms)


# =============================================================================
# Skybox 预设 - 工业级渲染背景
# =============================================================================

# 自定义 Skybox 图片路径
custom_skybox_path = None
custom_skybox_image = None

SKYBOX_PRESETS = [
    {"name": "Studio Gray", "desc": "Neutral gray - Standard studio"},
    {"name": "Warm Sunset", "desc": "Warm sunset - Cinematic"},
    {"name": "Cool Dawn", "desc": "Cool dawn - Morning vibe"},
    {"name": "HDR White", "desc": "White HDR - Product display"},
    {"name": "Dark Studio", "desc": "Dark studio - Highlight material"},
    {"name": "Gradient Blue", "desc": "Blue gradient - Tech feel"},
    {"name": "Gradient Orange", "desc": "Orange gradient - Warm vibe"},
    {"name": "Checkerboard", "desc": "Checkerboard - Alpha test"},
    {"name": "Custom Image", "desc": "Load custom image as skybox"},
]


def on_custom_skybox_select(sender, app_data):
    """加载自定义 Skybox 图片"""
    global custom_skybox_path, custom_skybox_image, current_skybox

    path = app_data.get("file_path_name", "") if isinstance(app_data, dict) else ""
    if not path:
        return

    img = cv2.imread(path)
    if img is None:
        print(f"[Skybox] Failed to load: {path}")
        return

    custom_skybox_path = path
    custom_skybox_image = img.astype(np.float32) / 255.0
    current_skybox = 8  # Custom Image index

    dpg.set_value("skybox_name", f"Custom: {os.path.basename(path)}")
    dpg.set_value("skybox_combo", "Custom Image")
    update_shape()
    print(f"[Skybox] Loaded custom: {path}")


def generate_skybox(preset_idx, size=400):
    """生成 Skybox 背景图像 - 更明显的差异"""
    global custom_skybox_image

    # 自定义图片
    if preset_idx == 8:
        if custom_skybox_image is not None:
            # 调整大小并返回
            img = cv2.resize(custom_skybox_image, (size, size))
            # 如果是 RGB，转换为 BGR
            if len(img.shape) == 2:
                img = np.stack([img, img, img], axis=-1)
            return img.astype(np.float32)
        else:
            # 没有自定义图片时返回灰色
            img = np.zeros((size, size, 3), dtype=np.float32)
            img[:] = [0.2, 0.2, 0.22]
            return img

    if preset_idx in _skybox_cache and _skybox_cache[preset_idx].shape[0] == size:
        return _skybox_cache[preset_idx]

    img = np.zeros((size, size, 3), dtype=np.float32)

    if preset_idx == 0:  # Studio Gray
        # 中性灰，微弱顶部渐变
        for y in range(size):
            t = y / size
            img[y, :] = [0.18 - 0.03*t, 0.18 - 0.03*t, 0.20 - 0.02*t]

    elif preset_idx == 1:  # Warm Sunset
        # 橙色到深蓝渐变
        for y in range(size):
            t = y / size
            r = 0.6 * (1-t) + 0.1 * t
            g = 0.35 * (1-t) + 0.08 * t
            b = 0.15 * (1-t) + 0.4 * t
            img[y, :] = [b, g, r]

    elif preset_idx == 2:  # Cool Dawn
        # 深蓝到浅蓝
        for y in range(size):
            t = y / size
            img[y, :] = [0.15 + 0.35*t, 0.18 + 0.25*t, 0.35 + 0.15*t]

    elif preset_idx == 3:  # HDR White
        # 明亮白色，边缘暗化
        img[:] = [0.95, 0.95, 0.98]
        cx, cy = size/2, size/2
        for y in range(size):
            for x in range(size):
                dist = np.sqrt((x-cx)**2 + (y-cy)**2) / (size * 0.8)
                vignette = max(0.6, 1 - dist * 0.4)
                img[y, x] = img[y, x] * vignette

    elif preset_idx == 4:  # Dark Studio
        # 深色背景，底部微光
        img[:] = [0.04, 0.04, 0.05]
        for y in range(size):
            if y > size * 0.8:
                t = (y - size * 0.8) / (size * 0.2)
                img[y, :] = [0.08 + 0.1*t, 0.08 + 0.1*t, 0.10 + 0.08*t]

    elif preset_idx == 5:  # Gradient Blue
        # 蓝色科技感渐变
        for y in range(size):
            t = y / size
            img[y, :] = [0.2 + 0.5*t, 0.3 + 0.4*t, 0.6 + 0.3*t]

    elif preset_idx == 6:  # Gradient Orange
        # 温暖橙色渐变
        for y in range(size):
            t = y / size
            img[y, :] = [0.15 + 0.15*t, 0.25 + 0.35*t, 0.7 - 0.1*t]

    elif preset_idx == 7:  # Checkerboard
        # 棋盘格
        cell_size = size // 10
        for y in range(size):
            for x in range(size):
                cy, cx = y // cell_size, x // cell_size
                if (cy + cx) % 2 == 0:
                    img[y, x] = [0.7, 0.7, 0.75]
                else:
                    img[y, x] = [0.25, 0.25, 0.28]

    _skybox_cache[preset_idx] = img.copy()
    return img


def precompute_sphere(size=400):
    global _sphere_data
    if _sphere_data is not None:
        return _sphere_data
    cx, cy = size // 2, size // 2
    radius = size // 2 - 20
    y_coords, x_coords = np.ogrid[:size, :size]
    dx, dy = x_coords - cx, y_coords - cy
    dist = np.sqrt(dx*dx + dy*dy)
    nx, ny = dx / radius, dy / radius
    nz = np.sqrt(np.maximum(0, 1 - nx*nx - ny*ny))

    # 球体坐标映射到 skybox
    # 使用球面坐标映射
    theta = np.arctan2(ny, nx)  # 水平角度
    phi = np.arcsin(np.clip(nz, -1, 1))  # 垂直角度

    _sphere_data = {
        'nx': nx.astype(np.float32), 'ny': ny, 'nz': nz,
        'mask': dist <= radius, 'outline': (dist > radius-3) & (dist <= radius),
        'theta': theta, 'phi': phi, 'radius': radius,
        'dist': dist
    }
    return _sphere_data


def precompute_cube(size=400):
    """Precompute cube normal data with perspective projection (3 visible faces)"""
    global _cube_data
    if _cube_data is not None:
        return _cube_data

    cx, cy = size // 2, size // 2
    half_size = size // 4  # Smaller to fit all 3 faces

    y_coords, x_coords = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')

    # Create arrays
    nx = np.zeros((size, size), dtype=np.float32)
    ny = np.zeros((size, size), dtype=np.float32)
    nz = np.zeros((size, size), dtype=np.float32)
    mask = np.zeros((size, size), dtype=bool)

    # Perspective cube - show front, top, and right faces
    # Front face (z direction) - center-left area
    front_x0 = cx - half_size - half_size // 2
    front_x1 = cx + half_size - half_size // 2
    front_y0 = cy - half_size + half_size // 2
    front_y1 = cy + half_size + half_size // 2

    front_mask = (x_coords >= front_x0) & (x_coords < front_x1) & \
                 (y_coords >= front_y0) & (y_coords < front_y1)
    mask |= front_mask
    nz[front_mask] = 0.9
    nx[front_mask] = 0.05
    ny[front_mask] = 0.05

    # Top face (y direction) - above front, tilted up
    top_x0 = front_x0 + half_size // 2
    top_x1 = front_x1 + half_size // 2
    top_y0 = front_y0 - half_size
    top_y1 = front_y0

    top_mask = (x_coords >= top_x0) & (x_coords < top_x1) & \
               (y_coords >= top_y0) & (y_coords < top_y1)
    mask |= top_mask
    ny[top_mask] = -0.8
    nz[top_mask] = 0.5
    nx[top_mask] = 0.1

    # Right face (x direction) - right of front
    right_x0 = front_x1
    right_x1 = front_x1 + half_size
    right_y0 = front_y0 + half_size // 2
    right_y1 = front_y1 + half_size // 2

    right_mask = (x_coords >= right_x0) & (x_coords < right_x1) & \
                 (y_coords >= right_y0) & (y_coords < right_y1)
    mask |= right_mask
    nx[right_mask] = 0.8
    nz[right_mask] = 0.5
    ny[right_mask] = 0.1

    # Normalize all normals
    norm = np.sqrt(nx**2 + ny**2 + nz**2)
    norm = np.maximum(norm, 0.01)
    nx = nx / norm
    ny = ny / norm
    nz = nz / norm

    # Calculate outline for each face
    dist = np.zeros((size, size), dtype=np.float32)
    outline_width = 3

    for y in range(size):
        for x in range(size):
            if front_mask[y, x]:
                edge_dists = [x - front_x0, front_x1 - x - 1, y - front_y0, front_y1 - y - 1]
                dist[y, x] = min(edge_dists)
            elif top_mask[y, x]:
                edge_dists = [x - top_x0, top_x1 - x - 1, y - top_y0, top_y1 - y - 1]
                dist[y, x] = min(edge_dists)
            elif right_mask[y, x]:
                edge_dists = [x - right_x0, right_x1 - x - 1, y - right_y0, right_y1 - y - 1]
                dist[y, x] = min(edge_dists)

    outline = (dist > 0) & (dist <= outline_width) & mask

    _cube_data = {
        'nx': nx, 'ny': ny, 'nz': nz,
        'mask': mask, 'outline': outline, 'dist': dist
    }
    return _cube_data


def precompute_cylinder(size=400):
    """Precompute cylinder normal data with perspective (side + top cap visible)"""
    global _cylinder_data
    if _cylinder_data is not None:
        return _cylinder_data

    cx, cy = size // 2, size // 2
    radius = size // 3
    half_height = size // 3

    # Use meshgrid for proper shape
    y_coords, x_coords = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')
    dx = (x_coords - cx).astype(np.float32)
    dy = (y_coords - cy).astype(np.float32)
    dist_xy = np.sqrt(dx*dx + dy*dy)

    nx = np.zeros((size, size), dtype=np.float32)
    ny = np.zeros((size, size), dtype=np.float32)
    nz = np.zeros((size, size), dtype=np.float32)
    mask = np.zeros((size, size), dtype=bool)

    # Cylinder body region (side surface)
    in_radius = dist_xy <= radius
    y_in_range = (dy >= -half_height) & (dy <= half_height - half_height // 4)  # Leave room for top cap
    body_mask = in_radius & y_in_range
    mask |= body_mask

    # Side normals - pointing outward with slight forward tilt
    side_area = body_mask & (dist_xy > 1)
    safe_dist = np.maximum(dist_xy[side_area], 1.0)
    nx[side_area] = dx[side_area] / safe_dist
    ny[side_area] = 0
    nz[side_area] = 0.35  # Forward tilt for better lighting

    # Normalize side normals
    side_norm = np.sqrt(nx[side_area]**2 + ny[side_area]**2 + nz[side_area]**2)
    nx[side_area] = nx[side_area] / np.maximum(side_norm, 0.01)
    nz[side_area] = nz[side_area] / np.maximum(side_norm, 0.01)

    # Top cap - ellipse shape for perspective
    top_center_y = cy - half_height + half_height // 4
    top_height = half_height // 3
    top_mask_region = (dy >= top_center_y - top_height) & (dy <= top_center_y + top_height) & in_radius

    # Only show top cap where it overlaps with cylinder projection
    # Use elliptical shape
    ellipse_mask = (dist_xy <= radius) & \
                   (dy >= top_center_y - top_height * 0.7) & \
                   (dy <= top_center_y + top_height * 0.7)
    mask |= ellipse_mask

    # Top cap normals - pointing up (-Y) with slight forward component
    top_area = ellipse_mask
    ny[top_area] = -0.85
    nz[top_area] = 0.4  # Forward tilt for perspective feel
    nx[top_area] = 0.0

    # Normalize top normals
    top_norm = np.sqrt(nx[top_area]**2 + ny[top_area]**2 + nz[top_area]**2)
    ny[top_area] = ny[top_area] / np.maximum(top_norm, 0.01)
    nz[top_area] = nz[top_area] / np.maximum(top_norm, 0.01)

    # Outline
    outline = (dist_xy > radius - 3) & (dist_xy <= radius) & y_in_range
    top_outline = in_radius & (dy > half_height - 3) & (dy <= half_height)
    bottom_outline = in_radius & (dy >= -half_height) & (dy < -half_height + 3)
    outline |= top_outline | bottom_outline

    _cylinder_data = {
        'nx': nx, 'ny': ny, 'nz': nz,
        'mask': mask, 'outline': outline,
        'dist': dist_xy
    }
    return _cylinder_data


def precompute_torus(size=400):
    """Precompute torus (donut) normal data"""
    global _torus_data
    if _torus_data is not None:
        return _torus_data

    cx, cy = size // 2, size // 2
    major_radius = size // 4  # Distance from center of torus to center of tube
    minor_radius = size // 10  # Radius of the tube

    y_coords, x_coords = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')

    # Distance from center
    dx = x_coords - cx
    dy = y_coords - cy
    dist_from_center = np.sqrt(dx*dx + dy*dy)

    # For each point, calculate distance from the torus ring
    # The torus is defined by points where |dist_from_center - major_radius| = minor_radius
    dist_from_ring = np.abs(dist_from_center - major_radius)

    # Create mask for torus surface (within minor_radius)
    mask = dist_from_ring <= minor_radius

    # Calculate normals
    nx = np.zeros((size, size), dtype=np.float32)
    ny = np.zeros((size, size), dtype=np.float32)
    nz = np.zeros((size, size), dtype=np.float32)

    # Points inside the torus tube
    tube_area = mask & (dist_from_center > 0.01)

    # Normal direction: from ring center outward
    # Ring center is at distance major_radius from origin
    ring_center_x = cx + (dx[tube_area] / dist_from_center[tube_area]) * major_radius
    ring_center_y = cy + (dy[tube_area] / dist_from_center[tube_area]) * major_radius

    # Normal points from ring center to the point
    nx[tube_area] = (x_coords[tube_area] - ring_center_x) / minor_radius
    ny[tube_area] = (y_coords[tube_area] - ring_center_y) / minor_radius

    # Z component: based on distance from ring, create spherical cross-section
    # The z normal is derived from the circular cross-section of the tube
    angle = np.arccos(np.clip(dist_from_ring[tube_area] / minor_radius, -1, 1))
    nz[tube_area] = np.sin(angle) * 0.5  # Simplified z component

    # Normalize
    norm = np.sqrt(nx[tube_area]**2 + ny[tube_area]**2 + nz[tube_area]**2)
    nx[tube_area] = nx[tube_area] / np.maximum(norm, 0.01)
    ny[tube_area] = ny[tube_area] / np.maximum(norm, 0.01)
    nz[tube_area] = nz[tube_area] / np.maximum(norm, 0.01)

    # Add slight forward tilt for better visibility
    nz[tube_area] = nz[tube_area] * 0.7 + 0.3

    # Outline
    outline = (dist_from_ring > minor_radius - 3) & (dist_from_ring <= minor_radius)

    _torus_data = {
        'nx': nx, 'ny': ny, 'nz': nz,
        'mask': mask, 'outline': outline,
        'dist': dist_from_ring
    }
    return _torus_data


def precompute_cone(size=400):
    """Precompute cone normal data with perspective"""
    global _cone_data
    if _cone_data is not None:
        return _cone_data

    cx, cy = size // 2, size // 2
    radius = size // 3
    height = size // 2
    tip_y = cy - height // 2  # Tip at top

    y_coords, x_coords = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')
    dx = (x_coords - cx).astype(np.float32)
    dy = (y_coords - cy).astype(np.float32)
    dist_xy = np.sqrt(dx*dx + dy*dy)

    nx = np.zeros((size, size), dtype=np.float32)
    ny = np.zeros((size, size), dtype=np.float32)
    nz = np.zeros((size, size), dtype=np.float32)
    mask = np.zeros((size, size), dtype=bool)

    # Cone body: radius decreases as we go up (toward tip)
    # At y = tip_y, radius = 0; at y = tip_y + height, radius = max
    for y in range(size):
        if y < tip_y or y > tip_y + height:
            continue
        # Calculate radius at this height
        t = (y - tip_y) / height  # 0 at tip, 1 at base
        current_radius = radius * t

        for x in range(size):
            dist = np.sqrt((x - cx)**2 + 0.001)
            if dist <= current_radius:
                mask[y, x] = True
                # Normal points outward and slightly up
                if dist > 0.01:
                    nx[y, x] = (x - cx) / dist * 0.7
                    nz[y, x] = 0.5 + 0.3 * (1 - t)  # More forward at tip
                    ny[y, x] = -0.3 * t  # Slight upward tilt at base

    # Normalize normals where mask is True
    for y in range(size):
        for x in range(size):
            if mask[y, x]:
                n = np.sqrt(nx[y,x]**2 + ny[y,x]**2 + nz[y,x]**2)
                if n > 0.01:
                    nx[y,x] /= n
                    ny[y,x] /= n
                    nz[y,x] /= n

    # Base circle
    base_y = tip_y + height
    base_mask = (dist_xy <= radius) & (y_coords >= base_y - 5) & (y_coords <= base_y + 2)
    mask |= base_mask
    ny[base_mask] = 0.9
    nz[base_mask] = 0.1

    # Outline
    dist = np.zeros((size, size), dtype=np.float32)
    outline = np.zeros((size, size), dtype=bool)

    # Edge outline
    for y in range(size):
        for x in range(size):
            if mask[y, x]:
                # Check edge
                if y > 0 and not mask[y-1, x]:
                    outline[y, x] = True
                elif y < size-1 and not mask[y+1, x]:
                    outline[y, x] = True
                elif x > 0 and not mask[y, x-1]:
                    outline[y, x] = True
                elif x < size-1 and not mask[y, x+1]:
                    outline[y, x] = True

    _cone_data = {
        'nx': nx, 'ny': ny, 'nz': nz,
        'mask': mask, 'outline': outline,
        'dist': dist
    }
    return _cone_data


def precompute_icosahedron(size=400):
    """Precompute icosahedron (20-faced polyhedron) normal data"""
    global _icosahedron_data
    if _icosahedron_data is not None:
        return _icosahedron_data

    cx, cy = size // 2, size // 2
    radius = size // 3

    y_coords, x_coords = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')

    nx = np.zeros((size, size), dtype=np.float32)
    ny = np.zeros((size, size), dtype=np.float32)
    nz = np.zeros((size, size), dtype=np.float32)
    mask = np.zeros((size, size), dtype=bool)

    # Icosahedron vertices (normalized)
    phi = (1 + np.sqrt(5)) / 2  # Golden ratio

    # 12 vertices of icosahedron
    vertices = np.array([
        [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
        [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
        [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1]
    ])
    # Normalize
    for i in range(12):
        vertices[i] = vertices[i] / np.linalg.norm(vertices[i])

    # 20 face triangles (indices into vertices)
    faces = [
        [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
        [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
        [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
        [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]
    ]

    # Project faces to 2D and render
    for face in faces:
        v0, v1, v2 = vertices[face[0]], vertices[face[1]], vertices[face[2]]

        # Calculate face normal
        edge1 = v1 - v0
        edge2 = v2 - v0
        normal = np.cross(edge1, edge2)
        normal = normal / np.linalg.norm(normal)

        # Only render front-facing faces (normal.z > 0)
        if normal[2] < 0:
            continue

        # Project vertices to 2D (simple orthographic + perspective tilt)
        scale = radius * 1.2
        p0 = (int(cx + v0[0] * scale), int(cy - v0[1] * scale * 0.8))
        p1 = (int(cx + v1[0] * scale), int(cy - v1[1] * scale * 0.8))
        p2 = (int(cx + v2[0] * scale), int(cy - v2[1] * scale * 0.8))

        # Fill triangle using cv2
        triangle = np.array([p0, p1, p2], dtype=np.int32)
        temp_mask = np.zeros((size, size), dtype=np.uint8)
        cv2.fillPoly(temp_mask, [triangle], 255)

        # Add to main mask and set normals
        new_area = temp_mask > 0
        mask |= new_area
        nx[new_area] = normal[0]
        ny[new_area] = -normal[1]  # Flip Y for image coordinates
        nz[new_area] = max(normal[2], 0.3)  # Ensure forward-facing

    # Calculate outline
    outline = np.zeros((size, size), dtype=bool)
    dist = np.zeros((size, size), dtype=np.float32)

    # Find edges by checking for boundary pixels
    for y in range(1, size-1):
        for x in range(1, size-1):
            if mask[y, x]:
                neighbors = [mask[y-1,x], mask[y+1,x], mask[y,x-1], mask[y,x+1]]
                if not all(neighbors):
                    outline[y, x] = True

    _icosahedron_data = {
        'nx': nx, 'ny': ny, 'nz': nz,
        'mask': mask, 'outline': outline,
        'dist': dist
    }
    return _icosahedron_data


def get_shape_data(shape_name, size=400):
    """获取指定形状的预计算数据"""
    if shape_name == "sphere":
        return precompute_sphere(size)
    elif shape_name == "cube":
        return precompute_cube(size)
    elif shape_name == "cylinder":
        return precompute_cylinder(size)
    elif shape_name == "torus":
        return precompute_torus(size)
    elif shape_name == "cone":
        return precompute_cone(size)
    elif shape_name == "icosa":
        return precompute_icosahedron(size)
    return precompute_sphere(size)


def render_shape_with_skybox():
    """Render material shape with Skybox background and camera rotation - Optimized with advanced effects"""
    data = get_shape_data(current_shape, VIEWER_SIZE)
    skybox = generate_skybox(current_skybox, VIEWER_SIZE)

    # Result image - fill with skybox first
    result = skybox.copy()

    # Pre-compute rotation values
    cp, sp = np.cos(np.radians(camera_pitch)), np.sin(np.radians(camera_pitch))
    cy, sy = np.cos(np.radians(camera_yaw)), np.sin(np.radians(camera_yaw))
    cr, sr = np.cos(np.radians(camera_roll)), np.sin(np.radians(camera_roll))

    # Light direction
    cos_a, sin_a = np.cos(np.radians(rotation_angle)), np.sin(np.radians(rotation_angle))
    light = np.array([0.5 * cos_a - 0.8 * sin_a, -0.5, 0.5 * sin_a + 0.8 * cos_a])
    light = light / np.linalg.norm(light)

    # Get normals and apply rotation (vectorized)
    nx_b, ny_b, nz_b = data['nx'], data['ny'], data['nz']

    # Combined rotation in one step
    nx = (nx_b * cy + nz_b * sy) * cr - (ny_b * cp - (-nx_b * sy + nz_b * cy) * sp) * sr
    ny = (nx_b * cy + nz_b * sy) * sr + (ny_b * cp - (-nx_b * sy + nz_b * cy) * sp) * cr
    nz = ny_b * sp + (-nx_b * sy + nz_b * cy) * cp

    mask = data['mask']

    # Diffuse (vectorized)
    NdotL = np.maximum(0, nx * light[0] + ny * light[1] + nz * light[2])

    # Subsurface scattering simulation
    sss = material["sss"]
    if sss > 0:
        # Wrap lighting for SSS effect
        wrap = 0.5
        NdotL_sss = np.maximum(0, (NdotL + wrap) / (1 + wrap))
        # Add reddish tint in shadow areas
        sss_factor = (1 - NdotL) * sss * 0.4
        NdotL = NdotL * (1 - sss * 0.3) + NdotL_sss * sss * 0.3

    # Smooth cel-shading with configurable smoothing
    levels = int(material["levels"])
    smooth_factor = 0.15

    if levels == 2:
        shade = np.clip((NdotL - 0.5) / smooth_factor + 0.5, 0, 1)
    elif levels == 3:
        shade = np.clip(np.floor(NdotL * 3 + 0.5) / 2, 0, 1)
    else:
        shade = np.clip(np.floor(NdotL * 4 + 0.5) / 3, 0, 1)

    shade = np.clip(shade + material["shadow_r"] * 0.3, 0, 1)

    # Color computation (vectorized)
    shadow_b = material["shadow_b"] + sss_factor * 0.1 if sss > 0 else material["shadow_b"]
    shadow_g, shadow_r = material["shadow_g"], material["shadow_r"]

    # Single array operation
    shape_color = np.stack([
        shadow_b + (0.92 - shadow_b) * shade,
        shadow_g + (0.90 - shadow_g) * shade,
        shadow_r + (0.90 - shadow_r) * shade
    ], axis=-1)

    # Add SSS reddish tint
    if sss > 0:
        shape_color[..., 2] += sss_factor * 0.15  # Add red in shadow areas

    # Specular with roughness
    roughness = material["roughness"]
    spec_power = 32 * (1 - roughness * 0.8)

    # Anisotropic specular
    aniso = material["aniso"]
    if aniso > 0:
        # Tangent-based anisotropic highlight
        tangent_x = np.where(np.abs(nz) < 0.99, -nz, 0)
        tangent_y = np.zeros_like(tangent_x)
        tangent_z = np.where(np.abs(nz) < 0.99, nx, 1)

        # Stretch highlight in tangent direction
        half = np.array([0.22, -0.22, 0.95])
        NdotH = np.maximum(0, nx * half[0] + ny * half[1] * (1 - aniso) + nz * half[2])
    else:
        half = np.array([0.22, -0.22, 0.95])
        NdotH = np.maximum(0, nx * half[0] + ny * half[1] + nz * half[2])

    spec = np.clip(np.power(NdotH, spec_power) * material["specular"], 0, 1)

    shape_color[..., 0] += spec * 0.9
    shape_color[..., 1] += spec * 0.8
    shape_color[..., 2] += spec * 0.7

    # Rim light with fresnel
    rim = np.power(np.maximum(0, 1 - nz), 3) * material["rim"]
    shape_color[..., 0] += rim * 1.0
    shape_color[..., 1] += rim * 0.85
    shape_color[..., 2] += rim * 0.8

    # Metallic reflection
    metallic = material["metallic"]
    fresnel = np.power(np.maximum(0, 1 - nz), 2) * (0.25 + metallic * 0.5)
    fresnel = np.expand_dims(fresnel, axis=-1)  # For broadcasting
    shape_color = shape_color * (1 - fresnel) + skybox * fresnel

    shape_color = np.clip(shape_color, 0, 1)

    # Composite
    result[mask] = shape_color[mask]

    # Outline
    if material["outline"] > 0 and 'outline' in data:
        result[data['outline']] = [0.02, 0.02, 0.05]

    return (result * 255).astype(np.uint8)


def update_shape():
    """更新形状渲染"""
    if compare_mode:
        img = render_compare_view()
    else:
        img = render_shape_with_skybox()
    rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0
    if dpg.does_item_exist("sphere_tex"):
        dpg.set_value("sphere_tex", rgba.ravel().tolist())


def update_multi_shape():
    """更新多形状预览"""
    global preview_mode

    if preview_mode == "single":
        update_shape()
        return

    # 多形状预览
    shapes_to_show = SHAPE_NAMES[:4] if preview_mode == "2x2" else SHAPE_NAMES[:3]

    for i, shape_name in enumerate(shapes_to_show):
        tex_tag = f"shape_tex_{i}"
        if not dpg.does_item_exist(tex_tag):
            continue

        # 渲染单个形状
        data = get_shape_data(shape_name, VIEWER_SIZE // 2 if preview_mode == "2x2" else VIEWER_SIZE)
        img = render_single_shape(data, VIEWER_SIZE // 2 if preview_mode == "2x2" else VIEWER_SIZE)

        # 调整大小
        if preview_mode == "2x2":
            img = cv2.resize(img, (VIEWER_SIZE // 2, VIEWER_SIZE // 2))
        else:
            img = cv2.resize(img, (VIEWER_SIZE // 3, VIEWER_SIZE))

        rgba = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0
        dpg.set_value(tex_tag, rgba.ravel().tolist())


def render_single_shape(data, size):
    """渲染单个形状"""
    skybox = generate_skybox(current_skybox, size)
    result = skybox.copy()

    # 计算旋转矩阵
    pitch_rad = np.radians(camera_pitch)
    yaw_rad = np.radians(camera_yaw)
    roll_rad = np.radians(camera_roll)
    cp, sp = np.cos(pitch_rad), np.sin(pitch_rad)
    cy, sy = np.cos(yaw_rad), np.sin(yaw_rad)
    cr, sr = np.cos(roll_rad), np.sin(roll_rad)

    # 光源方向
    angle_rad = np.radians(rotation_angle)
    base_light = np.array([0.5, -0.5, 0.8])
    cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)
    light = np.array([
        base_light[0] * cos_a - base_light[2] * sin_a,
        base_light[1],
        base_light[0] * sin_a + base_light[2] * cos_a
    ])
    light = light / np.linalg.norm(light)

    # 获取法线
    nx_base = data['nx']
    ny_base = data['ny']
    nz_base = data['nz']
    mask = data['mask']

    # 应用摄像机旋转
    nx_rot = nx_base * cy + nz_base * sy
    nz_rot = -nx_base * sy + nz_base * cy
    ny_rot = ny_base.copy()
    ny_final = ny_rot * cp - nz_rot * sp
    nz_final = ny_rot * sp + nz_rot * cp
    nx_final = nx_rot.copy()
    nx = nx_final * cr - ny_final * sr
    ny = nx_final * sr + ny_final * cr
    nz = nz_final.copy()

    # 漫反射
    NdotL = np.maximum(0, nx*light[0] + ny*light[1] + nz*light[2])

    # 色阶化
    levels = int(material["levels"])
    if levels == 2:
        shade = (NdotL > 0.5).astype(np.float32)
    elif levels == 3:
        shade = np.clip(np.floor(NdotL * 3) / 2, 0, 1)
    else:
        shade = np.clip(np.floor(NdotL * 4) / 3, 0, 1)

    shade = np.clip(shade + material["shadow_r"] * 0.3, 0, 1)

    # 颜色
    shadow = [material["shadow_b"], material["shadow_g"], material["shadow_r"]]
    base = [0.92, 0.9, 0.9]

    shape_color = np.zeros((size, size, 3), dtype=np.float32)
    for c in range(3):
        shape_color[:,:,c] = shadow[c] + (base[c] - shadow[c]) * shade

    # 高光
    half = np.array([0.25, -0.25, 0.9])
    half = half / np.linalg.norm(half)
    NdotH = np.maximum(0, nx*half[0] + ny*half[1] + nz*half[2])
    spec = np.clip(np.power(NdotH, 32) * material["specular"], 0, 1)

    shape_color[:,:,0] += spec * 0.9
    shape_color[:,:,1] += spec * 0.8
    shape_color[:,:,2] += spec * 0.7

    # 边缘光
    rim = np.power(1 - nz, 3) * material["rim"]
    shape_color[:,:,0] += rim * 1.0
    shape_color[:,:,1] += rim * 0.85
    shape_color[:,:,2] += rim * 0.8

    # 环境反射
    fresnel = np.power(1 - nz, 2)
    for c in range(3):
        shape_color[:,:,c] = shape_color[:,:,c] * (1 - fresnel * 0.2) + skybox[:,:,c] * fresnel * 0.2

    shape_color = np.clip(shape_color, 0, 1)

    # 合成
    result[mask] = shape_color[mask]

    # 描边
    outline_width = int(material["outline"])
    if outline_width > 0 and 'outline' in data:
        outline_mask = data['outline']
        result[outline_mask] = [0.02, 0.02, 0.05]

    return (result * 255).astype(np.uint8)


def on_preview_mode_change(sender, app_data):
    """切换预览模式"""
    global preview_mode
    preview_mode = app_data
    print(f"[Preview Mode] {preview_mode}")
    # 需要重建 UI
    rebuild_preview_area()


def toggle_compare_mode(sender, app_data):
    """切换对比视图模式"""
    global compare_mode
    compare_mode = not compare_mode
    label = "Compare: ON" if compare_mode else "Compare: OFF"
    dpg.set_item_label("btn_compare", label)
    dpg.set_value("status", f"Compare mode: {'ON' if compare_mode else 'OFF'}")
    update_shape()


def on_compare_shape_a_change(sender, app_data):
    """对比形状A选择"""
    global compare_shape_a
    compare_shape_a = app_data
    if compare_mode:
        update_shape()


def on_compare_shape_b_change(sender, app_data):
    """对比形状B选择"""
    global compare_shape_b
    compare_shape_b = app_data
    if compare_mode:
        update_shape()


def render_compare_view():
    """渲染对比视图（两个形状并排）"""
    half_size = VIEWER_SIZE // 2

    # 渲染形状A
    data_a = get_shape_data(compare_shape_a, half_size)
    skybox_a = generate_skybox(current_skybox, half_size)

    # 简化渲染（直接用 render_shape_with_skybox 然后缩放）
    global current_shape
    original_shape = current_shape

    current_shape = compare_shape_a
    img_a_full = render_shape_with_skybox()
    img_a = cv2.resize(img_a_full, (half_size, half_size))

    current_shape = compare_shape_b
    img_b_full = render_shape_with_skybox()
    img_b = cv2.resize(img_b_full, (half_size, half_size))

    # 恢复原形状
    current_shape = original_shape

    # 拼接
    result = np.hstack([img_a, img_b])

    # 添加分隔线
    cv2.line(result, (half_size, 0), (half_size, VIEWER_SIZE), (50, 50, 50), 2)

    # 添加标签
    cv2.putText(result, compare_shape_a, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150, 150, 150), 2)
    cv2.putText(result, compare_shape_b, (half_size + 10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150, 150, 150), 2)

    return result


def rebuild_preview_area():
    """重建预览区域"""
    # 删除旧的预览区域并重建
    if dpg.does_item_exist("preview_group"):
        dpg.delete_item("preview_group")

    # 重建将在下一帧完成
    dpg.split_frame()
    build_preview_area()


def build_preview_area():
    """构建预览区域"""
    with dpg.group(tag="preview_group"):
        if preview_mode == "single":
            # 单形状预览
            dpg.add_dynamic_texture(VIEWER_SIZE, VIEWER_SIZE, [0.1]*4*VIEWER_SIZE**2, tag="sphere_tex")
            with dpg.drawlist(width=VIEWER_SIZE, height=VIEWER_SIZE):
                dpg.draw_image("sphere_tex", (0, 0), (VIEWER_SIZE, VIEWER_SIZE))
        elif preview_mode == "2x2":
            # 2x2 网格
            small_size = VIEWER_SIZE // 2
            for i in range(4):
                dpg.add_dynamic_texture(small_size, small_size, [0.1]*4*small_size**2, tag=f"shape_tex_{i}")
            with dpg.drawlist(width=VIEWER_SIZE, height=VIEWER_SIZE):
                # 第一行
                dpg.draw_image("shape_tex_0", (0, 0), (small_size, small_size))
                dpg.draw_image("shape_tex_1", (small_size, 0), (VIEWER_SIZE, small_size))
                # 第二行
                dpg.draw_image("shape_tex_2", (0, small_size), (small_size, VIEWER_SIZE))
                dpg.draw_image("shape_tex_3", (small_size, small_size), (VIEWER_SIZE, VIEWER_SIZE))
        elif preview_mode == "1x3":
            # 1x3 水平排列
            w = VIEWER_SIZE // 3
            for i in range(3):
                dpg.add_dynamic_texture(w, VIEWER_SIZE, [0.1]*4*w*VIEWER_SIZE, tag=f"shape_tex_{i}")
            with dpg.drawlist(width=VIEWER_SIZE, height=VIEWER_SIZE):
                dpg.draw_image("shape_tex_0", (0, 0), (w, VIEWER_SIZE))
                dpg.draw_image("shape_tex_1", (w, 0), (2*w, VIEWER_SIZE))
                dpg.draw_image("shape_tex_2", (2*w, 0), (VIEWER_SIZE, VIEWER_SIZE))

    # 更新渲染
    update_shape()


def update_ref_image():
    if ref_image is None:
        return

    display = cv2.resize(ref_image.copy(), (VIEWER_SIZE, VIEWER_SIZE))

    if mask_image is not None:
        mask_resized = cv2.resize(mask_image, (VIEWER_SIZE, VIEWER_SIZE), interpolation=cv2.INTER_NEAREST)
        green = (mask_resized == 1)
        display[green] = (display[green] * 0.6 + np.array([100, 255, 0]) * 0.4).astype(np.uint8)
        red = (mask_resized == 2)
        display[red] = (display[red] * 0.6 + np.array([0, 50, 255]) * 0.4).astype(np.uint8)

    rgba = cv2.cvtColor(display, cv2.COLOR_BGR2RGBA).astype(np.float32) / 255.0
    dpg.set_value("ref_tex", rgba.ravel().tolist())


def on_file_select(sender, app_data):
    global ref_image, mask_image
    path = app_data.get("file_path_name", "") if isinstance(app_data, dict) else ""
    if not path:
        return

    img = cv2.imread(path)
    if img is None:
        return

    ref_image = img
    mask_image = np.zeros(img.shape[:2], dtype=np.uint8)
    update_ref_image()
    dpg.set_value("ref_path", os.path.basename(path))
    print(f"[Load] {img.shape[1]}x{img.shape[0]}")


def on_mouse_drag(sender, app_data):
    if ref_image is None or brush_mode == 0:
        return

    mx, my = dpg.get_mouse_pos()
    x = int((mx - 20) / VIEWER_SIZE * ref_image.shape[1])
    y = int((my - 80) / VIEWER_SIZE * ref_image.shape[0])

    if 0 <= x < ref_image.shape[1] and 0 <= y < ref_image.shape[0]:
        size = int(brush_size * ref_image.shape[1] / VIEWER_SIZE)
        cv2.circle(mask_image, (x, y), size, brush_mode, -1)
        update_ref_image()


def on_brush(mode):
    global brush_mode
    brush_mode = mode
    modes = ["Off", "Focus", "Ignore"]
    print(f"[Brush] {modes[mode]}")


def on_clear():
    global mask_image
    if ref_image is not None:
        mask_image = np.zeros(ref_image.shape[:2], dtype=np.uint8)
        update_ref_image()


def on_skybox_change(sender, app_data):
    global current_skybox
    # app_data 是选中的名称，需要找到对应的索引
    for idx, preset in enumerate(SKYBOX_PRESETS):
        if preset["name"] == app_data:
            current_skybox = idx
            break
    update_shape()
    dpg.set_value("skybox_name", SKYBOX_PRESETS[current_skybox]["desc"])
    print(f"[Skybox] {SKYBOX_PRESETS[current_skybox]['name']}")


def update_shape_button_themes():
    """更新形状按钮的主题高亮"""
    for i, shape in enumerate(SHAPE_NAMES):
        is_selected = shape == current_shape
        btn_color = (70, 140, 210) if is_selected else (50, 50, 55)
        hover_color = (100, 180, 240) if is_selected else (70, 70, 75)

        theme_tag = f"shape_theme_{i}"
        if dpg.does_item_exist(theme_tag):
            dpg.delete_item(theme_tag)

        with dpg.theme(tag=theme_tag):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, btn_color, category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, hover_color, category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, hover_color, category=dpg.mvThemeCat_Core)

        if dpg.does_item_exist(f"shape_btn_{i}"):
            dpg.bind_item_theme(f"shape_btn_{i}", theme_tag)


def on_shape_change_by_index(sender, app_data, index):
    """Shape change callback by index"""
    global current_shape
    new_shape = SHAPE_NAMES[index]

    if new_shape == current_shape:
        return

    current_shape = new_shape
    print(f"[Shape] Changed to {current_shape}")
    update_shape_button_themes()
    update_shape()


def on_auto_rotate(sender, app_data):
    """Toggle auto rotation"""
    global auto_rotate
    auto_rotate = not auto_rotate
    # Update button label
    label = "Auto: ON" if auto_rotate else "Auto: OFF"
    dpg.set_item_label("btn_rotate", label)
    print(f"[Rotation] {'ON' if auto_rotate else 'OFF'}")


# =============================================================================
# 摄像机控制
# =============================================================================

def on_camera_pitch(sender, app_data):
    """Camera pitch (X axis) slider callback"""
    global camera_pitch
    camera_pitch = app_data
    update_shape()


def on_camera_yaw(sender, app_data):
    """Camera yaw (Y axis) slider callback"""
    global camera_yaw, rotation_angle
    camera_yaw = app_data
    # Sync with rotation angle for light direction
    rotation_angle = camera_yaw
    if dpg.does_item_exist("rot_angle"):
        dpg.set_value("rot_angle", rotation_angle)
    update_shape()


def on_camera_roll(sender, app_data):
    """Camera roll (Z axis) slider callback"""
    global camera_roll
    camera_roll = app_data
    update_shape()


def on_camera_distance(sender, app_data):
    """Camera distance (zoom) slider callback"""
    global camera_distance
    camera_distance = app_data
    update_shape()


def on_mouse_down(sender, app_data):
    """Mouse button press handler"""
    global mouse_dragging, mouse_button, last_mouse_x, last_mouse_y
    mouse_dragging = True
    mouse_button = app_data  # 0=left, 1=right, 2=middle
    last_mouse_x, last_mouse_y = dpg.get_mouse_pos()


def on_mouse_up(sender, app_data):
    """Mouse button release handler"""
    global mouse_dragging, mouse_button
    mouse_dragging = False
    mouse_button = -1


def on_mouse_move(sender, app_data):
    """Mouse move handler for camera control"""
    global mouse_dragging, mouse_button, last_mouse_x, last_mouse_y
    global camera_pitch, camera_yaw, camera_pan_x, camera_pan_y, rotation_angle

    if not mouse_dragging:
        return

    mx, my = dpg.get_mouse_pos()
    dx = mx - last_mouse_x
    dy = my - last_mouse_y
    last_mouse_x, last_mouse_y = mx, my

    if mouse_button == 0:  # Left button: rotate
        camera_yaw += dx * 0.5
        camera_pitch += dy * 0.5
        # Clamp pitch to prevent flipping
        camera_pitch = np.clip(camera_pitch, -90, 90)
        # Keep yaw in 0-360 range
        while camera_yaw < 0:
            camera_yaw += 360
        while camera_yaw >= 360:
            camera_yaw -= 360
        # Sync rotation angle with yaw
        rotation_angle = camera_yaw
        # Update sliders
        if dpg.does_item_exist("cam_pitch"):
            dpg.set_value("cam_pitch", camera_pitch)
        if dpg.does_item_exist("cam_yaw"):
            dpg.set_value("cam_yaw", camera_yaw)
        if dpg.does_item_exist("rot_angle"):
            dpg.set_value("rot_angle", rotation_angle)
        update_shape()

    elif mouse_button == 1:  # Right button: pan
        camera_pan_x += dx * 0.002
        camera_pan_y -= dy * 0.002
        # Clamp pan
        camera_pan_x = np.clip(camera_pan_x, -0.5, 0.5)
        camera_pan_y = np.clip(camera_pan_y, -0.5, 0.5)
        update_shape()


def on_mouse_wheel(sender, app_data):
    """Mouse wheel handler for zoom"""
    global camera_distance
    # app_data is wheel direction (+/-)
    camera_distance -= app_data * 0.05
    camera_distance = np.clip(camera_distance, 0.5, 2.0)
    dpg.set_value("cam_dist", camera_distance)
    update_shape()


def sync_camera_sliders():
    """Sync all camera sliders with current values"""
    if dpg.does_item_exist("cam_pitch"):
        dpg.set_value("cam_pitch", camera_pitch)
    if dpg.does_item_exist("cam_yaw"):
        dpg.set_value("cam_yaw", camera_yaw)
    if dpg.does_item_exist("cam_roll"):
        dpg.set_value("cam_roll", camera_roll)
    if dpg.does_item_exist("cam_dist"):
        dpg.set_value("cam_dist", camera_distance)


def reset_camera():
    """Reset camera to default position"""
    global camera_pitch, camera_yaw, camera_roll, camera_distance
    camera_pitch, camera_yaw, camera_roll, camera_distance = 0.0, 0.0, 0.0, 1.0
    sync_camera_sliders()
    update_shape()


def randomize_material():
    """随机生成材质参数"""
    import random

    global material
    material = {
        "shadow_r": random.uniform(0.2, 0.5),
        "shadow_g": random.uniform(0.2, 0.5),
        "shadow_b": random.uniform(0.25, 0.55),
        "specular": random.uniform(0.3, 1.2),
        "rim": random.uniform(0.2, 1.0),
        "outline": random.uniform(0.5, 4.0),
        "levels": random.choice([2, 3, 4]),
        "sss": random.uniform(0, 0.5),
        "aniso": random.uniform(0, 0.5),
        "metallic": random.uniform(0, 0.8),
        "roughness": random.uniform(0.2, 0.8),
    }

    # Update UI sliders
    for key, tag in [("shadow_r","s_r"), ("shadow_g","s_g"), ("shadow_b","s_b"),
                     ("specular","s_sp"), ("rim","s_rm"), ("outline","s_ot"),
                     ("sss","s_sss"), ("aniso","s_aniso"), ("metallic","s_metal"),
                     ("roughness","s_rough")]:
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, material[key])
    dpg.set_value("s_lv", int(material["levels"]))
    update_shape()


def on_randomize(sender, app_data):
    """随机风格按钮回调"""
    randomize_material()
    dpg.set_value("status", "Random style generated")


def reset_material():
    """Reset material to default values"""
    global material
    material = {
        "shadow_r": 0.35, "shadow_g": 0.35, "shadow_b": 0.4,
        "specular": 0.6, "rim": 0.5, "outline": 2.0, "levels": 3,
        "sss": 0.3, "aniso": 0.2, "metallic": 0.0, "roughness": 0.5,
    }
    # Update all UI sliders
    for key, tag in [("shadow_r","s_r"), ("shadow_g","s_g"), ("shadow_b","s_b"),
                     ("specular","s_sp"), ("rim","s_rm"), ("outline","s_ot"),
                     ("sss","s_sss"), ("aniso","s_aniso"), ("metallic","s_metal"),
                     ("roughness","s_rough")]:
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, material[key])
    dpg.set_value("s_lv", 3)
    update_shape()


def save_screenshot():
    """保存当前预览截图"""
    import datetime

    # 渲染当前画面
    img = render_shape_with_skybox()

    # 生成文件名
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"autotoon_{current_shape}_{timestamp}.png"

    # 保存到 data/screenshots 目录
    screenshot_dir = os.path.join(os.path.dirname(__file__), "..", "data", "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)
    filepath = os.path.join(screenshot_dir, filename)

    cv2.imwrite(filepath, img)
    print(f"[Screenshot] Saved: {filepath}")
    return filepath


def on_save_screenshot(sender, app_data):
    """截图按钮回调"""
    path = save_screenshot()
    dpg.set_value("status", f"Saved: {os.path.basename(path)}")


def on_key_press(sender, app_data):
    """Handle keyboard shortcuts"""
    key = app_data

    # Shape shortcuts: 1-6
    if key in [ord(str(i)) for i in range(1, 7)]:
        idx = key - ord('1')
        if idx < len(SHAPE_NAMES):
            global current_shape
            current_shape = SHAPE_NAMES[idx]
            update_shape_button_themes()
            update_shape()

    # Reset: R
    elif key == ord('r') or key == ord('R'):
        reset_camera()

    # Reset material: M
    elif key == ord('m') or key == ord('M'):
        reset_material()

    # Toggle auto rotate: Space
    elif key == 32:  # Space
        on_auto_rotate(None, None)


# =============================================================================
# 风格预设管理
# =============================================================================

STYLE_DIR = os.path.join(os.path.dirname(__file__), "..", "presets")


def get_style_presets():
    """获取所有风格预设"""
    os.makedirs(STYLE_DIR, exist_ok=True)
    presets = []
    for f in os.listdir(STYLE_DIR):
        if f.endswith(".style"):
            presets.append(f[:-6])  # Remove .style extension
    return presets


def save_style_preset(name):
    """保存当前材质参数为预设"""
    os.makedirs(STYLE_DIR, exist_ok=True)
    filepath = os.path.join(STYLE_DIR, f"{name}.style")
    data = {
        "name": name,
        "material": material.copy(),
        "skybox": current_skybox,
        "shape": current_shape,
    }
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"[Style] Saved: {filepath}")


def load_style_preset(name):
    """加载风格预设"""
    filepath = os.path.join(STYLE_DIR, f"{name}.style")
    if not os.path.exists(filepath):
        print(f"[Style] Not found: {filepath}")
        return False

    with open(filepath, 'r') as f:
        data = json.load(f)

    global material, current_skybox, current_shape

    # Load material
    for key in material:
        if key in data.get("material", {}):
            material[key] = data["material"][key]

    # Update UI sliders
    for key, tag in [("shadow_r","s_r"), ("shadow_g","s_g"), ("shadow_b","s_b"),
                     ("specular","s_sp"), ("rim","s_rm"), ("outline","s_ot"),
                     ("sss","s_sss"), ("aniso","s_aniso"), ("metallic","s_metal"),
                     ("roughness","s_rough")]:
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, material[key])
    dpg.set_value("s_lv", int(material.get("levels", 3)))

    # Load skybox
    current_skybox = data.get("skybox", 0)
    dpg.set_value("skybox_combo", SKYBOX_PRESETS[current_skybox]["name"])

    # Load shape
    current_shape = data.get("shape", "sphere")
    update_shape_button_themes()
    update_shape()

    print(f"[Style] Loaded: {name}")
    return True


def on_save_preset(sender, app_data):
    """保存预设回调"""
    name = dpg.get_value("preset_name")
    if not name:
        dpg.set_value("status", "Enter preset name")
        return
    save_style_preset(name)
    update_preset_list()
    dpg.set_value("status", f"Saved: {name}")


def show_about_dialog():
    """显示关于对话框"""
    with dpg.window(label="About AutoToon", modal=True, tag="about_window", width=400, height=350):
        dpg.add_text("AutoToon Studio - Skybox Version 2.0", color=(100, 180, 255))
        dpg.add_separator()
        dpg.add_spacer(height=5)

        dpg.add_text("AI-assisted UE5 real-time stylization tool")
        dpg.add_spacer(height=10)

        dpg.add_text("Features:", color=(180, 180, 100))
        dpg.add_text("• 6 Shape Types: Sphere, Cube, Cylinder, Torus, Cone, Icosa")
        dpg.add_text("• 9 Skybox Presets + Custom Image Support")
        dpg.add_text("• Advanced: SSS, Anisotropic, Metallic, Roughness")
        dpg.add_text("• Style Presets: Save/Load material configurations")
        dpg.add_text("• Screenshot Export")
        dpg.add_spacer(height=10)

        dpg.add_text("Keyboard Shortcuts:", color=(180, 180, 100))
        dpg.add_text("1-6: Switch shapes | R: Reset camera")
        dpg.add_text("M: Reset material | Space: Toggle auto-rotate")
        dpg.add_spacer(height=10)

        dpg.add_text("Tech Stack:", color=(180, 180, 100))
        dpg.add_text("Python + Dear PyGui + NumPy + OpenCV + ONNX")
        dpg.add_spacer(height=15)

        dpg.add_button(label="Close", callback=lambda: dpg.delete_item("about_window"), width=100)


def on_about(sender, app_data):
    """关于按钮回调"""
    if dpg.does_item_exist("about_window"):
        dpg.delete_item("about_window")
    show_about_dialog()


def on_load_preset(sender, app_data):
    """加载预设回调"""
    name = dpg.get_value("preset_combo")
    if not name:
        return
    if load_style_preset(name):
        dpg.set_value("status", f"Loaded: {name}")


def update_preset_list():
    """更新预设下拉列表"""
    presets = get_style_presets()
    if dpg.does_item_exist("preset_combo"):
        dpg.configure_item("preset_combo", items=presets)


# =============================================================================
# UE5 连接功能
# =============================================================================

def check_ue5_connection():
    """检查 UE5 连接状态"""
    if ue_client is None:
        return {"ok": False, "error": "UE5 client not available"}

    result = ue_client.health_check()
    return result


def send_to_ue5():
    """发送当前材质参数到 UE5"""
    if ue_client is None:
        return {"ok": False, "error": "UE5 client not available"}

    # 构建参数列表 (6 个主要参数)
    params = [
        material["shadow_r"],
        material["shadow_g"],
        material["shadow_b"],
        material["specular"],
        material["rim"],
        material["outline"] / 5.0,  # 归一化到 0-1
    ]

    return ue_client.send_params(params)


def on_check_ue5(sender, app_data):
    """检查 UE5 连接按钮回调"""
    result = check_ue5_connection()
    if result["ok"]:
        dpg.set_value("ue5_status", "Connected ✓")
        dpg.configure_item("ue5_status", color=(80, 200, 80))
    else:
        dpg.set_value("ue5_status", "Disconnected ✗")
        dpg.configure_item("ue5_status", color=(200, 80, 80))
    dpg.set_value("status", result.get("error", "UE5 connected") if not result["ok"] else "UE5 connected")


def on_send_ue5(sender, app_data):
    """发送到 UE5 按钮回调"""
    # 先检查连接
    check = check_ue5_connection()
    if not check["ok"]:
        dpg.set_value("status", check.get("error", "UE5 not connected"))
        dpg.set_value("ue5_status", "Disconnected ✗")
        dpg.configure_item("ue5_status", color=(200, 80, 80))
        return

    # 发送参数
    result = send_to_ue5()
    if result["ok"]:
        dpg.set_value("status", "Sent to UE5!")
    else:
        dpg.set_value("status", result.get("error", "Send failed"))


# =============================================================================
# 实时联动功能
# =============================================================================

def on_realtime_sync_toggle(sender, app_data):
    """实时联动开关回调"""
    global realtime_sync

    realtime_sync = app_data

    if realtime_sync:
        # 启动 WebSocket 客户端
        if ws_client:
            ws_client.on_params_received(on_ws_params_received)
            ws_client.on_connected(on_ws_connected)
            ws_client.on_disconnected(on_ws_disconnected)
            ws_client.start()
            dpg.set_value("status", "Real-time sync enabled")
        else:
            dpg.set_value("status", "WebSocket not available")
            dpg.set_value("realtime_sync_checkbox", False)
            realtime_sync = False
    else:
        # 停止 WebSocket 客户端
        if ws_client:
            ws_client.stop()
        dpg.set_value("ws_status", "Disabled")
        dpg.configure_item("ws_status", color=(150, 150, 150))


def on_ws_params_received(params: dict):
    """WebSocket 参数接收回调"""
    global _updating_from_ue5, material

    _updating_from_ue5 = True

    try:
        # 更新材质参数
        if "shadow_r" in params:
            material["shadow_r"] = params["shadow_r"]
            dpg.set_value("slider_shadow_r", params["shadow_r"])
        if "shadow_g" in params:
            material["shadow_g"] = params["shadow_g"]
            dpg.set_value("slider_shadow_g", params["shadow_g"])
        if "shadow_b" in params:
            material["shadow_b"] = params["shadow_b"]
            dpg.set_value("slider_shadow_b", params["shadow_b"])
        if "specular" in params:
            material["specular"] = params["specular"]
            dpg.set_value("slider_specular", params["specular"])
        if "rim" in params:
            material["rim"] = params["rim"]
            dpg.set_value("slider_rim", params["rim"])
        if "outline" in params:
            material["outline"] = params["outline"]
            dpg.set_value("slider_outline", params["outline"])
        if "sss" in params:
            material["sss"] = params["sss"]
            dpg.set_value("slider_sss", params["sss"])
        if "aniso" in params:
            material["aniso"] = params["aniso"]
            dpg.set_value("slider_aniso", params["aniso"])
        if "metallic" in params:
            material["metallic"] = params["metallic"]
            dpg.set_value("slider_metallic", params["metallic"])
        if "roughness" in params:
            material["roughness"] = params["roughness"]
            dpg.set_value("slider_roughness", params["roughness"])

        dpg.set_value("status", "Params updated from UE5")

    finally:
        _updating_from_ue5 = False


def on_ws_connected():
    """WebSocket 连接成功回调"""
    dpg.set_value("ws_status", "Connected")
    dpg.configure_item("ws_status", color=(80, 200, 80))


def on_ws_disconnected():
    """WebSocket 断开连接回调"""
    dpg.set_value("ws_status", "Disconnected")
    dpg.configure_item("ws_status", color=(200, 80, 80))


def send_params_realtime():
    """实时发送参数到 UE5（通过 WebSocket）"""
    if not realtime_sync or not ws_client or not ws_client.connected:
        return

    params = {
        "shadow_r": material["shadow_r"],
        "shadow_g": material["shadow_g"],
        "shadow_b": material["shadow_b"],
        "specular": material["specular"],
        "rim": material["rim"],
        "outline": material["outline"],
        "sss": material["sss"],
        "aniso": material["aniso"],
        "metallic": material["metallic"],
        "roughness": material["roughness"],
    }

    ws_client.send_params(params)


# =============================================================================
# 批量处理功能
# =============================================================================

batch_images = []
batch_results = []


def on_batch_folder_select(sender, app_data):
    """选择批量处理文件夹"""
    global batch_images, batch_results

    folder_path = app_data.get("file_path_name", "") if isinstance(app_data, dict) else ""
    if not folder_path or not os.path.isdir(folder_path):
        dpg.set_value("status", "Invalid folder")
        return

    # 收集所有图片
    batch_images = []
    valid_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}

    for f in os.listdir(folder_path):
        if os.path.splitext(f)[1].lower() in valid_exts:
            batch_images.append(os.path.join(folder_path, f))

    batch_results = []
    dpg.set_value("batch_info", f"Found {len(batch_images)} images")
    dpg.set_value("status", f"Loaded {len(batch_images)} images for batch processing")


def run_batch_process():
    """执行批量处理"""
    global batch_results

    if not batch_images:
        return

    if engine is None:
        dpg.set_value("status", "No model loaded")
        return

    from PIL import Image
    MEAN, STD = np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225])

    batch_results = []

    for i, img_path in enumerate(batch_images):
        try:
            img = cv2.imread(img_path)
            if img is None:
                continue

            x = np.array(Image.fromarray(img).convert("RGB").resize((224, 224)), dtype=np.float32) / 255.0
            x = ((x - MEAN) / STD).astype(np.float32).transpose(2, 0, 1)[np.newaxis, :]

            preds = engine.run(["params"], {engine.get_inputs()[0].name: x})[0][0]

            result = {
                "file": os.path.basename(img_path),
                "params": preds.tolist()
            }
            batch_results.append(result)

            dpg.set_value("batch_info", f"Processing: {i+1}/{len(batch_images)}")

        except Exception as e:
            print(f"[Batch] Error processing {img_path}: {e}")

    # 保存结果
    output_path = os.path.join(os.path.dirname(__file__), "..", "data", "batch_results.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(batch_results, f, indent=2)

    dpg.set_value("status", f"Batch done: {len(batch_results)} results saved")
    dpg.set_value("batch_info", f"Processed: {len(batch_results)}/{len(batch_images)}")


def on_batch_process(sender, app_data):
    """批量处理按钮回调"""
    run_batch_process()


def on_rotation_speed(sender, app_data):
    """Change rotation speed"""
    global rotation_speed
    rotation_speed = app_data


def on_manual_rotation(sender, app_data):
    """Manual rotation angle"""
    global rotation_angle
    rotation_angle = app_data
    if not auto_rotate:
        update_shape()


def on_infer():
    global engine
    if engine is None or ref_image is None:
        dpg.set_value("status", "No image/model")
        return

    try:
        from PIL import Image
        MEAN, STD = np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225])

        img = ref_image.copy()
        if mask_image is not None and np.any(mask_image == 2):
            img[mask_image == 2] = cv2.GaussianBlur(img, (51, 51), 0)[mask_image == 2]

        x = np.array(Image.fromarray(img).convert("RGB").resize((224, 224)), dtype=np.float32) / 255.0
        x = ((x - MEAN) / STD).astype(np.float32).transpose(2, 0, 1)[np.newaxis, :]

        preds = engine.run(["params"], {engine.get_inputs()[0].name: x})[0][0]

        material["shadow_r"] = float(preds[0])
        material["shadow_g"] = float(preds[1])
        material["shadow_b"] = float(preds[2])
        material["specular"] = float(preds[3])
        material["rim"] = float(preds[4])
        material["outline"] = float(preds[5]) * 5  # 0~5 范围

        for k, tag in [("shadow_r","s_r"), ("shadow_g","s_g"), ("shadow_b","s_b"),
                       ("specular","s_sp"), ("rim","s_rm"), ("outline","s_ot")]:
            dpg.set_value(tag, material[k])

        update_shape()
        dpg.set_value("status", "Done!")
        print(f"[Infer] {preds[:6]}")
    except Exception as e:
        print(f"[Error] {e}")
        dpg.set_value("status", "Error")


def on_param(s, a, k):
    material[k] = a
    print(f"[Param] {k} = {a}")
    update_shape()


def load_model():
    global engine
    try:
        import onnxruntime as ort
        path = os.path.join(os.path.dirname(__file__), "..", "training", "mooatoon_model.onnx")
        if os.path.exists(path):
            engine = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
            print("[Model] Loaded")
    except Exception as e:
        print(f"[Model] {e}")


def make_param_callback(key):
    """创建参数回调函数"""
    def callback(s, a):
        material[key] = a
        print(f"[Param] {key} = {a:.3f}")
        update_shape()

        # 实时联动发送
        if realtime_sync and ws_client and ws_client.connected and not _updating_from_ue5:
            send_params_realtime()
    return callback


def build():
    dpg.create_context()
    dpg.create_viewport(title="AutoToon Studio - Skybox v2.0", width=950, height=720)

    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (25, 25, 28))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (40, 40, 45))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (55, 60, 70))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (70, 130, 200))
    dpg.bind_theme(t)

    with dpg.texture_registry():
        dpg.add_dynamic_texture(VIEWER_SIZE, VIEWER_SIZE, [0.1]*4*VIEWER_SIZE**2, tag="ref_tex")
        dpg.add_dynamic_texture(VIEWER_SIZE, VIEWER_SIZE, [0.1]*4*VIEWER_SIZE**2, tag="sphere_tex")

    # 参考图文件选择器
    with dpg.file_dialog(directory_selector=False, show=False, callback=on_file_select,
                        tag="fdlg", width=500, height=300):
        dpg.add_file_extension("Images{.png,.jpg,.jpeg,.bmp,.webp,.gif}", color=(80, 180, 220))

    # 自定义 Skybox 文件选择器
    with dpg.file_dialog(directory_selector=False, show=False, callback=on_custom_skybox_select,
                        tag="skybox_fdlg", width=500, height=300):
        dpg.add_file_extension("Images{.png,.jpg,.jpeg,.bmp,.webp}", color=(80, 180, 220))

    # 批量处理文件夹选择器
    with dpg.file_dialog(directory_selector=True, show=False, callback=on_batch_folder_select,
                        tag="batch_fdlg", width=500, height=300):
        pass

    with dpg.window(tag="main"):
        dpg.add_text("AutoToon Studio — Skybox v2.1 + UE5", color=(70, 140, 210))
        dpg.add_separator()

        with dpg.group(horizontal=True):
            # 左: 参考图
            with dpg.group():
                dpg.add_text("Reference", color=(140, 140, 150))
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Upload", callback=lambda: dpg.show_item("fdlg"), width=60)
                    dpg.add_button(label="Focus", callback=lambda: on_brush(1), width=50)
                    dpg.add_button(label="Ignore", callback=lambda: on_brush(2), width=55)
                    dpg.add_button(label="Clear", callback=on_clear, width=50)
                dpg.add_text("", tag="ref_path", color=(90, 90, 90))
                with dpg.drawlist(width=VIEWER_SIZE, height=VIEWER_SIZE):
                    dpg.draw_image("ref_tex", (0, 0), (VIEWER_SIZE, VIEWER_SIZE))
                with dpg.group(horizontal=True):
                    dpg.add_text("Brush:")
                    dpg.add_slider_int(tag="bsize", default_value=20, min_value=5, max_value=50, width=120,
                                      callback=lambda s,a: globals().__setitem__('brush_size', a))

                # UE5 Connection
                dpg.add_separator()
                dpg.add_text("UE5 Connection", color=(140, 140, 150))
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Check", callback=on_check_ue5, width=60)
                    dpg.add_button(label="Send", callback=on_send_ue5, width=60)
                    dpg.add_text("Disconnected ✗", tag="ue5_status", color=(200, 80, 80))

                # 实时联动区域
                dpg.add_separator()
                dpg.add_spacer(height=5)

                with dpg.group(horizontal=True):
                    dpg.add_checkbox(
                        label="Real-time Sync (WebSocket)",
                        tag="realtime_sync_checkbox",
                        default_value=False,
                        callback=on_realtime_sync_toggle
                    )

                with dpg.group(horizontal=True):
                    dpg.add_text("WebSocket:", color=(150, 150, 150))
                    dpg.add_text("Disabled", tag="ws_status", color=(150, 150, 150))

                # Compare View
                dpg.add_separator()
                dpg.add_text("Compare View", color=(140, 140, 150))
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Compare: OFF", tag="btn_compare", callback=toggle_compare_mode, width=90)
                    dpg.add_combo(items=SHAPE_NAMES, default_value=compare_shape_a, width=70,
                                  callback=on_compare_shape_a_change)
                    dpg.add_text("vs")
                    dpg.add_combo(items=SHAPE_NAMES, default_value=compare_shape_b, width=70,
                                  callback=on_compare_shape_b_change)

                # Batch Processing
                dpg.add_separator()
                dpg.add_text("Batch Process", color=(140, 140, 150))
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Select Folder", callback=lambda: dpg.show_item("batch_fdlg"), width=90)
                    dpg.add_button(label="Run", callback=on_batch_process, width=50)
                dpg.add_text("No folder selected", tag="batch_info", color=(100, 100, 100))

                # 截图和推理按钮
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Screenshot", callback=on_save_screenshot, width=90)
                    dpg.add_button(label="Extract", callback=on_infer, width=70)
                dpg.add_text("", tag="status", color=(80, 180, 80))

            dpg.add_spacer(width=15)

            # 右: 预览
            with dpg.group():
                dpg.add_text("Material Preview", color=(140, 140, 150))

                # Skybox 选择
                with dpg.group(horizontal=True):
                    dpg.add_text("Skybox:")
                    dpg.add_combo(
                        items=[s["name"] for s in SKYBOX_PRESETS],
                        default_value=SKYBOX_PRESETS[0]["name"],
                        tag="skybox_combo",
                        width=130,
                        callback=on_skybox_change
                    )
                    dpg.add_button(label="Load", callback=lambda: dpg.show_item("skybox_fdlg"), width=50)

                # Style presets
                with dpg.group(horizontal=True):
                    dpg.add_text("Preset:")
                    dpg.add_combo(items=get_style_presets(), tag="preset_combo", width=100, callback=on_load_preset)
                    dpg.add_input_text(tag="preset_name", hint="name", width=70)
                    dpg.add_button(label="Save", callback=on_save_preset, width=45)

                # Shape selection - split into two rows for 6 shapes
                with dpg.group():
                    with dpg.group(horizontal=True):
                        dpg.add_text("Shape:")
                        dpg.add_button(label="?", callback=on_about, width=20)
                    # Row 1: Sphere, Cube, Cylinder
                    with dpg.group(horizontal=True):
                        for i, shape in enumerate(SHAPE_NAMES[:3]):
                            label = SHAPE_LABELS.get(shape, shape)
                            is_selected = shape == current_shape
                            btn_color = (70, 140, 210) if is_selected else (50, 50, 55)
                            dpg.add_button(
                                label=label,
                                tag=f"shape_btn_{i}",
                                width=65,
                                callback=on_shape_change_by_index,
                                user_data=i
                            )
                            with dpg.theme(tag=f"shape_theme_{i}"):
                                with dpg.theme_component(dpg.mvButton):
                                    dpg.add_theme_color(dpg.mvThemeCol_Button, btn_color, category=dpg.mvThemeCat_Core)
                                    hover = (100, 180, 240) if is_selected else (70, 70, 75)
                                    dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, hover, category=dpg.mvThemeCat_Core)
                            dpg.bind_item_theme(f"shape_btn_{i}", f"shape_theme_{i}")
                    # Row 2: Torus, Cone, Icosa
                    with dpg.group(horizontal=True):
                        for i, shape in enumerate(SHAPE_NAMES[3:], start=3):
                            label = SHAPE_LABELS.get(shape, shape)
                            is_selected = shape == current_shape
                            btn_color = (70, 140, 210) if is_selected else (50, 50, 55)
                            dpg.add_button(
                                label=label,
                                tag=f"shape_btn_{i}",
                                width=65,
                                callback=on_shape_change_by_index,
                                user_data=i
                            )
                            with dpg.theme(tag=f"shape_theme_{i}"):
                                with dpg.theme_component(dpg.mvButton):
                                    dpg.add_theme_color(dpg.mvThemeCol_Button, btn_color, category=dpg.mvThemeCat_Core)
                                    hover = (100, 180, 240) if is_selected else (70, 70, 75)
                                    dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, hover, category=dpg.mvThemeCat_Core)
                            dpg.bind_item_theme(f"shape_btn_{i}", f"shape_theme_{i}")

                # Preview mode selection
                with dpg.group(horizontal=True):
                    dpg.add_text("Preview:")
                    dpg.add_combo(
                        items=list(PREVIEW_MODE_LABELS.values()),
                        default_value=PREVIEW_MODE_LABELS["single"],
                        tag="preview_mode_combo",
                        width=100,
                        callback=lambda s, a: on_preview_mode_change(s, [k for k, v in PREVIEW_MODE_LABELS.items() if v == a][0])
                    )

                dpg.add_text(SKYBOX_PRESETS[0]["desc"], tag="skybox_name", color=(100, 100, 100))

                # Camera control section
                dpg.add_separator()
                dpg.add_text("Camera Control", color=(110, 140, 180))
                with dpg.group(horizontal=True):
                    dpg.add_text("Pitch:")
                    dpg.add_slider_float(
                        tag="cam_pitch",
                        default_value=0.0,
                        min_value=-90.0,
                        max_value=90.0,
                        width=120,
                        callback=on_camera_pitch
                    )
                with dpg.group(horizontal=True):
                    dpg.add_text("Yaw:")
                    dpg.add_slider_float(
                        tag="cam_yaw",
                        default_value=0.0,
                        min_value=0.0,
                        max_value=360.0,
                        width=120,
                        callback=on_camera_yaw
                    )
                with dpg.group(horizontal=True):
                    dpg.add_text("Roll:")
                    dpg.add_slider_float(
                        tag="cam_roll",
                        default_value=0.0,
                        min_value=-180.0,
                        max_value=180.0,
                        width=120,
                        callback=on_camera_roll
                    )
                with dpg.group(horizontal=True):
                    dpg.add_text("Zoom:")
                    dpg.add_slider_float(
                        tag="cam_dist",
                        default_value=1.0,
                        min_value=0.5,
                        max_value=2.0,
                        width=120,
                        callback=on_camera_distance
                    )
                dpg.add_text("(Mouse: L-drag=Rotate, R-drag=Pan, Scroll=Zoom)", color=(70, 70, 70))

                dpg.add_separator()

                # Auto rotation control
                dpg.add_text("Auto Rotation", color=(110, 140, 180))
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Auto: OFF", tag="btn_rotate", callback=on_auto_rotate, width=80)
                    dpg.add_slider_float(
                        label="Speed",
                        tag="rot_speed",
                        default_value=30.0,
                        min_value=5.0,
                        max_value=120.0,
                        width=100,
                        callback=on_rotation_speed
                    )

                with dpg.drawlist(width=VIEWER_SIZE, height=VIEWER_SIZE):
                    dpg.draw_image("sphere_tex", (0, 0), (VIEWER_SIZE, VIEWER_SIZE))

                dpg.add_separator()
                dpg.add_text("Parameters", color=(110, 110, 120))

                # 使用 make_param_callback 创建正确的回调
                params_config = [
                    ("Shadow R", "s_r", "shadow_r", 0, 1, False),
                    ("Shadow G", "s_g", "shadow_g", 0, 1, False),
                    ("Shadow B", "s_b", "shadow_b", 0, 1, False),
                    ("Specular", "s_sp", "specular", 0, 1.5, False),
                    ("Rim Light", "s_rm", "rim", 0, 1.5, False),
                    ("Outline", "s_ot", "outline", 0, 5, False),
                    ("Shade Lv", "s_lv", "levels", 2, 4, True),
                ]

                for label, tag, key, mn, mx, is_int in params_config:
                    with dpg.group(horizontal=True):
                        dpg.add_text(f"{label}:")
                        if is_int:
                            dpg.add_slider_int(
                                tag=tag,
                                default_value=int(material[key]),
                                min_value=int(mn),
                                max_value=int(mx),
                                width=130,
                                callback=make_param_callback(key)
                            )
                        else:
                            dpg.add_slider_float(
                                tag=tag,
                                default_value=material[key],
                                min_value=mn,
                                max_value=mx,
                                width=130,
                                callback=make_param_callback(key)
                            )

                # Advanced material parameters
                dpg.add_separator()
                dpg.add_text("Advanced", color=(110, 110, 120))
                adv_params = [
                    ("SSS", "s_sss", "sss", 0, 1, False),
                    ("Aniso", "s_aniso", "aniso", 0, 1, False),
                    ("Metallic", "s_metal", "metallic", 0, 1, False),
                    ("Roughness", "s_rough", "roughness", 0, 1, False),
                ]

                for label, tag, key, mn, mx, is_int in adv_params:
                    with dpg.group(horizontal=True):
                        dpg.add_text(f"{label}:")
                        dpg.add_slider_float(
                            tag=tag,
                            default_value=material[key],
                            min_value=mn,
                            max_value=mx,
                            width=130,
                            callback=make_param_callback(key)
                        )

        dpg.add_spacer(height=5)

        # Reset and Random buttons
        with dpg.group(horizontal=True):
            dpg.add_button(label="Reset Cam", callback=reset_camera, width=75)
            dpg.add_button(label="Reset Mat", callback=reset_material, width=75)
            dpg.add_button(label="Random!", callback=on_randomize, width=70)

        dpg.add_text("Shortcuts: 1-6=Shapes, R=Reset Cam, M=Reset Mat, Space=Auto", color=(70, 70, 70))

    with dpg.handler_registry():
        # Brush drag on reference image
        dpg.add_mouse_drag_handler(button=0, callback=on_mouse_drag)
        # Camera control - use mouse click and drag handlers
        dpg.add_mouse_click_handler(button=0, callback=on_mouse_down)  # Left click
        dpg.add_mouse_click_handler(button=1, callback=on_mouse_down)  # Right click
        dpg.add_mouse_release_handler(callback=on_mouse_up)  # Release any button
        dpg.add_mouse_move_handler(callback=on_mouse_move)
        dpg.add_mouse_wheel_handler(callback=on_mouse_wheel)
        # Keyboard shortcuts
        dpg.add_key_press_handler(callback=on_key_press)

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main", True)


def run():
    print("=" * 50)
    print("AutoToon Studio - Skybox Version 2.0")
    print("  9 Skybox Presets + Custom Image Support")
    print("  6 Shape Types: Sphere, Cube, Cylinder, Torus, Cone, Icosa")
    print("  Advanced: SSS, Anisotropic, Metallic, Roughness")
    print("  Controls: Mouse drag, Scroll, Keyboard shortcuts")
    print("=" * 50)
    load_model()
    build()
    update_shape()
    print("\n[Ready]\n")

    last_time = time.time()
    frame_count = 0

    while dpg.is_dearpygui_running():
        current_time = time.time()
        delta_time = current_time - last_time
        last_time = current_time

        # Auto rotation - limit update rate for performance
        if auto_rotate:
            global rotation_angle
            rotation_angle += rotation_speed * delta_time
            if rotation_angle >= 360.0:
                rotation_angle -= 360.0
            # Sync angle slider (only every few frames to reduce UI overhead)
            frame_count += 1
            if frame_count % 3 == 0:
                if dpg.does_item_exist("rot_angle"):
                    dpg.set_value("rot_angle", rotation_angle)
                update_shape()

        dpg.render_dearpygui_frame()

    dpg.destroy_context()


if __name__ == "__main__":
    run()