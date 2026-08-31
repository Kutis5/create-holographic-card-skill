# Card Presentation IR v2 / GPU Optical Recipe Registry v2

公开 MCP v5 参数和 `schemaVersion: 5` 保持不变。调用方只选择材质族、兼容微纹理、目标、调色板和公开强度；不得传入 Shader uniform、CSS、遮罩、混合模式或内部运动系数。

## 公开契约

- `FRAME`: `none | hairline | narrow | double`，宽度 `0–0.9%`；`colorMode` 为 `fixed | image`，缺省 `fixed`。
- `RADIUS`: 外圆角 `2–8%`；内圆角由服务根据边框宽度规范化。
- `SURFACE.material`: `clear-coat | pearl | brushed-metal | spectral-lines | etched-holo | cosmic-flake | star-holo`。
- `FOIL`: 目标 `background | surface | frame`，1–6 个颜色，强度 `0–1`。
- `TEXTURE`、`SPARKLE`、`GLARE`: 强度均为 `0–1`。
- `DEPTH`: 视差轴 `0–2.5%`、抬升 `0–28px`、阴影不透明度 `0–0.3`、模糊 `0–28px`、轮廓光 `0–0.25`。
- `MOTION`: maxX/maxY `0–14`、scale `1–1.05`、smoothing `0.08–0.4`。
- `CONSTRAINTS`: `keepInsideFrame: true`。

先按画面选择光学模式，而不是把旗舰彩虹作为所有卡片的默认。浅色、低饱和、柔和粉彩或产品摄影使用淡银模式：foil `0.28`、texture `0.32`、glare `0.36`。主体或背景为鲜艳高饱和、明确虹彩主题，或用户要求彩虹时，使用旗舰模式：foil `0.78`、texture `0.48`、glare `0.62`。两种模式都保留 `14° × 14°` 倾斜与 `1.024` 悬浮缩放。旧卡的较小强度通过感知曲线映射；例如 foil `0.18` 仍需明显可见。`enabled: false` 必须严格关闭对应效果。

低饱和画面必须提供完整六色的淡银调色板，避免视觉意图被自动补全。参考淡银色：`["#b7bcc3", "#d6d8d8", "#aeb5bd", "#e5e1da", "#c2c8cd", "#929aa4"]`。仅有一到五色且所有输入颜色 HSL 饱和度不超过 20% 时，运行时补为同样低饱和的六段明度渐变；其他不足六色的旧调色板仍补为连续六段光谱；已提供六色时保持原值。淡银模式不得引入明显粉、绿或蓝色带，且静止态不得改变主体固有颜色、压过主体层级或令浅色区域大面积泛白。推荐的淡银示例：

```json
{
  "frame": {"style":"narrow","width":0.65,"color":"#b9b8b6","colorMode":"image"},
  "foil": {"enabled":true,"target":"background","colors":["#b7bcc3","#d6d8d8","#aeb5bd","#e5e1da","#c2c8cd","#929aa4"],"intensity":0.28},
  "texture": {"kind":"micro-grain","target":"background","intensity":0.32},
  "glare": {"enabled":true,"target":"surface","intensity":0.36},
  "motion": {"maxX":14,"maxY":14,"scale":1.024,"smoothing":0.18}
}
```

高饱和或明确虹彩主题的推荐示例：

```json
{
  "frame": {"style":"narrow","width":0.65,"color":"#75808f","colorMode":"image"},
  "foil": {"enabled":true,"target":"background","colors":["#ff5470","#ffcc66","#50e3c2","#5cb8ff","#8f7cff","#ef7dff"],"intensity":0.78},
  "texture": {"kind":"micro-grain","target":"background","intensity":0.48},
  "glare": {"enabled":true,"target":"surface","intensity":0.62},
  "motion": {"maxX":14,"maxY":14,"scale":1.024,"smoothing":0.18}
}
```

`frame.colorMode: "image"` 从每一面图片外围 20% 取色；正反面独立分析。`frame.color` 始终是确定性回退色。跨域 Canvas、像素读取或有效样本不足时静默回退，不阻断卡片。

## 固定旗舰光学栈

所有七种材质共享：原图、自动反光遮罩、WebGL 微结构、两组不同角度和速度的调色板驱动反射、局部亮暗塑形、指针径向 glare、卡边高光/外辉光/投影。淡银或彩虹由公开调色板和强度决定；静止态显现量为 70%，加载后自动扫光；交互时指针接管，离开后 1.2 秒弹性回归自动光路。reduced-motion 停止动画并保留一帧明显斜向反射。

自动遮罩依据亮度、饱和度、边缘梯度和图集密度生成：暗线稿与阴影保留，中高亮、浅色和金属区域反射更强。背景、WebGL、coat、无硬边的错速柔光场、闪点和 glare 全部位于透明主体下方；禁止额外叠加周期性斜向条纹。主体只保留原始像素、3D 视差和无彩黑色自然阴影，绝不接收彩虹、扫光、明暗塑形或轮廓光。`depth.rimIntensity` 为旧数据兼容字段，在主体隔离模式下不产生视觉效果。

七种材质只改变微纹理：

- `clear-coat`: 低粗糙度清漆与局部折射。
- `pearl`: 云母密度和珠光干涉。
- `brushed-metal`: 定向微沟槽和交叉高光。
- `spectral-lines`: 被密度通道打断的衍射线。
- `etched-holo`: 高度边缘和交错蚀刻片段。
- `cosmic-flake`: 三尺度非整数采样闪片。
- `star-holo`: 单尺度星形压纹；静止时轻微可辨，方向吻合时呈现白亮芯和彩虹边并逐颗闪现。

兼容矩阵：clear-coat 支持 `none | micro-grain | scanline | sparse-flake`；pearl 支持 `none | micro-grain | contour | sparse-flake`；brushed-metal 与 spectral-lines 支持 `none | micro-grain | scanline`；etched-holo 支持 `none | micro-grain | geometric | contour`；cosmic-flake 与 star-holo 支持 `none | micro-grain`。

Sparkle 只允许 clear-coat、pearl 或 cosmic-flake；cosmic-flake 不允许 sparse-flake，star-holo 禁止通用 sparkle。图案化 surface 请求规范化到 background 并返回警告；surface 只允许 glare 或无图案 clear-coat。

## 生命周期与失败策略

每个渲染器实例加载当前材质图集、blue noise 和 micro grain；DPR 上限为 2。页面隐藏时停止请求帧。WebGL2 缺失、Shader 编译、纹理加载/解码/上传或 context lost 均阻断卡片并显示错误，不启用平面降级。React、Browser 预览和安装后的 Skill 必须使用同一份引擎、交互模块、CSS 与纹理资产。
