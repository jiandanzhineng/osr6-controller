import socket
import time

# 创建 UDP Socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# 允许地址重用，防止重启脚本时端口被占用
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(('0.0.0.0', 8080))

# 跟踪最近连接的客户端
last_client = None
last_client_time = 0

print('虚拟 OSR6 服务器已启动（UDP），等待 XTPlayer 连接...')
print('监听端口: 8080')

def send_response(address, response):
    """向客户端发送响应"""
    try:
        server_socket.sendto(response.encode('utf-8'), address)
        print(f'--> 发送响应: {response.strip()}')
    except Exception as e:
        print(f'发送响应失败: {e}')

try:
    while True:
        data, client_address = server_socket.recvfrom(4096)
        
        # 更新客户端信息
        last_client = client_address
        last_client_time = time.time()
        
        print(f'--- 收到数据来自: {client_address} ---')
        
        # 解码并处理数据
        decoded_data = data.decode("utf-8", errors="ignore").strip()
        print(f'指令: {decoded_data}')
        
        # 处理设备查询命令 (D0, D1, D2, D3等)
        if decoded_data.startswith('D'):
            # 设备信息查询
            if decoded_data == 'D0':
                # 设备型号查询 - 响应 OSR6
                send_response(client_address, 'OSR6\n')
            elif decoded_data == 'D1':
                # 固件版本/握手查询 - 必须返回包含 TCode 版本的响应
                # 支持的版本: "TCode v0.2", "TCode v0.3", "TCode v0.4"
                send_response(client_address, 'TCode v0.3\n')
            elif decoded_data == 'D2':
                # 硬件版本查询
                send_response(client_address, '1.0\n')
            elif decoded_data == 'D3':
                # 设备ID查询
                send_response(client_address, 'VIRTUAL-OSR6-001\n')
            else:
                # 其他 D 命令，响应空或 OK
                send_response(client_address, 'OK\n')
        elif decoded_data.startswith('V'):
            # 振动查询或命令 - 响应 OK
            send_response(client_address, 'OK\n')
        elif decoded_data == '$' or decoded_data == '':
            # 心跳或空命令 - 响应 OK
            send_response(client_address, 'OK\n')
        else:
            # 其他 TCode 命令，响应 OK 确认收到
            send_response(client_address, 'OK\n')

except KeyboardInterrupt:
    print("\n服务器正在关闭...")
finally:
    server_socket.close()
