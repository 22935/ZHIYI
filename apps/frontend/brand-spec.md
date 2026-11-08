# 知弈 AgentOS 前端品牌规范

## 视觉真源

- 品牌与产品外壳：`C4-mainline` 的 Milan 前端。
- Logo 真源：`apps/frontend/public/logo.svg`（矢量方章）；位图 `docs/assets/brand/logo.png` 仅作溯源，不得用文字色块或重绘图形替代。
- 数据与运行语义：current WKN AgentOS v2；视觉恢复不得引入 C4 RuntimeGraph 或旧 `/core` API。

## 定位

- 叙事角色：Chat 是主工作区，Console 是高密度审计台，ACG 页面突出拓扑、运行摘要和变化时间线。
- 使用距离：桌面与笔记本优先，平板和窄屏保持完整信息层级。
- 视觉温度：克制、专业、可信，呈现工程工具感而非营销页面感。
- 信息容量：摘要使用响应式 4/8 栅格；长审计信息进入可折叠时间线。

## 设计令牌

- 主色：`#A78BFA`；hover `#B8A2FC`；active `#8F73E6`。
- 背景：app `#1E1F2E`；sidebar `#292A3D`；card `#2D2E42`；panel `#343548`；input `#252638`。
- 文本：primary `#E8E7F0`；regular `#D2D1DE`；secondary `#AAA9BE`；muted `#85859B`。
- 语义色：success `#75C69A`；warning `#D9B66F`；danger `#E88787`；info `#8FB4E8`。
- 字体：正文使用现有中文无衬线栈，章节标题使用现有中文衬线栈，标识与引用使用现有等宽栈。
- 间距：4px 微间距，8px 基础节奏，12/16/24px 作为主要层级。
- 圆角：6px 控件、9px 卡片、12px 大容器、999px 状态标签。
- 阴影：仅使用 `global.css` 的既有阴影层级，不新增彩色光晕。
- 动效：160-220ms，沿用 `--ease-out`，并尊重 `prefers-reduced-motion`。

## WKN 视觉映射

- C4 “动态运行摘要”外壳改为 WKN “运行态摘要”，展示 Graph version、Step 状态、GraphPatch 引用、恢复与审计数量。
- C4 “运行时变化时间线”外壳改为 WKN “运行审计时间线”，只消费 Trace、Recovery、Checkpoint、Review 与 GraphPatch reference。
- 不展示无法从真实 v2 API 得出的推测统计；缺失数据使用空态，不伪造数字。

## 禁止项

- `runtimeGraph`、`dynamicPatch`、`bindingSwitchCount`、planning fake projection。
- 第二套 Runtime、旧 Executor、旧 `/core` API。
- 新增偏离 C4 的配色、字体、渐变、图标或装饰性卡片。
- 为追求视觉完整而伪造运行指标。

## 品牌标识（SVG 真源）

- `public/logo.svg`：完整方章，深色底 `#0B0F16` + 线条 `#F3F3F4`，用于顶栏、启动页、加载态与大尺寸展示。
- `public/logo-mark.svg`：透明底纯线条，路径与 `logo.svg` 同源，用于水印、空态与低干扰装饰，避免深色实心块压住页面内容。
- `public/logo-compact.svg`：32×32 像素网格对齐的精简方章，专供 favicon 与 16/24/32px 桌面图标。整数/半整数坐标 + 偶数线宽（主笔 2px、次笔 1px），省略眉弧与笔锋，避免细线在小尺寸糊化；不用于 ≥48px 场景。
- 配色取自系统暗色令牌族（`--bg-app` 近 `#181818`、`--text-primary` 近 `#D4D4D4`）；浅色主题由 `useTheme` 下发 `--brand-logo-filter` 统一反相并回正色相，保证 5 套配色下对比度一致。
- 桌面应用图标 `apps/desktop/electron/icons/icon.ico` 共 16/24/32/48/64/256 六档：前三档由 `logo-compact.svg` 逐尺寸直出，后三档由 `logo.svg` 导出，避免小尺寸二次缩放损失。
- 像素对齐基线：以 `docs/assets/brand/logo.png`（132×121）为几何真源，方章 `x=8 y=1 w=116 h=114 r=27`；主笔 4.5px、次笔 3.4px、收笔 2.8px，均圆头；白色笔画像素重合基线 IoU ≥ 0.73，方章轮廓差异 ≤ 60px。
- 旧位图花环标 `public/logo.webp` / `logo.png` 已退役，仅留作历史资产；`acglogo.webp` 是 ACG 子系统专用标，不作为主品牌标使用。
- 禁止用文字色块或另绘图形替代矢量真源。
