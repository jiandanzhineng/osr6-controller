# `main_gui.py` 增加处理模式切换计划

## Summary

* 目标：在 `main_gui.py` 的 GUI 上增加一个“缩放模式”选项，让用户可在“比例”和“极值”之间切换 TCode 处理方式。

* 默认行为：GUI 默认选中“极值”，保持当前程序的默认处理逻辑不变。

* 切换策略：切换模式时保留当前已学习的动态范围，不自动重置各轴 `min/max`。

## Current State Analysis

* `main_gui.py` 当前只有一套缩放逻辑，集中在 `AxisTracker.update_and_scale()` 中。

* 现在的 `process_tcode(command_line, scale)` 只接收缩放比例 `scale`，没有模式参数，因此调用方无法决定使用哪种算法。

* GUI 的“缓和参数”区域目前只有一个滑块 `self.scale_var`，没有“处理方式”选择控件。

* UDP 接收链路在 `udp_loop()` 中固定调用 `process_tcode(decoded_data, scale)`，说明只需要在这一处把模式传下去即可。

* `reset_all_axes()` 已存在，但本次已明确切换模式时不自动调用它。

## Proposed Changes

### 1. 在核心逻辑中同时保留两种算法

* 文件：`e:\develop\osr6controller\main_gui.py`

* 位置：`AxisTracker`、`process_tcode()`

* 改法：

  * 在 `AxisTracker` 中拆分或补充两套明确的方法：

    * `比例`：围绕动态中点整体按比例压缩，对应老方式。

    * `极值`：围绕动态中点限制上下边界，区间内原样输出、超出才截断，对应新方式。

  * 保留当前动态范围学习逻辑，避免为两种模式各自维护一套独立状态。

  * `process_tcode()` 增加一个模式参数，例如 `mode`，按当前 GUI 选择决定调用哪套算法。

  * 输出格式、TCode 解析规则、`0-9999` 安全边界保持不变。

### 2. 在 GUI 的缓和参数区域增加模式选择控件

* 文件：`e:\develop\osr6controller\main_gui.py`

* 位置：`App.setup_ui()`

* 改法：

  * 在现有 `frame_scale` 区域新增一个模式变量，例如 `self.scale_mode_var`。

  * 增加一个标题为 `缩放模式` 的模式选择控件。

  * 选项文案使用：

    * `比例`

    * `极值`

  * 默认值设为 `极值`。

  * 控件形式优先使用和当前 Tk/ttk 风格一致、占用空间较小的单选控件或下拉控件；执行时保持界面简洁，不额外引入复杂布局。

### 3. 将所选模式接入实际处理链路

* 文件：`e:\develop\osr6controller\main_gui.py`

* 位置：`udp_loop()`

* 改法：

  * 在处理 TCode 前，同时读取：

    * `scale = self.scale_var.get()`

    * `mode = self.scale_mode_var.get()`

  * 将 `mode` 传给 `process_tcode()`。

  * MQTT 对 `power` 的处理保持只影响缩放比例，不改变模式选择。

### 4. 更新说明文字，避免 GUI 与实际行为不一致

* 文件：`e:\develop\osr6controller\main_gui.py`

* 位置：

  * `AxisTracker` / `process_tcode()` 的简短说明

  * `frame_scale` 附近的界面文案

* 改法：

  * 把说明改成“可选择缩放模式 + 调整缩放比例”这一语义。

  * 保持注释简短，只写出 `比例=老方式`、`极值=新方式` 这层映射，不增加过多说明。

## Assumptions & Decisions

* 本次只改 `main_gui.py`，不改 `osr6.py`、`README_GUI.md` 或其他脚本。

* `比例` 定义为原来的整体比例压缩算法：`midpoint + (current - midpoint) * scale`。

* `极值` 定义为当前代码中的上下边界限制算法。

* 默认模式为 `极值`，以保持当前版本的默认行为。

* 切换模式时保留当前动态范围，不自动重置；用户仍可手动点击“刷新(换视频后点我)”来清空学习结果。

## Verification Steps

* 代码结构检查：

  * `process_tcode()` 已支持接收模式参数。

  * `udp_loop()` 已把 GUI 当前模式传入处理函数。

  * GUI 已新增 `缩放模式` 选择控件，且默认值为 `极值`。

* 行为验证：

  * 选择 `比例` 时，处理结果应回到整体比例压缩逻辑。

  * 选择 `极值` 时，处理结果应保持当前的上下边界限制逻辑。

  * 只切换模式、不点“刷新”时，已学习的动态范围应继续生效。

* 基础检查：

  * `main_gui.py` 无语法错误。

  * 相关修改不影响 MQTT 更新缩放比例、串口发送和 UDP 接收主流程。

