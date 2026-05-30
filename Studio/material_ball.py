"""
material_ball.py — 可 360° 旋转的材质球渲染器
操作方式（仿 Blender）：
  中键拖拽 = 轨道旋转（Orbit）
  滚轮    = 缩放（Zoom）
  左键拖拽 = 平移（Pan）
  双击    = 重置视角
"""
import numpy as np
import cv2

SIZE = 384


# ─── 灯光/材质参数 ───────────────────────────────────────────────────────────────
class LightParams:
    def __init__(self):
        self.ambient = 0.25
        self.diffuse = 0.80
        self.specular_power = 40
        self.specular_intensity = 0.35
        self.rim_intensity = 0.15
        self.rim_power = 3.0
        self.light_dir = (0.4, -0.5, 0.7)
        self.fill_dir = (-0.3, 0.2, 0.5)
        self.ground_shadow = 0.25


# ─── 相机状态 ────────────────────────────────────────────────────────────────────
class Camera:
    def __init__(self):
        self.yaw = 25.0      # 水平旋转角度（度）
        self.pitch = -15.0   # 垂直旋转角度（度）
        self.zoom = 1.0      # 缩放倍率
        self.pan_x = 0.0     # 平移 X
        self.pan_y = 0.0     # 平移 Y

    def reset(self):
        self.yaw, self.pitch = 25.0, -15.0
        self.zoom = 1.0
        self.pan_x, self.pan_y = 0.0, 0.0

    def rotation_matrix(self):
        """返回 (3x3) 旋转矩阵：先绕 Y 轴（yaw），再绕 X 轴（pitch）"""
        cy, sy = np.cos(np.radians(self.yaw)), np.sin(np.radians(self.yaw))
        cp, sp = np.cos(np.radians(self.pitch)), np.sin(np.radians(self.pitch))
        Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
        return Ry @ Rx

    def inverse_rotation(self):
        """返回逆旋转矩阵：将屏幕坐标转回物体本地空间"""
        return self.rotation_matrix().T


# ─── 光线-形状求交 ────────────────────────────────────────────────────────────────
# 每个函数输入: 本地空间射线原点(ox,oy,oz) + 方向(dx,dy,dz), 全是 (S,S) 数组
# 返回: (nx, ny, nz, mask)  本地空间法线 + 命中掩码


def _ray_sphere(ox, oy, oz, dx, dy, dz, r):
    """光线-球体求交（解析法）"""
    # a·t² + 2b·t + c = 0
    a = dx * dx + dy * dy + dz * dz
    b = ox * dx + oy * dy + oz * dz
    c = ox * ox + oy * oy + oz * oz - r * r
    disc = b * b - a * c
    hit = disc >= 0
    sqrt_disc = np.sqrt(np.maximum(disc, 0))
    t = (-b - sqrt_disc) / np.where(a > 0, a, 1)
    t = np.where(hit & (t > 0.001), t, 0)
    hx = ox + dx * t
    hy = oy + dy * t
    hz = oz + dz * t
    inv_r = 1.0 / r
    return hx * inv_r, hy * inv_r, hz * inv_r, hit


def _ray_cube(ox, oy, oz, dx, dy, dz, s):
    """光线-AABB 立方体求交（slab method）"""
    inv = np.where((dx != 0) & (dy != 0) & (dz != 0), 1.0, 1e10)
    idx = np.where(dx != 0, 1.0 / np.where(dx != 0, dx, 1), inv)
    idy = np.where(dy != 0, 1.0 / np.where(dy != 0, dy, 1), inv)
    idz = np.where(dz != 0, 1.0 / np.where(dz != 0, dz, 1), inv)

    t1x = (-s - ox) * idx
    t2x = ( s - ox) * idx
    t1y = (-s - oy) * idy
    t2y = ( s - oy) * idy
    t1z = (-s - oz) * idz
    t2z = ( s - oz) * idz

    tmin = np.maximum(np.minimum(t1x, t2x),
           np.maximum(np.minimum(t1y, t2y),
                      np.minimum(t1z, t2z)))
    tmax = np.minimum(np.maximum(t1x, t2x),
           np.minimum(np.maximum(t1y, t2y),
                      np.maximum(t1z, t2z)))

    hit = (tmax >= np.maximum(tmin, 0.001))
    t = np.where(hit, tmin, 0)

    hx = ox + dx * t
    hy = oy + dy * t
    hz = oz + dz * t

    # 法线 = 命中的面方向
    eps = 1e-4
    nx = np.where(np.abs(hx + s) < eps, -1.0,
       np.where(np.abs(hx - s) < eps,  1.0, 0.0))
    ny = np.where(np.abs(hy + s) < eps, -1.0,
       np.where(np.abs(hy - s) < eps,  1.0, 0.0))
    nz = np.where(np.abs(hz + s) < eps, -1.0,
       np.where(np.abs(hz - s) < eps,  1.0, 0.0))
    return nx, ny, nz, hit


def _ray_cylinder(ox, oy, oz, dx, dy, dz, rw, rh):
    """光线-圆柱体求交（侧面 + 顶底盖，Y 轴为高）"""
    mask = np.zeros(ox.shape, dtype=bool)
    t_best = np.full(ox.shape, 1e10)

    # ---- 侧面: x² + z² = rw² ----
    a = dx * dx + dz * dz
    b = ox * dx + oz * dz
    c = ox * ox + oz * oz - rw * rw
    disc = b * b - a * c
    sd = disc >= 0
    sq = np.sqrt(np.maximum(disc, 0))
    ts1 = (-b - sq) / np.where(a > 0, a, 1)
    ts2 = (-b + sq) / np.where(a > 0, a, 1)
    h1 = sd & (ts1 > 0.001)
    y1 = oy + dy * ts1
    side1 = h1 & (np.abs(y1) <= rh) & (ts1 < t_best)
    t_best = np.where(side1, ts1, t_best)
    mask |= side1
    h2 = sd & (ts2 > 0.001)
    y2 = oy + dy * ts2
    side2 = h2 & (np.abs(y2) <= rh) & (ts2 < t_best) & ~side1
    t_best = np.where(side2, ts2, t_best)
    mask |= side2

    # ---- 顶盖 y = rh ----
    if np.abs(dy).max() > 1e-8:
        t_top = (rh - oy) / np.where(np.abs(dy) > 1e-8, dy, 1)
        tx = ox + dx * t_top
        tz = oz + dz * t_top
        top_hit = (t_top > 0.001) & (tx * tx + tz * tz <= rw * rw) & (t_top < t_best)
        t_best = np.where(top_hit, t_top, t_best)
        mask |= top_hit

    # ---- 底盖 y = -rh ----
    if np.abs(dy).max() > 1e-8:
        t_bot = (-rh - oy) / np.where(np.abs(dy) > 1e-8, dy, 1)
        tx = ox + dx * t_bot
        tz = oz + dz * t_bot
        bot_hit = (t_bot > 0.001) & (tx * tx + tz * tz <= rw * rw) & (t_bot < t_best)
        t_best = np.where(bot_hit, t_bot, t_best)
        mask |= bot_hit

    t = np.where(mask, t_best, 0)
    hx = ox + dx * t
    hy = oy + dy * t
    hz = oz + dz * t

    # 法线
    rlen = np.sqrt(hx * hx + hz * hz)
    on_side = np.abs(np.abs(hy) - rh) > 0.01
    inv_r = np.where(rlen > 0, 1.0 / rlen, 0.0)
    nx = np.where(mask & on_side, hx * inv_r, 0.0)
    ny = np.where(mask & ~on_side, np.where(hy > 0, 1.0, -1.0), 0.0)
    nz = np.where(mask & on_side, hz * inv_r, 0.0)
    return nx, ny, nz, mask


def _ray_torus(ox, oy, oz, dx, dy, dz, R, r):
    """光线-圆环体求交（SDF ray marching）"""
    MAX_STEPS = 80
    MIN_DIST = 0.002
    MAX_DIST = 4.0

    t = np.full(ox.shape, 0.5)  # 从原点沿射线的距离
    alive = np.ones(ox.shape, dtype=bool)

    for _ in range(MAX_STEPS):
        px = ox + dx * t
        py = oy + dy * t
        pz = oz + dz * t
        # torus SDF: (sqrt(x²+z²) - R)² + y² - r²
        hlen = np.sqrt(px * px + pz * pz)
        sdf = np.sqrt((hlen - R) ** 2 + py * py) - r

        done = sdf < MIN_DIST
        escaped = t > MAX_DIST
        alive = alive & ~done & ~escaped
        t = np.where(alive, t + np.maximum(sdf * 0.8, MIN_DIST), t)
        if not alive.any():
            break

    hit = ~alive & (t <= MAX_DIST) & (t > 0.001)
    t = np.where(hit, t, 0)
    hx = ox + dx * t
    hy = oy + dy * t
    hz = oz + dz * t

    # 法线 = SDF 梯度（中心差分）
    eps = 0.003

    def _sdf_at(px, py, pz):
        hh = np.sqrt(px * px + pz * pz)
        return np.sqrt((hh - R) ** 2 + py * py) - r

    gx = (_sdf_at(hx + eps, hy, hz) - _sdf_at(hx - eps, hy, hz)) / (2 * eps)
    gy = (_sdf_at(hx, hy + eps, hz) - _sdf_at(hx, hy - eps, hz)) / (2 * eps)
    gz = (_sdf_at(hx, hy, hz + eps) - _sdf_at(hx, hy, hz - eps)) / (2 * eps)
    glen = np.sqrt(gx * gx + gy * gy + gz * gz)
    glen = np.where(glen > 0, glen, 1)
    nx = np.where(hit, gx / glen, 0.0)
    ny = np.where(hit, gy / glen, 0.0)
    nz = np.where(hit, gz / glen, 0.0)
    return nx, ny, nz, hit


SHAPES = {
    "sphere":   lambda ox, oy, oz, dx, dy, dz: _ray_sphere(ox, oy, oz, dx, dy, dz, 0.85),
    "cube":     lambda ox, oy, oz, dx, dy, dz: _ray_cube(ox, oy, oz, dx, dy, dz, 0.80),
    "cylinder": lambda ox, oy, oz, dx, dy, dz: _ray_cylinder(ox, oy, oz, dx, dy, dz, 0.55, 0.85),
    "torus":    lambda ox, oy, oz, dx, dy, dz: _ray_torus(ox, oy, oz, dx, dy, dz, 0.60, 0.30),
}


# ─── 渲染 ────────────────────────────────────────────────────────────────────────
def render_ball(shape_name: str, light: LightParams, camera: Camera = None,
                style_color=(0.65, 0.65, 0.65),
                style_specular_boost: float = 0.0,
                style_rim_boost: float = 0.0,
                size: int = 0) -> np.ndarray:
    """渲染材质球，支持任意角度旋转"""
    if camera is None:
        camera = Camera()

    S = size if size > 0 else SIZE
    img = np.full((S, S, 3), [28, 28, 30], np.float32)

    # 屏幕坐标 → 归一化设备坐标 (-1 ~ 1)
    yy, xx = np.mgrid[:S, :S].astype(np.float32)
    ndc_x = (xx - S / 2 + camera.pan_x) / (S / 2) / camera.zoom
    ndc_y = (yy - S / 2 + camera.pan_y) / (S / 2) / camera.zoom

    # 构建本地空间射线
    R_inv = camera.inverse_rotation()
    # 射线原点: 相机在本地空间的位置 (z=0 平面沿视线方向)
    flat_origin = np.stack([ndc_x.ravel(), ndc_y.ravel(), np.zeros_like(ndc_x.ravel())])
    local_origin = R_inv @ flat_origin  # (3, N)
    # 射线方向: 沿本地空间 -Z（视线方向）
    ray_dir_world = np.array([0, 0, -1.0])
    local_dir = R_inv @ ray_dir_world  # (3,)

    ox = local_origin[0].reshape(S, S)
    oy = local_origin[1].reshape(S, S)
    oz = local_origin[2].reshape(S, S)
    dx = np.full_like(ox, local_dir[0])
    dy = np.full_like(ox, local_dir[1])
    dz = np.full_like(ox, local_dir[2])

    # 光线求交（本地空间法线）
    fn = SHAPES.get(shape_name, SHAPES["sphere"])
    nx_local, ny_local, nz_local, mask = fn(ox, oy, oz, dx, dy, dz)

    if not mask.any():
        return img.astype(np.uint8)

    # 法线旋转回世界空间
    R = camera.rotation_matrix()
    nx = R[0, 0] * nx_local + R[0, 1] * ny_local + R[0, 2] * nz_local
    ny = R[1, 0] * nx_local + R[1, 1] * ny_local + R[1, 2] * nz_local
    nz = R[2, 0] * nx_local + R[2, 1] * ny_local + R[2, 2] * nz_local

    # 灯光方向
    lx1, ly1, lz1 = light.light_dir
    nl1 = (lx1**2 + ly1**2 + lz1**2) ** 0.5
    lx1, ly1, lz1 = lx1 / nl1, ly1 / nl1, lz1 / nl1

    lx2, ly2, lz2 = light.fill_dir
    nl2 = (lx2**2 + ly2**2 + lz2**2) ** 0.5
    lx2, ly2, lz2 = lx2 / nl2, ly2 / nl2, lz2 / nl2

    # 漫反射
    diff1 = np.clip(nx * lx1 + ny * ly1 + nz * lz1, 0, 1)
    diff2 = np.clip(nx * lx2 + ny * ly2 + nz * lz2, 0, 1)
    diffuse = np.clip(light.ambient + light.diffuse * (diff1 * 0.75 + diff2 * 0.25), 0, 1)

    # Blinn-Phong 高光
    hx, hy, hz = (lx1 + 0) / 2, (ly1 + 0) / 2, (lz1 + 1) / 2
    hn = np.sqrt(hx**2 + hy**2 + hz**2)
    spec_dot = np.clip((nx * hx / hn + ny * hy / hn + nz * hz / hn), 0, 1)
    spec_pow = light.specular_power + style_specular_boost * 30
    specular = spec_dot ** spec_pow * (light.specular_intensity + style_specular_boost * 0.2)

    # Fresnel 边缘光
    rim = np.clip(1.0 - nz, 0, 1) ** light.rim_power * (light.rim_intensity + style_rim_boost * 0.15)

    # 合成
    br, bg, bb = style_color
    for c, base in enumerate([br, bg, bb]):
        ch = np.clip(base * diffuse + specular + rim * (0.05 + c * 0.02), 0, 1)
        img[:, :, c] = np.where(mask, ch * 255, img[:, :, c])

    # 地面阴影
    if light.ground_shadow > 0.01:
        shadow_cy = S * 0.5 + S * 0.35 / camera.zoom + camera.pan_y
        sy = np.arange(S).reshape(-1, 1)
        sx = np.arange(S).reshape(1, -1)
        sd = np.sqrt(((sx - S/2 - camera.pan_x) * 0.5) ** 2 + (sy - shadow_cy) ** 2)
        sa = np.clip(light.ground_shadow * (1 - sd / (S * 0.25)), 0, 0.5)
        valid = sd < S * 0.25
        for c in range(3):
            img[:, :, c] = np.where(valid, img[:, :, c] * (1 - sa), img[:, :, c])

    return img.astype(np.uint8)
