"""构建Asset Agent通用二进制（C/Win32 API版本）

使用MinGW-w64编译Agent C客户端，并将产物复制到static/agent/目录。
服务器配置在用户下载时由Flask动态注入，无需编译时嵌入。

用法:
    python Auto_Setup/build_agent.py              # 编译并复制
    python Auto_Setup/build_agent.py --skip-build # 跳过编译，仅复制已有二进制
    python Auto_Setup/build_agent.py --clean      # 清理构建产物
"""
import os
import sys
import subprocess
import shutil
import argparse

# 项目根目录（相对于本脚本的上层目录）
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
AGENT_DIR = os.path.join(PROJECT_ROOT, 'agent')
STATIC_AGENT_DIR = os.path.join(PROJECT_ROOT, 'static', 'agent')

# Agent二进制文件名（与Makefile中TARGET一致）
AGENT_BINARY = 'asset-agent.exe'


def check_mingw():
    """检查MinGW-w64是否可用（make命令）"""
    try:
        result = subprocess.run(['make', '--version'],
                                capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ MinGW-w64 (make) 可用")
            return True
        else:
            print("❌ make 命令执行失败")
            return False
    except FileNotFoundError:
        print("❌ 未找到 make 命令，请安装 MinGW-w64")
        print("   下载地址: https://www.mingw-w64.org/")
        print("   或使用: choco install mingw")
        return False
    except Exception as e:
        print(f"❌ 检查MinGW-w64时出错: {e}")
        return False


def build_agent():
    """使用make编译C Agent（通用二进制，不含服务器配置）"""
    print(f"正在编译 Asset Agent...")
    print(f"  源码目录: {AGENT_DIR}")

    if not os.path.isdir(AGENT_DIR):
        print(f"❌ Agent源码目录不存在: {AGENT_DIR}")
        sys.exit(1)

    result = subprocess.run(['make', '-C', AGENT_DIR],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ 编译失败:\n{result.stderr}")
        sys.exit(1)

    # 检查编译产物
    agent_exe = os.path.join(AGENT_DIR, AGENT_BINARY)
    if not os.path.isfile(agent_exe):
        print(f"❌ 编译产物不存在: {agent_exe}")
        sys.exit(1)

    file_size = os.path.getsize(agent_exe)
    print(f"✅ 编译成功: {AGENT_BINARY} ({file_size:,} bytes)")
    return agent_exe


def copy_to_static(src_path=None):
    """将编译产物复制到static/agent/目录"""
    if src_path is None:
        src_path = os.path.join(AGENT_DIR, AGENT_BINARY)

    if not os.path.isfile(src_path):
        print(f"❌ Agent二进制不存在: {src_path}")
        print("   请先编译: python Auto_Setup/build_agent.py")
        sys.exit(1)

    # 创建目标目录
    os.makedirs(STATIC_AGENT_DIR, exist_ok=True)

    dst_path = os.path.join(STATIC_AGENT_DIR, AGENT_BINARY)
    shutil.copy2(src_path, dst_path)
    print(f"✅ 已复制到: {dst_path}")
    return dst_path


def clean_build():
    """清理构建产物"""
    print("正在清理构建产物...")

    # 清理agent目录下的.o文件和.exe文件
    result = subprocess.run(['make', '-C', AGENT_DIR, 'clean'],
                            capture_output=True, text=True)
    if result.returncode == 0:
        print("✅ 已清理 agent/ 目录构建产物")
    else:
        # Makefile的clean可能使用del命令，在非Windows环境可能失败
        print("⚠️ make clean 执行返回非零，尝试手动清理...")
        # 手动清理.o文件
        for ext in ['.o']:
            for f in os.listdir(AGENT_DIR):
                if f.endswith(ext):
                    os.remove(os.path.join(AGENT_DIR, f))
                    print(f"  已删除: {f}")

    # 清理static/agent/下的exe文件
    if os.path.isdir(STATIC_AGENT_DIR):
        for f in os.listdir(STATIC_AGENT_DIR):
            if f.endswith('.exe'):
                os.remove(os.path.join(STATIC_AGENT_DIR, f))
                print(f"  已删除: static/agent/{f}")

    print("✅ 清理完成")


def main():
    parser = argparse.ArgumentParser(
        description='构建Asset Agent通用二进制'
    )
    parser.add_argument('--skip-build', action='store_true',
                        help='跳过编译，仅复制已有二进制到static/agent/')
    parser.add_argument('--clean', action='store_true',
                        help='清理构建产物')
    args = parser.parse_args()

    if args.clean:
        clean_build()
        return

    if args.skip_build:
        # 跳过编译，仅复制
        print("⏭️ 跳过编译，仅复制已有二进制...")
        copy_to_static()
    else:
        # 检查MinGW-w64
        if not check_mingw():
            print("\n⚠️ MinGW-w64 不可用，无法编译Agent")
            print("   如果已有预编译二进制，可使用 --skip-build 跳过编译")
            sys.exit(1)

        # 编译
        build_agent()

        # 复制到static目录
        copy_to_static()

    print(f"\n===== 构建完成 =====")
    print(f"Agent文件: {os.path.join(STATIC_AGENT_DIR, AGENT_BINARY)}")
    print(f"注意: 服务器配置在用户下载时由Flask动态注入，无需编译时嵌入")


if __name__ == '__main__':
    main()