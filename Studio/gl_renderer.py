"""
gl_renderer.py — ModernGL GPU 渲染器（替换 material_ball 软件渲染）
Phong 着色 + framebuffer 离屏渲染 → numpy 数组 → DearPyGui 纹理
"""
import numpy as np
import moderngl


# ─── 网格生成 ────────────────────────────────────────────────────────────────────

def _gen_sphere(subdivisions=8):
    """UV 球体 (纬度/经度细分)"""
    st, sphi = max(2, subdivisions * 4), max(4, subdivisions * 8)
    verts, idx = [], []
    for i in range(st + 1):
        theta = np.pi * i / st
        sin_t, cos_t = np.sin(theta), np.cos(theta)
        for j in range(sphi + 1):
            phi = 2 * np.pi * j / sphi
            sin_p, cos_p = np.sin(phi), np.cos(phi)
            x, y, z = sin_t * cos_p, cos_t, sin_t * sin_p
            verts.extend([x * 0.85, y * 0.85, z * 0.85, x, y, z])
    for i in range(st):
        for j in range(sphi):
            a, b = i * (sphi + 1) + j, i * (sphi + 1) + j + 1
            c, d = (i + 1) * (sphi + 1) + j, (i + 1) * (sphi + 1) + j + 1
            idx.extend([a, c, b, b, c, d])
    return np.array(verts, 'f4'), np.array(idx, 'i4')


def _gen_cube():
    """立方体 (24 顶点, 每面独立法线)"""
    hs = 0.80
    f = [
        ([-1,0,0], [[-hs,-hs, hs],[-hs,-hs,-hs],[-hs, hs,-hs],[-hs, hs, hs]]),
        ([ 1,0,0], [[ hs,-hs,-hs],[ hs,-hs, hs],[ hs, hs, hs],[ hs, hs,-hs]]),
        ([0,-1,0], [[-hs,-hs,-hs],[ hs,-hs,-hs],[ hs,-hs, hs],[-hs,-hs, hs]]),
        ([0, 1,0], [[-hs, hs, hs],[ hs, hs, hs],[ hs, hs,-hs],[-hs, hs,-hs]]),
        ([0,0,-1], [[-hs,-hs,-hs],[-hs, hs,-hs],[ hs, hs,-hs],[ hs,-hs,-hs]]),
        ([0,0, 1], [[ hs,-hs, hs],[ hs, hs, hs],[-hs, hs, hs],[-hs,-hs, hs]]),
    ]
    v, idx = [], []
    for i, (n, corners) in enumerate(f):
        for c in corners:
            v.extend(c + n)
        idx.extend([i*4, i*4+1, i*4+2, i*4, i*4+2, i*4+3])
    return np.array(v, 'f4'), np.array(idx, 'i4')


def _gen_cylinder(seg=48):
    """圆柱体 (Y 轴, 侧面+顶底盖)"""
    R, H = 0.55, 0.85
    v, idx = [], []
    # 侧面
    for i in range(seg + 1):
        a = 2 * np.pi * i / seg
        cs, sn = np.cos(a) * R, np.sin(a) * R
        nx, nz = np.cos(a), np.sin(a)
        v.extend([cs, -H, sn, nx, 0, nz, cs, H, sn, nx, 0, nz])
    for i in range(seg):
        b = i * 2
        idx.extend([b, b+2, b+1, b+1, b+2, b+3])
    n = (seg + 1) * 2
    # 顶盖
    v.extend([0, H, 0, 0, 1, 0])
    for i in range(seg + 1):
        a = 2 * np.pi * i / seg
        v.extend([np.cos(a)*R, H, np.sin(a)*R, 0, 1, 0])
    for i in range(seg):
        idx.extend([n, n+1+i, n+1+i+1])
    n += seg + 2
    # 底盖
    v.extend([0, -H, 0, 0, -1, 0])
    for i in range(seg + 1):
        a = 2 * np.pi * i / seg
        v.extend([np.cos(a)*R, -H, np.sin(a)*R, 0, -1, 0])
    for i in range(seg):
        idx.extend([n, n+1+i+1, n+1+i])
    return np.array(v, 'f4'), np.array(idx, 'i4')


def _gen_torus(seg_major=64, seg_minor=32):
    """圆环体 (SDF-style, major R=0.60, minor r=0.30)"""
    R, r = 0.60, 0.30
    v, idx = [], []
    for i in range(seg_major + 1):
        theta = 2 * np.pi * i / seg_major
        ct, st = np.cos(theta), np.sin(theta)
        for j in range(seg_minor + 1):
            phi = 2 * np.pi * j / seg_minor
            cp, sp = np.cos(phi), np.sin(phi)
            px = (R + r * cp) * ct
            py = r * sp
            pz = (R + r * cp) * st
            nx, ny, nz = cp * ct, sp, cp * st
            v.extend([px, py, pz, nx, ny, nz])
    for i in range(seg_major):
        for j in range(seg_minor):
            a = i * (seg_minor + 1) + j
            b = a + 1
            c = (i + 1) * (seg_minor + 1) + j
            d = c + 1
            idx.extend([a, c, b, b, c, d])
    return np.array(v, 'f4'), np.array(idx, 'i4')


# ─── 着色器 ──────────────────────────────────────────────────────────────────────

VERT = """
#version 330
in vec3 in_pos;
in vec3 in_norm;
uniform mat4 mvp;
out vec3 v_norm;
out vec3 v_pos;
void main() {
    gl_Position = mvp * vec4(in_pos, 1.0);
    v_norm = normalize(in_norm);
    v_pos = in_pos;
}
"""

FRAG = """
#version 330
in vec3 v_norm;
in vec3 v_pos;
uniform vec3 u_light_dir;
uniform vec3 u_fill_dir;
uniform vec3 u_color;
uniform float u_ambient;
uniform float u_diffuse;
uniform float u_spec_pow;
uniform float u_spec_int;
uniform float u_rim_int;
uniform float u_rim_pow;
uniform vec3 u_cam_pos;
out vec4 frag_color;
void main() {
    vec3 N = normalize(v_norm);
    vec3 V = normalize(u_cam_pos - v_pos);

    // 主光
    vec3 L1 = normalize(u_light_dir);
    float d1 = max(dot(N, L1), 0.0);

    // 补光
    vec3 L2 = normalize(u_fill_dir);
    float d2 = max(dot(N, L2), 0.0);

    float diff = clamp(u_ambient + u_diffuse * (d1 * 0.75 + d2 * 0.25), 0.0, 1.0);

    // Blinn-Phong 高光
    vec3 H = normalize(L1 + V);
    float spec = pow(max(dot(N, H), 0.0), u_spec_pow) * u_spec_int;

    // Fresnel 边缘光
    float rim = pow(1.0 - max(dot(N, V), 0.0), u_rim_pow) * u_rim_int;

    vec3 c = u_color * diff + spec + rim * vec3(0.07, 0.08, 0.12);
    frag_color = vec4(clamp(c, 0.0, 1.0), 1.0);
}
"""


# ─── 相机 ────────────────────────────────────────────────────────────────────────

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


class Camera:
    def __init__(self):
        self.yaw = 25.0
        self.pitch = -15.0
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0

    def reset(self):
        self.yaw, self.pitch = 25.0, -15.0
        self.zoom = 1.0
        self.pan_x, self.pan_y = 0.0, 0.0

    def view_matrix(self):
        dist = 3.0 / self.zoom
        cy, sy = np.cos(np.radians(self.yaw)), np.sin(np.radians(self.yaw))
        cp, sp = np.cos(np.radians(self.pitch)), np.sin(np.radians(self.pitch))
        eye = np.array([dist * cy * cp, dist * sp, dist * sy * cp], dtype='f4')
        up = np.array([0, 1, 0], dtype='f4')
        f = -eye / np.linalg.norm(eye)
        r = np.cross(f, up)
        r /= np.linalg.norm(r) + 1e-10
        u = np.cross(r, f)
        M = np.eye(4, dtype='f4')
        M[0, :3], M[1, :3], M[2, :3] = r, u, -f
        M[:3, 3] = -M[:3, :3] @ eye
        return M

    def proj_matrix(self, aspect=1.0):
        fov, near, far = 45.0, 0.1, 50.0
        t = np.tan(np.radians(fov) / 2)
        P = np.zeros((4, 4), dtype='f4')
        P[0, 0] = 1 / (aspect * t)
        P[1, 1] = 1 / t
        P[2, 2] = -(far + near) / (far - near)
        P[2, 3] = -2 * far * near / (far - near)
        P[3, 2] = -1
        return P


# ─── 渲染器 ──────────────────────────────────────────────────────────────────────

class GLRenderer:
    """ModernGL 离屏渲染器"""

    def __init__(self, width=380, height=380):
        self.w, self.h = width, height
        # 创建 OpenGL 上下文
        try:
            self.ctx = moderngl.create_standalone_context()
        except Exception:
            import glfw
            glfw.init()
            glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
            _w = glfw.create_window(1, 1, "", None, None)
            self.ctx = moderngl.create_standalone_context()
            glfw.destroy_window(_w)
            glfw.terminate()
        self.ctx.enable(moderngl.DEPTH_TEST)

        # 编译着色器
        self.prog = self.ctx.program(
            vertex_shader=VERT, fragment_shader=FRAG,
        )

        # 创建 mesh
        self.meshes = {}
        for name, fn in [
            ("sphere", _gen_sphere),
            ("cube", _gen_cube),
            ("cylinder", _gen_cylinder),
            ("torus", _gen_torus),
        ]:
            vi, ii = fn()
            self.meshes[name] = (
                self.ctx.buffer(vi.tobytes()),
                self.ctx.buffer(ii.tobytes()),
                len(ii),
            )

        # framebuffer
        self._create_fbo(width, height)

    def _create_fbo(self, w, h):
        if hasattr(self, 'fbo'):
            self.fbo.release()
            self.color.release()
            self.depth.release()
        self.w, self.h = w, h
        self.color = self.ctx.texture((w, h), 4)
        self.depth = self.ctx.depth_renderbuffer((w, h))
        self.fbo = self.ctx.framebuffer(color_attachments=[self.color],
                                         depth_attachment=self.depth)

    def render(self, shape, camera, light, color=(0.65, 0.65, 0.65),
               spec_boost=0.0, rim_boost=0.0, width=0, height=0) -> np.ndarray:
        """渲染到 framebuffer，返回 RGB numpy 数组"""
        rw = width if width > 0 else self.w
        rh = height if height > 0 else self.h
        if rw != self.w or rh != self.h:
            self._create_fbo(rw, rh)

        vbuf, ibuf, icnt = self.meshes.get(shape, self.meshes["sphere"])

        vao = self.ctx.vertex_array(self.prog, [
            (vbuf, '3f 3f', 'in_pos', 'in_norm'),
        ], ibuf)

        # MVP
        mvp = camera.proj_matrix(1.0) @ camera.view_matrix()
        self.prog['mvp'].write(mvp.tobytes())

        # 灯光参数
        d = light.light_dir
        self.prog['u_light_dir'].value = (d[0], d[1], d[2])
        d2 = light.fill_dir
        self.prog['u_fill_dir'].value = (d2[0], d2[1], d2[2])

        self.prog['u_color'].value = color
        self.prog['u_ambient'].value = light.ambient
        self.prog['u_diffuse'].value = light.diffuse
        self.prog['u_spec_pow'].value = light.specular_power + spec_boost * 30
        self.prog['u_spec_int'].value = light.specular_intensity + spec_boost * 0.2
        self.prog['u_rim_int'].value = light.rim_intensity + rim_boost * 0.15
        self.prog['u_rim_pow'].value = light.rim_power

        dist = 3.0 / camera.zoom
        cy, sy = np.cos(np.radians(camera.yaw)), np.sin(np.radians(camera.yaw))
        cp, sp = np.cos(np.radians(camera.pitch)), np.sin(np.radians(camera.pitch))
        self.prog['u_cam_pos'].value = (dist * cy * cp, dist * sp, dist * sy * cp)

        # 渲染
        self.fbo.use()
        self.fbo.clear(28/255, 28/255, 30/255, 1.0)
        vao.render(moderngl.TRIANGLES)
        vao.release()

        # 读取像素 → numpy
        data = self.fbo.read(components=4)
        img = np.frombuffer(data, dtype='u1').reshape(rh, rw, 4)
        img = np.flipud(img)  # OpenGL 底朝上 → 顶朝下
        # OpenGL RGB → OpenCV BGR（供 ImageViewer 使用）
        return img[:, :, [2, 1, 0]].copy()

    def cleanup(self):
        for vbuf, ibuf, _ in self.meshes.values():
            vbuf.release()
            ibuf.release()
        self.fbo.release()
        self.color.release()
        self.depth.release()
        self.prog.release()
        self.ctx.release()
