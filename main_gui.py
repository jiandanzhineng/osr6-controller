import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import socket
import threading
import serial
import serial.tools.list_ports
import re
import time
import json
import webbrowser
import paho.mqtt.client as mqtt

# ================= 核心逻辑：轴范围自适应与缓和 =================
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

        # 2. 计算当前的动态中点
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
        
        results.append(f"{axis_id}{new_val:04d}{interval}")

    return " ".join(results) + "\n"

# ================= MQTT 客户端 =================
class OSR6MqttClient:
    def __init__(self, app, broker, port, device_id):
        self.app = app
        self.broker = broker
        self.port = int(port)
        self.device_id = device_id
        # 使用 MQTT v5 回调风格 (兼容 paho-mqtt 2.x)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.running = False
        self.publish_topic = f"/dpub/{device_id}"
        self.subscribe_topic = f"/drecv/{device_id}"

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self.app.log(f"MQTT已连接: {self.broker}")
            client.subscribe(self.subscribe_topic)
            client.subscribe("/all")
        else:
            self.app.log(f"MQTT连接失败: {reason_code}")

    def on_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode('utf-8')
            self.app.log(f"收到MQTT消息: {payload}")
            data = json.loads(payload)
            self.process_message(data)
        except Exception as e:
            self.app.log(f"MQTT消息错误: {e}")

    def process_message(self, data):
        method = data.get("method")
        if method == "set":
            key = data.get("key")
            value = data.get("value")
            if key == "power":
                try:
                    val = float(value)
                    scale = max(0, min(255, val)) / 255.0
                    # 在主线程更新 UI
                    self.app.root.after(0, lambda: self.app.update_scale_from_mqtt(scale))
                except:
                    pass
        elif method == "get":
            key = data.get("key")
            if key == "power":
                 self.report_status()
        elif method == "update":
            # 处理批量更新
            for key, value in data.items():
                if key == "power":
                    try:
                        val = float(value)
                        scale = max(0, min(255, val)) / 255.0
                        self.app.root.after(0, lambda: self.app.update_scale_from_mqtt(scale))
                    except:
                        pass

    def start(self):
        try:
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
            self.running = True
            threading.Thread(target=self.heartbeat_loop, daemon=True).start()
        except Exception as e:
            self.app.log(f"MQTT启动失败: {e}")

    def stop(self):
        self.running = False
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except:
            pass

    def heartbeat_loop(self):
        while self.running:
            self.report_status()
            time.sleep(10)

    def report_status(self):
        if not self.running: return
        try:
            data = {
                "method": "report",
                "device_type": "OSR6",
                "power": int(self.app.scale_var.get() * 255),
                "battery": 100
            }
            self.client.publish(self.publish_topic, json.dumps(data))
        except Exception as e:
            self.app.log(f"心跳错误: {e}")

# ================= GUI 主程序 =================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("硅基之下OSR6控制器")
        self.root.geometry("600x600") # 增加高度以容纳MQTT设置
        
        self.udp_socket = None
        self.serial_conn = None
        self.running = False
        self.udp_thread = None
        
        self.mqtt_client = None

        self.setup_ui()
        self.refresh_ports()

    def setup_ui(self):
        # 1. 串口设置区域
        frame_serial = ttk.LabelFrame(self.root, text="串口设置", padding=10)
        frame_serial.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_serial, text="选择串口:").pack(side="left")
        self.combo_ports = ttk.Combobox(frame_serial, width=30)
        self.combo_ports.pack(side="left", padx=5)
        
        btn_refresh = ttk.Button(frame_serial, text="刷新", command=self.refresh_ports)
        btn_refresh.pack(side="left", padx=5)

        # 2. UDP 设置区域
        frame_udp = ttk.LabelFrame(self.root, text="UDP 设置", padding=10)
        frame_udp.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_udp, text="监听端口:").pack(side="left")
        self.entry_port = ttk.Entry(frame_udp, width=10)
        self.entry_port.insert(0, "8080")
        self.entry_port.pack(side="left", padx=5)
        
        # 3. MQTT 设置区域
        frame_mqtt = ttk.LabelFrame(self.root, text="MQTT 设置", padding=10)
        frame_mqtt.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(frame_mqtt, text="Broker:").pack(side="left")
        self.entry_mqtt_broker = ttk.Entry(frame_mqtt, width=15)
        self.entry_mqtt_broker.insert(0, "localhost")
        self.entry_mqtt_broker.pack(side="left", padx=2)
        
        ttk.Label(frame_mqtt, text="Port:").pack(side="left")
        self.entry_mqtt_port = ttk.Entry(frame_mqtt, width=6)
        self.entry_mqtt_port.insert(0, "1883")
        self.entry_mqtt_port.pack(side="left", padx=2)
        
        ttk.Label(frame_mqtt, text="ID:").pack(side="left")
        self.entry_mqtt_id = ttk.Entry(frame_mqtt, width=10)
        self.entry_mqtt_id.insert(0, "OSR6_001")
        self.entry_mqtt_id.pack(side="left", padx=2)

        self.mqtt_var = tk.BooleanVar(value=True)
        self.chk_mqtt = ttk.Checkbutton(frame_mqtt, text="启用MQTT", variable=self.mqtt_var)
        self.chk_mqtt.pack(side="left", padx=5)

        # 4. 缓和参数设置
        frame_scale = ttk.LabelFrame(self.root, text="缓和参数 (幅度缩放)", padding=10)
        frame_scale.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_scale, text="缩放比例 (0.0 - 1.0):").pack(side="left")
        self.scale_var = tk.DoubleVar(value=0.5)
        self.scale_slider = ttk.Scale(frame_scale, from_=0.0, to=1.0, variable=self.scale_var, orient="horizontal", length=200)
        self.scale_slider.pack(side="left", padx=10)
        self.label_scale_val = ttk.Label(frame_scale, text="0.5")
        self.label_scale_val.pack(side="left")
        
        # 更新显示的数值
        self.scale_var.trace_add("write", lambda *args: self.label_scale_val.config(text=f"{self.scale_var.get():.2f}"))

        # 5. 控制按钮
        frame_ctrl = ttk.Frame(self.root, padding=10)
        frame_ctrl.pack(fill="x", padx=10)

        self.btn_start = ttk.Button(frame_ctrl, text="启动服务", command=self.toggle_server)
        self.btn_start.pack(side="left", fill="x", expand=True)

        self.btn_reset = ttk.Button(frame_ctrl, text="刷新(换视频后点我)", command=self.reset_all_axes)
        self.btn_reset.pack(side="left", fill="x", expand=True, padx=5)

        # 6. 日志区域
        frame_log = ttk.LabelFrame(self.root, text="运行日志", padding=10)
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)

        self.text_log = scrolledtext.ScrolledText(frame_log, height=10, state="disabled")
        self.text_log.pack(fill="both", expand=True)

        # 7. 底部链接
        frame_links = ttk.Frame(self.root)
        frame_links.pack(fill="x", pady=5)

        link1 = ttk.Label(frame_links, text="使用说明", cursor="hand2", foreground="blue")
        link1.pack(side="left", expand=True)
        link1.bind("<Button-1>", lambda e: webbrowser.open("https://docs.undersilicon.com/docs/device/osr6-control-plugin"))

        ttk.Label(frame_links, text="|").pack(side="left")

        link2 = ttk.Label(frame_links, text="官方文档", cursor="hand2", foreground="blue")
        link2.pack(side="left", expand=True)
        link2.bind("<Button-1>", lambda e: webbrowser.open("https://docs.undersilicon.com/docs/"))

        ttk.Label(frame_links, text="|").pack(side="left")

        ttk.Label(frame_links, text="QQ群见文档底部").pack(side="left", expand=True)

    def log(self, message):
        self.text_log.config(state="normal")
        self.text_log.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.text_log.see("end")
        self.text_log.config(state="disabled")

    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        port_list = [f"{p.device} - {p.description}" for p in ports]
        self.combo_ports['values'] = port_list
        if port_list:
            self.combo_ports.current(0)
        else:
            self.combo_ports.set("未找到串口")

    def reset_all_axes(self):
        for tracker in axis_registry.values():
            tracker.min_val = 9999
            tracker.max_val = 0
            tracker.has_data = False
        self.log("已重置所有轴的动态范围")

    def toggle_server(self):
        if not self.running:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        # 获取串口
        selected = self.combo_ports.get()
        if not selected or "未找到串口" in selected:
            messagebox.showerror("错误", "请先选择有效的串口")
            return
        
        port_name = selected.split(" - ")[0]
        udp_port = int(self.entry_port.get())

        try:
            # 打开串口
            self.serial_conn = serial.Serial(port_name, 115200, timeout=0.1)
            self.log(f"串口 {port_name} 已打开")
        except Exception as e:
            messagebox.showerror("串口错误", str(e))
            return

        try:
            # 打开 UDP
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.bind(('0.0.0.0', udp_port))
            self.udp_socket.settimeout(1.0) # 设置超时以便线程可以退出
            self.log(f"UDP 服务器监听端口: {udp_port}")
        except Exception as e:
            if self.serial_conn: self.serial_conn.close()
            messagebox.showerror("UDP 错误", str(e))
            return
            
        # 启动 MQTT (如果勾选)
        if self.mqtt_var.get():
            try:
                broker = self.entry_mqtt_broker.get()
                port = self.entry_mqtt_port.get()
                dev_id = self.entry_mqtt_id.get()
                self.mqtt_client = OSR6MqttClient(self, broker, port, dev_id)
                self.mqtt_client.start()
            except Exception as e:
                self.log(f"MQTT 初始化错误: {e}")

        self.running = True
        self.btn_start.config(text="停止服务")
        self.combo_ports.config(state="disabled")
        self.entry_port.config(state="disabled")
        self.entry_mqtt_broker.config(state="disabled")
        self.entry_mqtt_port.config(state="disabled")
        self.entry_mqtt_id.config(state="disabled")
        
        # 启动接收线程
        self.udp_thread = threading.Thread(target=self.udp_loop, daemon=True)
        self.udp_thread.start()

    def stop_server(self):
        self.running = False
        if self.udp_thread:
            self.udp_thread.join(timeout=2.0)
        
        if self.udp_socket:
            self.udp_socket.close()
            self.udp_socket = None
            
        if self.serial_conn:
            self.serial_conn.close()
            self.serial_conn = None
            
        if self.mqtt_client:
            self.mqtt_client.stop()
            self.mqtt_client = None
            
        self.log("服务已停止")
        self.btn_start.config(text="启动服务")
        self.combo_ports.config(state="normal")
        self.entry_port.config(state="normal")
        self.entry_mqtt_broker.config(state="normal")
        self.entry_mqtt_port.config(state="normal")
        self.entry_mqtt_id.config(state="normal")

    def update_scale_from_mqtt(self, val):
        self.scale_var.set(max(0.0, min(1.0, val)))
        self.log(f"MQTT更新Power: {int(val*255)} (Scale: {val:.2f})")

    def udp_loop(self):
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(4096)
                decoded_data = data.decode("utf-8", errors="ignore").strip()
                
                # 处理 TCode 指令
                if decoded_data.startswith('L') or decoded_data.startswith('R'): # 简单的 TCode 判断
                    scale = self.scale_var.get()
                    processed_cmd = process_tcode(decoded_data, scale)
                    
                    if self.serial_conn and self.serial_conn.is_open:
                        self.serial_conn.write(processed_cmd.encode('utf-8'))
                        # self.log(f"发送: {processed_cmd.strip()}") # 频繁发送可注释掉日志
                
                # 处理设备查询命令 (参考 udp_server.py)
                elif decoded_data.startswith('D'):
                    resp = 'OK\n'
                    if decoded_data == 'D0': resp = 'OSR6\n'
                    elif decoded_data == 'D1': resp = 'TCode v0.3\n'
                    elif decoded_data == 'D2': resp = '1.0\n'
                    elif decoded_data == 'D3': resp = 'GUI-OSR6-001\n'
                    
                    self.udp_socket.sendto(resp.encode('utf-8'), addr)
                    self.log(f"回复查询 {decoded_data}: {resp.strip()}")

                elif decoded_data.startswith('V') or decoded_data == '$' or decoded_data == '':
                    self.udp_socket.sendto(b'OK\n', addr)
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.log(f"接收错误: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
