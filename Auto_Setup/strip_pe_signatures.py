#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PE文件签名剥离工具

用于剥离PyInstaller打包产物中.pyd/.dll文件的Authenticode签名。
Windows 7缺少SHA-2代码签名支持(KB4474419)时，无法验证SHA-256签名，
导致DLL加载失败：ImportError: DLL load failed while importing _socket: 参数错误

剥离签名后，Windows加载器不会尝试验证签名，直接加载DLL，从而绕过此问题。

用法:
    python strip_pe_signatures.py <dist目录路径>
    python strip_pe_signatures.py dist/行政后勤管理系统

原理:
    PE文件格式中，Authenticode签名存储在文件末尾的Certificate Table中。
    Optional Header的DATA_DIRECTORY[4]指向该签名数据。
    本脚本将签名数据从文件中移除，并清零目录条目，使Windows跳过签名验证。

注意:
    - 仅处理.pyd和.dll文件，不影响.exe文件
    - 剥离签名不影响DLL功能，仅移除数字签名信息
    - 此操作不可逆，建议在打包流程中自动执行
"""

import os
import sys
import struct
import glob


def strip_pe_signature(filepath):
    """
    剥离单个PE文件的Authenticode签名
    
    Args:
        filepath: PE文件路径
        
    Returns:
        tuple: (是否成功, 描述信息)
    """
    try:
        with open(filepath, 'rb') as f:
            data = bytearray(f.read())
        
        if len(data) < 64:
            return False, "文件太小，不是有效的PE文件"
        
        # 验证DOS头标志 MZ
        if data[0:2] != b'MZ':
            return False, "不是有效的PE文件（缺少MZ标志）"
        
        # 获取PE头偏移
        pe_offset = struct.unpack_from('<I', data, 0x3C)[0]
        
        if pe_offset + 4 > len(data):
            return False, "PE头偏移超出文件范围"
        
        # 验证PE头标志 PE\0\0
        if data[pe_offset:pe_offset+4] != b'PE\0\0':
            return False, "不是有效的PE文件（缺少PE标志）"
        
        # COFF头
        coff_offset = pe_offset + 4
        machine = struct.unpack_from('<H', data, coff_offset)[0]
        # 0x14c = i386, 0x8664 = AMD64
        if machine not in (0x14c, 0x8664):
            return False, f"不支持的机器类型: 0x{machine:04x}"
        
        optional_header_size = struct.unpack_from('<H', data, coff_offset + 16)[0]
        
        if optional_header_size == 0:
            return False, "无Optional Header"
        
        # Optional Header
        opt_offset = coff_offset + 20
        magic = struct.unpack_from('<H', data, opt_offset)[0]
        
        # PE32: 0x10b, PE32+: 0x20b
        if magic == 0x10b:
            # PE32格式
            num_data_dirs = struct.unpack_from('<I', data, opt_offset + 92)[0]
            cert_dir_offset = opt_offset + 96 + 4 * 8  # 第5个目录项(index=4)
        elif magic == 0x20b:
            # PE32+格式(64位)
            num_data_dirs = struct.unpack_from('<I', data, opt_offset + 108)[0]
            cert_dir_offset = opt_offset + 112 + 4 * 8  # 第5个目录项(index=4)
        else:
            return False, f"未知的Optional Header magic: 0x{magic:04x}"
        
        if num_data_dirs < 5:
            return False, "无Certificate Table目录项"
        
        # 读取Certificate Table目录项
        cert_va = struct.unpack_from('<I', data, cert_dir_offset)[0]
        cert_size = struct.unpack_from('<I', data, cert_dir_offset + 4)[0]
        
        if cert_va == 0 or cert_size == 0:
            return False, "无签名（文件未签名）"
        
        # 剥离签名：截断文件到签名数据之前，并清零目录项
        # Certificate Table始终在文件末尾，VA就是文件偏移
        new_file_size = cert_va
        
        # 清零Certificate Table目录项
        struct.pack_into('<I', data, cert_dir_offset, 0)      # VirtualAddress = 0
        struct.pack_into('<I', data, cert_dir_offset + 4, 0)  # Size = 0
        
        # 写回文件（截断到签名之前）
        with open(filepath, 'wb') as f:
            f.write(data[:new_file_size])
        
        return True, f"已剥离签名 ({cert_size} 字节)"
        
    except Exception as e:
        return False, f"处理失败: {e}"


def process_directory(dist_dir):
    """
    处理目录中的所有.pyd和.dll文件
    
    Args:
        dist_dir: PyInstaller输出目录路径
    """
    if not os.path.isdir(dist_dir):
        print(f"错误: 目录不存在 - {dist_dir}")
        sys.exit(1)
    
    # 查找所有.pyd和.dll文件
    extensions = ('*.pyd', '*.dll')
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(dist_dir, '**', ext), recursive=True))
    
    if not files:
        print(f"未找到.pyd或.dll文件 - {dist_dir}")
        return
    
    print(f"找到 {len(files)} 个文件待处理")
    print("-" * 60)
    
    success_count = 0
    skip_count = 0
    fail_count = 0
    
    for filepath in sorted(files):
        rel_path = os.path.relpath(filepath, dist_dir)
        ok, msg = strip_pe_signature(filepath)
        
        if ok:
            success_count += 1
            print(f"  [剥离] {rel_path} - {msg}")
        elif "无签名" in msg:
            skip_count += 1
            # 未签名的文件不需要处理，静默跳过
        else:
            fail_count += 1
            print(f"  [跳过] {rel_path} - {msg}")
    
    print("-" * 60)
    print(f"完成: 剥离 {success_count} 个, 跳过 {skip_count + fail_count} 个")
    
    if success_count > 0:
        print(f"\n已剥离 {success_count} 个文件的Authenticode签名。")
        print("Windows 7 用户无需安装 KB4474419 补丁即可正常运行程序。")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python strip_pe_signatures.py <dist目录路径>")
        print("示例: python strip_pe_signatures.py dist/行政后勤管理系统")
        sys.exit(1)
    
    target_dir = sys.argv[1]
    print(f"=" * 60)
    print(f"PE签名剥离工具 - Win7兼容性处理")
    print(f"=" * 60)
    print(f"目标目录: {target_dir}")
    print()
    
    process_directory(target_dir)