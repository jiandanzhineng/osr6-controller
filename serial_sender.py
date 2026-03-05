import serial
import serial.tools.list_ports
import time

def list_serial_ports():
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("未找到可用的串口")
        return []
    
    print("可用的串口列表:")
    for i, port in enumerate(ports, 1):
        print(f"{i}. {port.device} - {port.description}")
    
    return ports

def select_port(ports):
    while True:
        try:
            choice = input("请选择串口编号 (输入 q 退出): ")
            if choice.lower() == 'q':
                return None
            
            index = int(choice) - 1
            if 0 <= index < len(ports):
                return ports[index].device
            else:
                print("无效的选择，请重新输入")
        except ValueError:
            print("请输入有效的数字")

def send_ok_to_serial(port_name):
    try:
        ser = serial.Serial(
            port_name,
            baudrate=115200,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1
        )
        print(f"已连接到 {port_name}")
        print(f"串口配置: 波特率=115200, 数据位=8, 校验位=无, 停止位=1")
        print("开始每秒发送 'OK' (按 Ctrl+C 停止)")
        
        try:
            while True:
                ser.write(b'OK\n')
                print(f"[{time.strftime('%H:%M:%S')}] 已发送: OK")
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n停止发送")
        
        ser.close()
        print(f"已关闭串口 {port_name}")
    except serial.SerialException as e:
        print(f"串口错误: {e}")

def main():
    print("串口通信工具")
    print("=" * 30)
    
    ports = list_serial_ports()
    if not ports:
        return
    
    selected_port = select_port(ports)
    if selected_port:
        send_ok_to_serial(selected_port)

if __name__ == "__main__":
    main()
