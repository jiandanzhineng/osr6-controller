# `main_gui.py` 缩放上限限制改造计划

## Summary

* 目标：把 `main_gui.py` 里的 TCode 缩放方式，从“围绕中心点整体按比例压缩”改为“围绕中心点限制上下边界”。

* 作用范围：只修改 `main_gui.py`，不改 `osr6.py` 和说明文档。

* 目标行为：对每个轴继续维护动态范围和中心点，但输出值不再整体乘比例；而是计算一个新的下限和上限，超出新区间的值截断到边界，落在新区间内的值原样输出。

## Current State Analysis

* `main_gui.py` 中的 `AxisTracker.update_and_scale()` 目前会先更新每个轴的 `min_val` / `max_val`，再计算动态中心点。

* 当前算法是：

  * `dynamic_midpoint = (max_val + min_val) / 2`

  * `scaled_val = dynamic_midpoint + (current_val - dynamic_midpoint) * scale`

* 这意味着所有高于或低于中心点的值都会被整体压缩，不符合“只限制上下边界，区间内值保持不变”的新需求。

* `process_tcode()` 只负责解析 TCode、获取对应轴的 `AxisTracker`，并调用 `update_and_scale()` 返回新值。

* `reset_all_axes()` 会重置所有轴的动态范围，因此新方案仍可复用这套“换视频后重新学习范围”的机制。

## Proposed Changes

### 1. 修改 `main_gui.py` 中的缩放核心算法

* 文件：`e:\develop\osr6controller\main_gui.py`

* 位置：`AxisTracker.update_and_scale()`

* 改法：

  * 保留当前的动态范围学习逻辑：继续更新 `min_val`、`max_val`，并继续计算动态中心点。

* <br />

  * 把“整体压缩公式”改成“上下边界截断公式”。

* <br />

  * 新公式按“保留中心点概念”同时处理上下两段：

  * `dynamic_midpoint = (max_val + min_val) / 2`

* <br />

  * `scaled_lower_limit = dynamic_midpoint - (dynamic_midpoint - min_val) * scale`
    \- `scaled_upper_limit = dynamic_midpoint + (max_val - dynamic_midpoint) * scale`

* 输出规则：

* <br />

  * 如果 `current_val < scaled_lower_limit`，输出 `scaled_lower_limit`

* <br />

  * 如果 `scaled_lower_limit <= current_val <= scaled_upper_limit`，直接输出 `current_val`

* <br />

  * 如果 `current_val > scaled_upper_limit`，输出 `scaled_upper_limit`

* 最后继续保留 `0-9999` 的边界保护和四位格式化输出。

### 2. 同步调整函数说明，避免语义误导

* 文件：`e:\develop\osr6controller\main_gui.py`

* 位置：

  * `AxisTracker` 类说明

  * `update_and_scale()` 内的注释

  * `process_tcode()` 的 docstring（如果当前描述仍强调“自适应缩放”）

* 改法：

* <br />

  * 把说明改成更贴近实际行为，比如“学习动态范围并限制上下边界”。

* 保持注释简短，只保留帮助理解新算法所需的最少说明。

### 3. 保持调用链不变，减少改动面

* 文件：`e:\develop\osr6controller\main_gui.py`

* 位置：`process_tcode()`、`udp_loop()`

* 改法：

  * 不改 TCode 解析格式。

  * 不改 GUI 滑块、MQTT 同步、串口发送流程。

* <br />

  * `scale` 仍然沿用 `0.0 - 1.0` 的输入范围，只改变其语义：从“整体缩放比例”变为“围绕中心点保留的有效范围比例”。

## Assumptions & Decisions

* 只改 `main_gui.py`，因为本次明确指定该文件；`osr6.py` 先保持原样。

* “按固定中心点”这里采用当前代码已有的动态中心点逻辑，不额外引入新的固定常量中心。

* 新方案同时限制下限和上限，不对新边界区间内的输入做额外压缩。

* 当某个轴刚开始学习范围时，如果 `min_val == max_val`，公式仍能成立，此时上下限都等于当前值，不需要额外分支。

## Verification Steps

* 静态检查：

  * 检查 `update_and_scale()` 是否已不再使用“偏移量整体乘比例”的旧公式。

  * 检查 `process_tcode()` 的输出格式是否仍为 `AXIS + 4位数值 + 可选I参数`。

* 关键样例验证：

  * 已学习范围近似为 `min=-100, max=100, midpoint=0, scale=0.1` 时：

    * 新下限应为 `-10`

    * 新上限应为 `10`

    * `current_val=5` 时原样输出 `5`

    * `current_val=50` 时截断为 `10`

    * `current_val=-50` 时截断为 `-10`

* 边界验证：

  * `scale=0` 时，上下限都应收缩到中心点。

  * `scale=1` 时，不应产生额外截断，输出应接近原值。

  * 输出仍应被限制在 `0-9999` 范围内。

* 代码质量验证：

  * 用诊断工具检查 `main_gui.py` 是否引入语法或明显静态错误。

## Note

* 计划按“保留中心点概念 + 同时限制上下边界”执行；也就是先学习每个轴的动态中心点，再把可输出范围收紧到中心点附近，超出新区间的值才截断。

