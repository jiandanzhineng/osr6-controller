import os
import shutil
import subprocess
import sys
from pathlib import Path

def build():
    # 配置
    project_root = Path(__file__).parent.absolute()
    dist_dir = project_root / "dist"
    venv_dir = project_root / ".venv_build"
    source_file = project_root / "main_gui.py"
    icon_path = project_root / "icon" / "icon.ico"
    exe_name = "硅基之下OSR6控制插件"
    
    print(f"Project Root: {project_root}")
    
    # 1. 准备目录
    if dist_dir.exists():
        print("Cleaning old dist directory...")
        # 即使报错也忽略，防止文件占用导致脚本中断
        shutil.rmtree(dist_dir, ignore_errors=True)
    
    if not dist_dir.exists():
        dist_dir.mkdir(exist_ok=True)
    
    # 2. 检查/创建虚拟环境
    python_exe = venv_dir / "Scripts" / "python.exe"
    if not python_exe.exists():
        print("Creating virtual environment for build...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    
    # 3. 安装依赖
    print("Installing/Checking dependencies...")
    subprocess.run(
        [str(python_exe), "-m", "pip", "install", "--disable-pip-version-check", "pyserial", "paho-mqtt", "pyinstaller", "Pillow"],
        check=True
    )
    
    # 4. 执行构建
    print("Starting PyInstaller...")
    pyinstaller_exe = venv_dir / "Scripts" / "pyinstaller.exe"
    
    # 确保图标存在
    if not icon_path.exists():
        print(f"Error: Icon file not found at {icon_path}")
        return

    cmd = [
        str(pyinstaller_exe),
        "--noconfirm",
        "--onefile",
        "--noconsole",
        f"--icon={str(icon_path)}",
        f"--name={exe_name}",
        f"--distpath={str(dist_dir)}",
        f"--workpath={str(dist_dir / 'build')}",
        f"--specpath={str(dist_dir)}",
        str(source_file)
    ]
    
    print("Executing build command...")
    # 使用 shell=False 避免 Windows shell 的编码干扰
    result = subprocess.run(cmd)
    
    exe_path = dist_dir / f"{exe_name}.exe"
    
    if result.returncode == 0 and exe_path.exists():
        print("\n=== Build Successful! ===")
        print(f"Output file: {exe_path}")
    else:
        print("\n=== Build Failed ===")
        if not exe_path.exists():
            print("Executable not found.")

if __name__ == "__main__":
    build()
