
"""
HybriToon - MooaToon 材质参数定义
Day1: 研究MooaToon材质参数列表 & 设计参数向量结构

基于官方文档和MToon参考实现设计的完整参数体系
"""

from dataclasses import dataclass, field
from typing import List, Tuple
import numpy as np


@dataclass
class ColorParams:
    """颜色相关参数"""
    base_color_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    shadow_color: Tuple[float, float, float] = (0.5, 0.5, 0.5)
    shadow_color_map_intensity: float = 1.0
    specular_color: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    outline_color: Tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class ShadingParams:
    """光影相关参数"""
    shadow_threshold: float = 0.5
    shadow_softness: float = 0.1
    shadow_shift: float = 0.0
    shadow_threshold_2: float = 0.2
    shadow_softness_2: float = 0.1


@dataclass
class SpecularParams:
    """高光相关参数"""
    specular_intensity: float = 0.5
    specular_range: float = 0.3
    specular_softness: float = 0.2
    specular_anisotropy: float = 0.0
    specular_anisotropy_direction: float = 0.0


@dataclass
class HairParams:
    """头发相关参数 (基于Kajiya-Kay模型)"""
    hair_specular_intensity: float = 1.0
    hair_specular_shift_1: float = 0.0
    hair_specular_range_1: float = 0.3
    hair_specular_shift_2: float = -0.3
    hair_specular_range_2: float = 0.2
    hair_specular_color_1: Tuple[float, float, float] = (1.0, 0.9, 0.7)
    hair_specular_color_2: Tuple[float, float, float] = (0.8, 0.6, 0.4)


@dataclass
class OutlineParams:
    """描边相关参数"""
    outline_width: float = 0.05
    outline_width_map_intensity: float = 1.0
    outline_z_bias: float = 0.01
    outline_screen_space_intensity: float = 0.0
    outline_depth_threshold: float = 0.1
    outline_normal_threshold: float = 0.5


@dataclass
class RimLightParams:
    """边缘光相关参数"""
    rimlight_intensity: float = 0.0
    rimlight_range: float = 0.5
    rimlight_color: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    rimlight_threshold: float = 0.0


@dataclass
class GIParams:
    """全局光照相关参数"""
    gi_intensity: float = 1.0
    gi_directionality: float = 1.0
    reflection_intensity: float = 1.0


@dataclass
class PostProcessParams:
    """后期处理参数"""
    exposure_compensation: float = 0.0
    saturation: float = 1.0
    contrast: float = 1.0
    gamma: float = 1.0


@dataclass
class MooaToonMaterialParams:
    """
    MooaToon 完整材质参数集合
    
    这是HybriToon风格编码器的输出目标，
    包含从参考图中可学习的所有可控参数。
    """
    color: ColorParams = field(default_factory=ColorParams)
    shading: ShadingParams = field(default_factory=ShadingParams)
    specular: SpecularParams = field(default_factory=SpecularParams)
    hair: HairParams = field(default_factory=HairParams)
    outline: OutlineParams = field(default_factory=OutlineParams)
    rimlight: RimLightParams = field(default_factory=RimLightParams)
    gi: GIParams = field(default_factory=GIParams)
    post_process: PostProcessParams = field(default_factory=PostProcessParams)
    style_preset: str = "default"
    
    def to_vector(self, normalize: bool = True):
        params = []
        
        params.extend(self.color.base_color_offset)
        params.extend(self.color.shadow_color)
        params.append(self.color.shadow_color_map_intensity)
        params.extend(self.color.specular_color)
        params.extend(self.color.outline_color)
        
        params.append(self.shading.shadow_threshold)
        params.append(self.shading.shadow_softness)
        params.append(self.shading.shadow_shift)
        params.append(self.shading.shadow_threshold_2)
        params.append(self.shading.shadow_softness_2)
        
        params.append(self.specular.specular_intensity)
        params.append(self.specular.specular_range)
        params.append(self.specular.specular_softness)
        params.append(self.specular.specular_anisotropy)
        params.append(self.specular.specular_anisotropy_direction)
        
        params.append(self.hair.hair_specular_intensity)
        params.append(self.hair.hair_specular_shift_1)
        params.append(self.hair.hair_specular_range_1)
        params.append(self.hair.hair_specular_shift_2)
        params.append(self.hair.hair_specular_range_2)
        params.extend(self.hair.hair_specular_color_1)
        params.extend(self.hair.hair_specular_color_2)
        
        params.append(self.outline.outline_width)
        params.append(self.outline.outline_width_map_intensity)
        params.append(self.outline.outline_z_bias)
        params.append(self.outline.outline_screen_space_intensity)
        params.append(self.outline.outline_depth_threshold)
        params.append(self.outline.outline_normal_threshold)
        
        params.append(self.rimlight.rimlight_intensity)
        params.append(self.rimlight.rimlight_range)
        params.extend(self.rimlight.rimlight_color)
        params.append(self.rimlight.rimlight_threshold)
        
        params.append(self.gi.gi_intensity)
        params.append(self.gi.gi_directionality)
        params.append(self.gi.reflection_intensity)
        
        params.append(self.post_process.exposure_compensation)
        params.append(self.post_process.saturation)
        params.append(self.post_process.contrast)
        params.append(self.post_process.gamma)
        
        vec = np.array(params, dtype=np.float32)
        
        if normalize:
            vec = self._normalize_vector(vec)
        
        return vec
    
    @classmethod
    def from_vector(cls, vec, denormalize: bool = True):
        if denormalize:
            vec = cls._denormalize_vector(vec)
        
        idx = 0
        params = cls()
        
        params.color.base_color_offset = tuple(vec[idx:idx+3])
        idx += 3
        params.color.shadow_color = tuple(vec[idx:idx+3])
        idx += 3
        params.color.shadow_color_map_intensity = vec[idx]
        idx += 1
        params.color.specular_color = tuple(vec[idx:idx+3])
        idx += 3
        params.color.outline_color = tuple(vec[idx:idx+3])
        idx += 3
        
        params.shading.shadow_threshold = vec[idx]
        idx += 1
        params.shading.shadow_softness = vec[idx]
        idx += 1
        params.shading.shadow_shift = vec[idx]
        idx += 1
        params.shading.shadow_threshold_2 = vec[idx]
        idx += 1
        params.shading.shadow_softness_2 = vec[idx]
        idx += 1
        
        params.specular.specular_intensity = vec[idx]
        idx += 1
        params.specular.specular_range = vec[idx]
        idx += 1
        params.specular.specular_softness = vec[idx]
        idx += 1
        params.specular.specular_anisotropy = vec[idx]
        idx += 1
        params.specular.specular_anisotropy_direction = vec[idx]
        idx += 1
        
        params.hair.hair_specular_intensity = vec[idx]
        idx += 1
        params.hair.hair_specular_shift_1 = vec[idx]
        idx += 1
        params.hair.hair_specular_range_1 = vec[idx]
        idx += 1
        params.hair.hair_specular_shift_2 = vec[idx]
        idx += 1
        params.hair.hair_specular_range_2 = vec[idx]
        idx += 1
        params.hair.hair_specular_color_1 = tuple(vec[idx:idx+3])
        idx += 3
        params.hair.hair_specular_color_2 = tuple(vec[idx:idx+3])
        idx += 3
        
        params.outline.outline_width = vec[idx]
        idx += 1
        params.outline.outline_width_map_intensity = vec[idx]
        idx += 1
        params.outline.outline_z_bias = vec[idx]
        idx += 1
        params.outline.outline_screen_space_intensity = vec[idx]
        idx += 1
        params.outline.outline_depth_threshold = vec[idx]
        idx += 1
        params.outline.outline_normal_threshold = vec[idx]
        idx += 1
        
        params.rimlight.rimlight_intensity = vec[idx]
        idx += 1
        params.rimlight.rimlight_range = vec[idx]
        idx += 1
        params.rimlight.rimlight_color = tuple(vec[idx:idx+3])
        idx += 3
        params.rimlight.rimlight_threshold = vec[idx]
        idx += 1
        
        params.gi.gi_intensity = vec[idx]
        idx += 1
        params.gi.gi_directionality = vec[idx]
        idx += 1
        params.gi.reflection_intensity = vec[idx]
        idx += 1
        
        params.post_process.exposure_compensation = vec[idx]
        idx += 1
        params.post_process.saturation = vec[idx]
        idx += 1
        params.post_process.contrast = vec[idx]
        idx += 1
        params.post_process.gamma = vec[idx]
        idx += 1
        
        return params
    
    @staticmethod
    def _normalize_vector(vec):
        normalized = vec.copy()
        normalized[0:3] = (vec[0:3] + 1.0) / 2.0
        normalized[15] = (vec[15] + 1.0) / 2.0
        normalized[24] = (vec[24] + 1.0) / 2.0
        normalized[26] = (vec[26] + 1.0) / 2.0
        normalized[34] = np.clip(vec[34] / 0.2, 0.0, 1.0)
        normalized[36] = np.clip(vec[36] / 0.1, 0.0, 1.0)
        normalized[49] = (vec[49] + 2.0) / 4.0
        normalized[50] = np.clip(vec[50] / 2.0, 0.0, 1.0)
        normalized[51] = np.clip(vec[51] / 2.0, 0.0, 1.0)
        normalized[52] = (vec[52] - 0.5) / 2.0
        return np.clip(normalized, 0.0, 1.0)
    
    @staticmethod
    def _denormalize_vector(normalized):
        vec = normalized.copy()
        vec[0:3] = vec[0:3] * 2.0 - 1.0
        vec[15] = vec[15] * 2.0 - 1.0
        vec[24] = vec[24] * 2.0 - 1.0
        vec[26] = vec[26] * 2.0 - 1.0
        vec[34] = vec[34] * 0.2
        vec[36] = vec[36] * 0.1
        vec[49] = vec[49] * 4.0 - 2.0
        vec[50] = vec[50] * 2.0
        vec[51] = vec[51] * 2.0
        vec[52] = vec[52] * 2.0 + 0.5
        return vec
    
    @staticmethod
    def get_param_dim():
        return 53


def get_anime_style_preset():
    params = MooaToonMaterialParams()
    params.style_preset = "anime"
    params.shading.shadow_threshold = 0.6
    params.shading.shadow_softness = 0.05
    params.shading.shadow_shift = 0.1
    params.outline.outline_width = 0.04
    params.outline.outline_color = (0.0, 0.0, 0.0)
    params.gi.gi_intensity = 0.3
    params.gi.gi_directionality = 0.5
    return params


def get_cartoon_style_preset():
    params = MooaToonMaterialParams()
    params.style_preset = "cartoon"
    params.shading.shadow_threshold = 0.5
    params.shading.shadow_softness = 0.3
    params.shading.shadow_shift = 0.0
    params.outline.outline_width = 0.06
    params.gi.gi_intensity = 0.8
    params.gi.gi_directionality = 1.0
    return params


def get_watercolor_style_preset():
    params = MooaToonMaterialParams()
    params.style_preset = "watercolor"
    params.shading.shadow_threshold = 0.4
    params.shading.shadow_softness = 0.6
    params.outline.outline_width = 0.02
    params.outline.outline_color = (0.2, 0.2, 0.2)
    params.post_process.saturation = 1.2
    params.post_process.contrast = 0.8
    return params


def get_all_style_presets():
    return {
        "default": MooaToonMaterialParams(),
        "anime": get_anime_style_preset(),
        "cartoon": get_cartoon_style_preset(),
        "watercolor": get_watercolor_style_preset(),
    }


if __name__ == "__main__":
    print("=" * 60)
    print("HybriToon - MooaToon 材质参数定义")
    print("=" * 60)
    
    default_params = MooaToonMaterialParams()
    print(f"\n默认参数向量维度: {default_params.to_vector().shape}")
    
    presets = get_all_style_presets()
    print(f"\n可用风格预设: {list(presets.keys())}")
    
    vec = default_params.to_vector()
    reconstructed = MooaToonMaterialParams.from_vector(vec)
    print(f"\n参数序列化测试: {'通过' if np.allclose(vec, reconstructed.to_vector()) else '失败'}")
    
    print("\n" + "=" * 60)
    print("Day1 任务完成!")
    print("- [x] 研究MooaToon材质参数列表")
    print("- [x] 设计参数向量结构 (53维)")
    print("=" * 60)

