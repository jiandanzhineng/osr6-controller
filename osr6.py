import socket
import re

# ================= 配置参数 =================
LISTEN_PORT = 8080
AMPLITUDE_SCALE = 0.5  # 动作幅度缩放比例：0.5 代表将实际范围缩小到 50%
# ===========================================

class AxisTracker:
    """用于追踪单个轴的动态范围和计算"""
    def __init__(self, name):
        self.name = name
        self.min_val = 9999  # 初始设为最大
        self.max_val = 0     # 初始设为最小
        self.has_data = False

    def update_and_scale(self, current_val, scale):
        # 1. 更新观察到的实际边界
        if current_val < self.min_val: self.min_val = current_val
        if current_val > self.max_val: self.max_val = current_val
        self.has_data = True

        # 2. 计算当前的动态中点和动态范围
        # 如果当前脚本只在 4000-6000 运行，中点就是 5000，实际行程是 2000
        dynamic_midpoint = (self.max_val + self.min_val) / 2
        
        # 3. 执行缩放算法：
        # 新值 = 动态中点 + (原始值 - 动态中点) * 缩放比例
        offset = current_val - dynamic_midpoint
        scaled_val = int(dynamic_midpoint + (offset * scale))

        # 4. 安全边界检查 (0-9999)
        scaled_val = max(0, min(9999, scaled_val))
        return scaled_val

# 全局存储所有轴的状态
axis_registry = {}

def process_tcode(command_line, scale):
    """解析 TCode 并应用自适应缩放"""
    # 匹配轴标识(如L0), 4位数值(如4787), 时间参数(如I10)
    pattern = r'([A-Z][0-9])(\d{4})(I\d+)'
    matches = re.findall(pattern, command_line)
    
    if not matches:
        return command_line

    results = []
    for axis_id, val_str, interval in matches:
        current_val = int(val_str)

        # 如果是第一次见到这个轴，为其创建一个追踪器
        if axis_id not in axis_registry:
            axis_registry[axis_id] = AxisTracker(axis_id)
        
        tracker = axis_registry[axis_id]
        
        # 获取缩放后的值
        new_val = tracker.update_and_scale(current_val, scale)
        
        # 打印调试信息（可选，可以看到动态范围的变化）
        # print(f"[{axis_id}] 范围: {tracker.min_val}-{tracker.max_val} 中点: {int((tracker.max_val+tracker.min_val)/2)}")
        
        results.append(f"{axis_id}{new_val:04d}{interval}")

    return " ".join(results)

def start_middleware():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind(('0.0.0.0', LISTEN_PORT))
        server_socket.listen(1)
        print(f"--- 自适应 OSR6 中间件已启动 ---")
        print(f"监听端口: {LISTEN_PORT} | 幅度设定: {AMPLITUDE_SCALE*100}%")
        print("提示: 随着脚本播放，中间件会自动学习每个轴的边界范围。\n")

        while True:
            client_socket, addr = server_socket.accept()
            print(f"MFP 已连接: {addr}")
            
            try:
                buffer = ""
                while True:
                    data = client_socket.recv(4096).decode('utf-8', errors='ignore')
                    if not data: break
                    
                    buffer += data
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            scaled_line = process_tcode(line, AMPLITUDE_SCALE)
                            # 模拟输出到真实设备
                            print(f"OUT: {scaled_line}")
                            
            except Exception as e:
                print(f"异常: {e}")
            finally:
                client_socket.close()
                print("连接已断开。")

    except KeyboardInterrupt:
        print("\n正在关闭...")
    finally:
        server_socket.close()

if __name__ == "__main__":
    start_middleware()