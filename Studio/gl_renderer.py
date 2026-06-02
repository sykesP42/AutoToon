"""
gl_renderer.py — ModernGL GPU 渲染器

工业级卡通风格渲染器，用于实时预览材质球效果。
支持 MSAA 抗锯齿、离散色阶光照、边缘描边等特性。

Author: AutoToon Team
License: MIT
"""
from __future__ import annotations

import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Tuple, Dict, Any, Optional

# 配置日志
logger = logging.getLogger(__name__)

# 尝试导入 moderngl
try:
    import moderngl
except ImportError as e:
    logger.error("moderngl 未安装，请运行: pip install moderngl")
    raise ImportError("moderngl is required for GPU rendering") from e


# =============================================================================
# 配置常量
# =============================================================================

# 渲染器默认配置
DEFAULT_WIDTH = 380
DEFAULT_HEIGHT = 380
DEFAULT_MSAA_SAMPLES = 2  # 1, 2, 4; 2 是性能与质量的平衡点
MAX_TEXTURE_SIZE = 1024   # 最大纹理尺寸限制

# 网格细分配置
MESH_SUBDIVISIONS = {
    "sphere": 8,
    "cylinder": 48,
    "torus_major": 64,
    "torus_minor": 32,
}

# 形状预设视角 (yaw, pitch, zoom)
SHAPE_PRESETS: Dict[str, Tuple[float, float, float]] = {
    "sphere":   (25.0, -15.0, 1.2),
    "cube":     (30.0, -20.0, 1.0),
    "cylinder": (25.0, -10.0, 1.1),
    "torus":    (45.0, -25.0, 1.0),
}

# 相机参数限制
CAMERA_ZOOM_MIN = 0.2
CAMERA_ZOOM_MAX = 5.0
CAMERA_PITCH_MIN = -89.0
CAMERA_PITCH_MAX = 89.0


# =============================================================================
# 着色器源码
# =============================================================================

VERTEX_SHADER = """
#version 330
in vec3 in_pos;
in vec3 in_norm;

uniform mat4 u_mvp;
uniform mat4 u_model;
uniform vec3 u_cam_pos;

out vec3 v_norm;
out vec3 v_world_pos;

void main() {
    gl_Position = u_mvp * vec4(in_pos, 1.0);
    v_norm = normalize(in_norm);
    v_world_pos = (u_model * vec4(in_pos, 1.0)).xyz;
}
"""

FRAGMENT_SHADER = """
#version 330
in vec3 v_norm;
in vec3 v_world_pos;

// 灯光参数
uniform vec3 u_light_dir;
uniform vec3 u_fill_dir;

// 卡通风格参数
uniform vec3 u_shadow_color;
uniform vec3 u_base_color;
uniform float u_outline_width;
uniform vec3 u_outline_color;
uniform int u_shade_levels;

// 光照强度
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
    vec3 V = normalize(u_cam_pos - v_world_pos);
    float NdotV = max(dot(N, V), 0.0);

    // ========== 1. 边缘描边 ==========
    // 基于菲涅尔效应检测边缘
    float edge_factor = 1.0 - NdotV;
    float outline_threshold = 1.0 - clamp(u_outline_width * 0.4, 0.1, 0.8);

    if (edge_factor > outline_threshold) {
        float alpha = smoothstep(outline_threshold, outline_threshold + 0.08, edge_factor);
        frag_color = vec4(u_outline_color, alpha);
        return;
    }

    // ========== 2. 离散光照 ==========
    vec3 L1 = normalize(u_light_dir);
    vec3 L2 = normalize(u_fill_dir);

    float d1 = max(dot(N, L1), 0.0);
    float d2 = max(dot(N, L2), 0.0);
    float total_light = d1 * 0.7 + d2 * 0.3;

    // 色阶化
    float shade_level;
    if (u_shade_levels == 2) {
        shade_level = step(0.5, total_light);
    } else if (u_shade_levels == 3) {
        shade_level = total_light > 0.66 ? 1.0 : (total_light > 0.33 ? 0.5 : 0.0);
    } else {
        shade_level = total_light > 0.75 ? 1.0 : (total_light > 0.5 ? 0.66 : (total_light > 0.25 ? 0.33 : 0.0));
    }

    // 阴影色/基础色混合
    vec3 diffuse_color = mix(u_shadow_color, u_base_color, shade_level * u_diffuse + u_ambient);

    // ========== 3. 高光 ==========
    vec3 H = normalize(L1 + V);
    float spec_raw = pow(max(dot(N, H), 0.0), u_spec_pow);
    float spec_threshold = 0.5 - u_spec_int * 0.3;
    float spec = step(spec_threshold, spec_raw) * u_spec_int * 0.8;

    // ========== 4. 边缘光 ==========
    float rim = pow(1.0 - NdotV, u_rim_pow) * u_rim_int;

    // ========== 5. 合成 ==========
    vec3 final_color = diffuse_color + spec + rim * vec3(0.9, 0.95, 1.0);

    // 简单环境光遮蔽
    float ao = 0.85 + 0.15 * max(dot(N, vec3(0.0, 1.0, 0.0)), 0.0);
    final_color *= ao;

    frag_color = vec4(clamp(final_color, 0.0, 1.0), 1.0);
}
"""


# =============================================================================
# 网格生成函数
# =============================================================================

def _generate_sphere(subdivisions: int = 8) -> Tuple[np.ndarray, np.ndarray]:
    """
    生成 UV 球体网格

    Args:
        subdivisions: 细分级别

    Returns:
        (vertices, indices) 顶点数组 (N, 6) 和索引数组
    """
    stacks = max(2, subdivisions * 4)
    sectors = max(4, subdivisions * 8)
    radius = 0.85

    vertices = []
    indices = []

    for i in range(stacks + 1):
        theta = np.pi * i / stacks
        sin_theta, cos_theta = np.sin(theta), np.cos(theta)

        for j in range(sectors + 1):
            phi = 2 * np.pi * j / sectors
            sin_phi, cos_phi = np.sin(phi), np.cos(phi)

            # 位置和法线
            x = sin_theta * cos_phi
            y = cos_theta
            z = sin_theta * sin_phi

            vertices.extend([x * radius, y * radius, z * radius, x, y, z])

    # 生成索引
    for i in range(stacks):
        for j in range(sectors):
            a = i * (sectors + 1) + j
            b = a + 1
            c = (i + 1) * (sectors + 1) + j
            d = c + 1
            indices.extend([a, c, b, b, c, d])

    return np.array(vertices, dtype='f4'), np.array(indices, dtype='i4')


def _generate_cube() -> Tuple[np.ndarray, np.ndarray]:
    """
    生成立方体网格（24 顶点，每面独立法线）

    Returns:
        (vertices, indices)
    """
    hs = 0.80  # half size
    faces = [
        ([-1, 0, 0], [[-hs, -hs, hs], [-hs, -hs, -hs], [-hs, hs, -hs], [-hs, hs, hs]]),
        ([ 1, 0, 0], [[ hs, -hs, -hs], [ hs, -hs, hs], [ hs, hs, hs], [ hs, hs, -hs]]),
        ([ 0,-1, 0], [[-hs, -hs, -hs], [ hs, -hs, -hs], [ hs, -hs, hs], [-hs, -hs, hs]]),
        ([ 0, 1, 0], [[-hs, hs, hs], [ hs, hs, hs], [ hs, hs, -hs], [-hs, hs, -hs]]),
        ([ 0, 0,-1], [[-hs, -hs, -hs], [-hs, hs, -hs], [ hs, hs, -hs], [ hs, -hs, -hs]]),
        ([ 0, 0, 1], [[ hs, -hs, hs], [ hs, hs, hs], [-hs, hs, hs], [-hs, -hs, hs]]),
    ]

    vertices = []
    indices = []

    for i, (normal, corners) in enumerate(faces):
        for corner in corners:
            vertices.extend(corner + normal)
        indices.extend([i*4, i*4+1, i*4+2, i*4, i*4+2, i*4+3])

    return np.array(vertices, dtype='f4'), np.array(indices, dtype='i4')


def _generate_cylinder(segments: int = 48) -> Tuple[np.ndarray, np.ndarray]:
    """
    生成圆柱体网格

    Args:
        segments: 圆周分段数

    Returns:
        (vertices, indices)
    """
    radius = 0.55
    half_height = 0.85

    vertices = []
    indices = []

    # 侧面
    for i in range(segments + 1):
        angle = 2 * np.pi * i / segments
        cos_a, sin_a = np.cos(angle), np.sin(angle)

        nx, nz = cos_a, sin_a
        x, z = cos_a * radius, sin_a * radius

        # 底部顶点
        vertices.extend([x, -half_height, z, nx, 0, nz])
        # 顶部顶点
        vertices.extend([x, half_height, z, nx, 0, nz])

    # 侧面索引
    for i in range(segments):
        b = i * 2
        indices.extend([b, b+2, b+1, b+1, b+2, b+3])

    base_idx = (segments + 1) * 2

    # 顶盖
    vertices.extend([0, half_height, 0, 0, 1, 0])
    for i in range(segments + 1):
        angle = 2 * np.pi * i / segments
        vertices.extend([np.cos(angle) * radius, half_height, np.sin(angle) * radius, 0, 1, 0])
    for i in range(segments):
        indices.extend([base_idx, base_idx + 1 + i, base_idx + 2 + i])

    base_idx += segments + 2

    # 底盖
    vertices.extend([0, -half_height, 0, 0, -1, 0])
    for i in range(segments + 1):
        angle = 2 * np.pi * i / segments
        vertices.extend([np.cos(angle) * radius, -half_height, np.sin(angle) * radius, 0, -1, 0])
    for i in range(segments):
        indices.extend([base_idx, base_idx + 2 + i, base_idx + 1 + i])

    return np.array(vertices, dtype='f4'), np.array(indices, dtype='i4')


def _generate_torus(major_segments: int = 64, minor_segments: int = 32) -> Tuple[np.ndarray, np.ndarray]:
    """
    生成圆环体网格

    Args:
        major_segments: 主圆周分段
        minor_segments: 管道圆周分段

    Returns:
        (vertices, indices)
    """
    major_radius = 0.60
    minor_radius = 0.30

    vertices = []
    indices = []

    for i in range(major_segments + 1):
        theta = 2 * np.pi * i / major_segments
        cos_t, sin_t = np.cos(theta), np.sin(theta)

        for j in range(minor_segments + 1):
            phi = 2 * np.pi * j / minor_segments
            cos_p, sin_p = np.cos(phi), np.sin(phi)

            # 位置
            px = (major_radius + minor_radius * cos_p) * cos_t
            py = minor_radius * sin_p
            pz = (major_radius + minor_radius * cos_p) * sin_t

            # 法线
            nx = cos_p * cos_t
            ny = sin_p
            nz = cos_p * sin_t

            vertices.extend([px, py, pz, nx, ny, nz])

    # 索引
    for i in range(major_segments):
        for j in range(minor_segments):
            a = i * (minor_segments + 1) + j
            b = a + 1
            c = (i + 1) * (minor_segments + 1) + j
            d = c + 1
            indices.extend([a, c, b, b, c, d])

    return np.array(vertices, dtype='f4'), np.array(indices, dtype='i4')


# =============================================================================
# 数据类
# =============================================================================

@dataclass
class LightParams:
    """灯光参数配置"""
    ambient: float = 0.25
    diffuse: float = 0.80
    specular_power: float = 40.0
    specular_intensity: float = 0.35
    rim_intensity: float = 0.15
    rim_power: float = 3.0
    light_dir: Tuple[float, float, float] = (0.4, -0.5, 0.7)
    fill_dir: Tuple[float, float, float] = (-0.3, 0.2, 0.5)
    ground_shadow: float = 0.25

    def validate(self) -> None:
        """验证参数范围"""
        self.ambient = max(0.0, min(1.0, self.ambient))
        self.diffuse = max(0.0, min(1.0, self.diffuse))
        self.specular_power = max(1.0, min(128.0, self.specular_power))
        self.specular_intensity = max(0.0, min(1.0, self.specular_intensity))
        self.rim_intensity = max(0.0, min(1.0, self.rim_intensity))
        self.rim_power = max(1.0, min(8.0, self.rim_power))


@dataclass
class RenderParams:
    """渲染参数配置"""
    shadow_color: Tuple[float, float, float] = (0.35, 0.35, 0.35)
    base_color: Tuple[float, float, float] = (0.85, 0.85, 0.85)
    outline_width: float = 1.0
    outline_color: Tuple[float, float, float] = (0.08, 0.08, 0.12)
    spec_boost: float = 0.0
    rim_boost: float = 0.0
    shade_levels: int = 3

    def validate(self) -> None:
        """验证参数范围"""
        self.outline_width = max(0.5, min(3.0, self.outline_width))
        self.spec_boost = max(0.0, min(1.0, self.spec_boost))
        self.rim_boost = max(0.0, min(1.0, self.rim_boost))
        self.shade_levels = max(2, min(4, self.shade_levels))
        # 颜色 clamp 到 [0, 1]
        self.shadow_color = tuple(max(0.0, min(1.0, c)) for c in self.shadow_color)
        self.base_color = tuple(max(0.0, min(1.0, c)) for c in self.base_color)
        self.outline_color = tuple(max(0.0, min(1.0, c)) for c in self.outline_color)


# =============================================================================
# 相机类
# =============================================================================

class Camera:
    """
    轨道相机控制器

    支持：
      - Yaw/Pitch 旋转
      - Zoom 缩放
      - Pan 平移
      - 形状预设视角
    """

    def __init__(self, shape: str = "sphere"):
        """
        初始化相机

        Args:
            shape: 初始形状名称，用于加载预设视角
        """
        self._yaw = 25.0
        self._pitch = -15.0
        self._zoom = 1.2
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._shape = shape

        self._apply_preset(shape)

    @property
    def yaw(self) -> float:
        return self._yaw

    @yaw.setter
    def yaw(self, value: float) -> None:
        self._yaw = value

    @property
    def pitch(self) -> float:
        return self._pitch

    @pitch.setter
    def pitch(self, value: float) -> None:
        self._pitch = max(CAMERA_PITCH_MIN, min(CAMERA_PITCH_MAX, value))

    @property
    def zoom(self) -> float:
        return self._zoom

    @zoom.setter
    def zoom(self, value: float) -> None:
        self._zoom = max(CAMERA_ZOOM_MIN, min(CAMERA_ZOOM_MAX, value))

    @property
    def pan_x(self) -> float:
        return self._pan_x

    @pan_x.setter
    def pan_x(self, value: float) -> None:
        self._pan_x = value

    @property
    def pan_y(self) -> float:
        return self._pan_y

    @pan_y.setter
    def pan_y(self, value: float) -> None:
        self._pan_y = value

    def _apply_preset(self, shape: str) -> None:
        """应用形状预设视角"""
        if shape in SHAPE_PRESETS:
            self._yaw, self._pitch, self._zoom = SHAPE_PRESETS[shape]
            self._shape = shape
            logger.debug(f"Applied camera preset for '{shape}': yaw={self._yaw}, pitch={self._pitch}, zoom={self._zoom}")

    def set_shape(self, shape: str) -> None:
        """切换形状并更新预设视角"""
        self._apply_preset(shape)

    def reset(self, shape: Optional[str] = None) -> None:
        """重置到预设视角"""
        target = shape or self._shape
        self._apply_preset(target)
        self._pan_x = 0.0
        self._pan_y = 0.0

    def view_matrix(self) -> np.ndarray:
        """
        计算视图矩阵

        Returns:
            4x4 视图矩阵
        """
        distance = 3.0 / self._zoom

        # 计算相机位置
        cy, sy = np.cos(np.radians(self._yaw)), np.sin(np.radians(self._yaw))
        cp, sp = np.cos(np.radians(self._pitch)), np.sin(np.radians(self._pitch))

        eye = np.array([
            distance * cy * cp,
            distance * sp,
            distance * sy * cp
        ], dtype='f4')

        # 构建视图矩阵
        up = np.array([0, 1, 0], dtype='f4')
        forward = -eye / (np.linalg.norm(eye) + 1e-10)
        right = np.cross(forward, up)
        right = right / (np.linalg.norm(right) + 1e-10)
        up = np.cross(right, forward)

        matrix = np.eye(4, dtype='f4')
        matrix[0, :3] = right
        matrix[1, :3] = up
        matrix[2, :3] = -forward
        matrix[:3, 3] = -matrix[:3, :3] @ eye

        return matrix

    def projection_matrix(self, aspect: float = 1.0) -> np.ndarray:
        """
        计算投影矩阵

        Args:
            aspect: 宽高比

        Returns:
            4x4 投影矩阵
        """
        fov = 45.0
        near = 0.1
        far = 50.0

        tan_half_fov = np.tan(np.radians(fov) / 2)

        matrix = np.zeros((4, 4), dtype='f4')
        matrix[0, 0] = 1 / (aspect * tan_half_fov)
        matrix[1, 1] = 1 / tan_half_fov
        matrix[2, 2] = -(far + near) / (far - near)
        matrix[2, 3] = -2 * far * near / (far - near)
        matrix[3, 2] = -1

        return matrix


# =============================================================================
# 渲染器类
# =============================================================================

class GLRenderer:
    """
    ModernGL 离屏渲染器

    工业级卡通风格渲染器，支持：
      - MSAA 抗锯齿
      - 离散色阶光照
      - 边缘描边
      - 高光和边缘光

    Example:
        >>> renderer = GLRenderer(380, 380)
        >>> camera = Camera("sphere")
        >>> light = LightParams()
        >>> params = RenderParams()
        >>> image = renderer.render("sphere", camera, light, params)
        >>> renderer.cleanup()
    """

    # 支持的形状类型
    SHAPES = ("sphere", "cube", "cylinder", "torus")

    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        samples: int = DEFAULT_MSAA_SAMPLES
    ):
        """
        初始化渲染器

        Args:
            width: 渲染宽度
            height: 渲染高度
            samples: MSAA 采样数 (1, 2, 4)
        """
        self._width = max(64, min(MAX_TEXTURE_SIZE, width))
        self._height = max(64, min(MAX_TEXTURE_SIZE, height))
        self._samples = max(1, min(4, samples))

        self._ctx: Optional[moderngl.Context] = None
        self._program: Optional[moderngl.Program] = None
        self._meshes: Dict[str, Tuple[moderngl.Buffer, moderngl.Buffer, int]] = {}
        self._fbo: Optional[moderngl.Framebuffer] = None
        self._color_tex: Optional[moderngl.Texture] = None
        self._depth_rb: Optional[moderngl.Renderbuffer] = None
        self._resolve_fbo: Optional[moderngl.Framebuffer] = None
        self._resolve_tex: Optional[moderngl.Texture] = None

        self._initialize()

    def _initialize(self) -> None:
        """初始化 OpenGL 资源"""
        # 创建上下文
        self._ctx = self._create_context()

        # 启用深度测试
        self._ctx.enable(moderngl.DEPTH_TEST)

        # 编译着色器
        self._program = self._ctx.program(
            vertex_shader=VERTEX_SHADER,
            fragment_shader=FRAGMENT_SHADER
        )

        # 创建网格
        self._create_meshes()

        # 创建帧缓冲
        self._create_framebuffer(self._width, self._height)

        logger.info(f"GLRenderer initialized: {self._width}x{self._height}, MSAA={self._samples}x")

    def _create_context(self) -> moderngl.Context:
        """创建 OpenGL 上下文"""
        try:
            ctx = moderngl.create_standalone_context()
            logger.info("Created standalone GL context")
            return ctx
        except Exception as e:
            logger.warning(f"Standalone context failed: {e}")
            # 回退到 GLFW 创建隐藏窗口
            try:
                import glfw
                glfw.init()
                glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
                glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
                glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
                glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
                window = glfw.create_window(1, 1, "hidden", None, None)
                glfw.make_context_current(window)
                ctx = moderngl.create_context()
                logger.info("Created GL context via GLFW")
                # 不销毁 window，保持上下文活跃
                self._glfw_window = window
                return ctx
            except ImportError:
                logger.error("GLFW not available")
                raise RuntimeError(
                    "Failed to create OpenGL context. "
                    "Please install glfw: pip install glfw"
                )
            except Exception as e2:
                logger.error(f"GLFW context also failed: {e2}")
                raise RuntimeError(
                    f"Failed to create OpenGL context: {e2}"
                )

    def _create_meshes(self) -> None:
        """创建网格数据"""
        generators = {
            "sphere": lambda: _generate_sphere(MESH_SUBDIVISIONS["sphere"]),
            "cube": _generate_cube,
            "cylinder": lambda: _generate_cylinder(MESH_SUBDIVISIONS["cylinder"]),
            "torus": lambda: _generate_torus(
                MESH_SUBDIVISIONS["torus_major"],
                MESH_SUBDIVISIONS["torus_minor"]
            ),
        }

        for name, gen_func in generators.items():
            vertices, indices = gen_func()
            self._meshes[name] = (
                self._ctx.buffer(vertices.tobytes()),
                self._ctx.buffer(indices.tobytes()),
                len(indices)
            )

    def _create_framebuffer(self, width: int, height: int) -> None:
        """创建帧缓冲对象"""
        # 释放旧资源
        self._release_framebuffer()

        self._width = width
        self._height = height

        if self._samples > 1:
            # MSAA 帧缓冲
            self._color_tex = self._ctx.texture((width, height), 4, samples=self._samples)
            self._depth_rb = self._ctx.depth_renderbuffer((width, height), samples=self._samples)
            self._fbo = self._ctx.framebuffer(
                color_attachments=[self._color_tex],
                depth_attachment=self._depth_rb
            )

            # Resolve 帧缓冲
            self._resolve_tex = self._ctx.texture((width, height), 4)
            self._resolve_fbo = self._ctx.framebuffer(color_attachments=[self._resolve_tex])
        else:
            # 普通帧缓冲
            self._color_tex = self._ctx.texture((width, height), 4)
            self._depth_rb = self._ctx.depth_renderbuffer((width, height))
            self._fbo = self._ctx.framebuffer(
                color_attachments=[self._color_tex],
                depth_attachment=self._depth_rb
            )

    def _release_framebuffer(self) -> None:
        """释放帧缓冲资源"""
        for obj in [self._fbo, self._color_tex, self._depth_rb, self._resolve_fbo, self._resolve_tex]:
            if obj is not None:
                obj.release()
        self._fbo = None
        self._color_tex = None
        self._depth_rb = None
        self._resolve_fbo = None
        self._resolve_tex = None

    def render(
        self,
        shape: str,
        camera: Camera,
        light: LightParams,
        params: Optional[RenderParams] = None,
        width: int = 0,
        height: int = 0
    ) -> np.ndarray:
        """
        渲染一帧

        Args:
            shape: 形状名称 (sphere, cube, cylinder, torus)
            camera: 相机对象
            light: 灯光参数
            params: 渲染参数，可选
            width: 渲染宽度，0 表示使用默认值
            height: 渲染高度，0 表示使用默认值

        Returns:
            BGR numpy 数组，形状为 (H, W, 3)
        """
        if params is None:
            params = RenderParams()

        # 参数验证
        params.validate()
        light.validate()

        # 确定渲染尺寸
        rw = width if width > 0 else self._width
        rh = height if height > 0 else self._height

        # 按需重建帧缓冲
        if rw != self._width or rh != self._height:
            self._create_framebuffer(rw, rh)

        # 获取网格
        if shape not in self._meshes:
            logger.warning(f"Unknown shape '{shape}', falling back to 'sphere'")
            shape = "sphere"

        vbuf, ibuf, index_count = self._meshes[shape]

        # 创建 VAO
        vao = self._ctx.vertex_array(
            self._program,
            [(vbuf, '3f 3f', 'in_pos', 'in_norm')],
            ibuf
        )

        # 设置 uniform
        self._set_uniforms(camera, light, params)

        # 渲染
        self._fbo.use()
        self._fbo.clear(28/255, 28/255, 30/255, 1.0)
        vao.render(moderngl.TRIANGLES)
        vao.release()

        # 读取像素
        return self._read_pixels(rw, rh)

    def _set_uniforms(
        self,
        camera: Camera,
        light: LightParams,
        params: RenderParams
    ) -> None:
        """设置着色器 uniform"""
        # MVP 矩阵
        mvp = camera.projection_matrix() @ camera.view_matrix()
        self._program['u_mvp'].write(mvp.tobytes())

        # Model 矩阵（单位矩阵）
        model = np.eye(4, dtype='f4')
        self._program['u_model'].write(model.tobytes())

        # 相机位置
        dist = 3.0 / camera.zoom
        cy, sy = np.cos(np.radians(camera.yaw)), np.sin(np.radians(camera.yaw))
        cp, sp = np.cos(np.radians(camera.pitch)), np.sin(np.radians(camera.pitch))
        self._program['u_cam_pos'].value = (dist * cy * cp, dist * sp, dist * sy * cp)

        # 灯光
        self._program['u_light_dir'].value = light.light_dir
        self._program['u_fill_dir'].value = light.fill_dir

        # 卡通参数
        self._program['u_shadow_color'].value = params.shadow_color
        self._program['u_base_color'].value = params.base_color
        self._program['u_outline_width'].value = params.outline_width
        self._program['u_outline_color'].value = params.outline_color
        self._program['u_shade_levels'].value = params.shade_levels

        # 光照强度
        self._program['u_ambient'].value = light.ambient
        self._program['u_diffuse'].value = light.diffuse
        self._program['u_spec_pow'].value = light.specular_power + params.spec_boost * 20
        self._program['u_spec_int'].value = min(1.0, light.specular_intensity + params.spec_boost * 0.3)
        self._program['u_rim_int'].value = min(1.0, light.rim_intensity + params.rim_boost * 0.25)
        self._program['u_rim_pow'].value = max(1.0, light.rim_power - params.rim_boost * 0.5)

    def _read_pixels(self, width: int, height: int) -> np.ndarray:
        """读取像素数据"""
        if self._samples > 1 and self._resolve_fbo:
            self._ctx.copy_framebuffer(self._resolve_fbo, self._fbo)
            data = self._resolve_fbo.read(components=4)
        else:
            data = self._fbo.read(components=4)

        # 转换为 numpy 数组
        img = np.frombuffer(data, dtype='u1').reshape(height, width, 4)
        img = np.flipud(img)  # OpenGL Y 轴翻转

        # RGBA -> BGR
        return img[:, :, [2, 1, 0]].copy()

    def cleanup(self) -> None:
        """释放所有资源"""
        # 释放网格
        for vbuf, ibuf, _ in self._meshes.values():
            vbuf.release()
            ibuf.release()
        self._meshes.clear()

        # 释放帧缓冲
        self._release_framebuffer()

        # 释放着色器
        if self._program is not None:
            self._program.release()
            self._program = None

        # 释放 GLFW 资源
        if hasattr(self, '_glfw_window') and self._glfw_window is not None:
            try:
                import glfw
                glfw.destroy_window(self._glfw_window)
                glfw.terminate()
            except Exception:
                pass
            self._glfw_window = None

        # 释放上下文
        if self._ctx is not None:
            self._ctx.release()
            self._ctx = None

        logger.info("GLRenderer cleanup complete")

    def __enter__(self) -> 'GLRenderer':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()
