#!/bin/bash
# ============================================================================
# build_python_framework.sh
# 使用 kivy-ios 2025.5.17 工具链编译 iOS 版 Python.framework
#
# 原理(kivy-ios 2025.5.17 源码已确认):
#   - toolchain build python3 --platform iphoneos-arm64 产出 dist/(静态库 + 标准库 + 头文件)
#   - kivy-ios 无 create-framework 命令,Python.framework 需手动构建:
#     1) clang -dynamiclib -force_load 把 libpython3.11.a 等静态库链成动态库
#     2) 标准库 python311.zip + site-packages 复制到 Resources/lib/
#   - C 扩展模块(_sqlite3/_ssl/_ctypes 等)按 ModulesSetup *static* 编译为
#     builtin,随 libpython3.11.a 链入,无需 .so 文件
#
# 用法:
#   cd ios && ./build_python_framework.sh
#   环境变量 KIVY_IOS_WORK_DIR 可覆盖工具链工作目录(默认 ios/kivy-ios-work)
#
# 产出:
#   ios/Frameworks/Python.framework  -> 供 Xcode 项目链接
# ============================================================================

set -e

# ----------------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------------
IOS_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$IOS_DIR")"
FRAMEWORKS_DIR="${IOS_DIR}/Frameworks"
KIVY_IOS_DIR="${KIVY_IOS_WORK_DIR:-${IOS_DIR}/kivy-ios-work}"
PYTHON_FRAMEWORK="Python.framework"

# 仅编译 python3 核心(openssl/libffi 为其自动依赖)
# 注:cryptography 无 kivy-ios recipe;Pillow recipe 名为小写 pillow,本项目不编译
RECIPES="python3"

# 仅真机 iphoneos-arm64(kivy-ios 2025.5.17 用 --platform 指定,有效值 iphoneos-arm64/iphonesimulator-arm64)
PLATFORM="iphoneos-arm64"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ----------------------------------------------------------------------------
# 环境检查
# ----------------------------------------------------------------------------
check_environment() {
    log_info "检查构建环境..."

    if [[ "$(uname)" != "Darwin" ]]; then
        log_error "此脚本只能在 macOS 上运行 (当前: $(uname))"
        exit 1
    fi

    if ! command -v xcodebuild &> /dev/null; then
        log_error "未找到 xcodebuild,请先安装 Xcode 命令行工具: xcode-select --install"
        exit 1
    fi

    if ! command -v toolchain &> /dev/null; then
        log_warn "未找到 kivy-ios toolchain,正在安装..."
        pip3 install "kivy-ios==2025.5.17" "sh==1.14.3"
        if ! command -v toolchain &> /dev/null; then
            log_error "kivy-ios 安装失败,请手动执行: pip3 install kivy-ios"
            exit 1
        fi
    fi

    if ! command -v ccache &> /dev/null; then
        log_info "未检测到 ccache，kivy-ios 需要它，尝试安装..."
        brew install ccache || { log_error "ccache 安装失败，请手动执行: brew install ccache"; exit 1; }
    fi

    # kivy-ios 2025.5.17 用 shutil.which 替代 sh.which，兼容 sh 2.x，无需检查 sh 版本

    log_info "环境检查通过"
}

# ----------------------------------------------------------------------------
# 编译 recipes
# ----------------------------------------------------------------------------
build_recipes() {
    log_info "开始编译 recipes: ${RECIPES} (平台: ${PLATFORM})"
    log_info "工作目录: ${KIVY_IOS_DIR}"

    mkdir -p "${KIVY_IOS_DIR}"
    cd "${KIVY_IOS_DIR}"

    for recipe in ${RECIPES}; do
        log_info "编译 recipe: ${recipe}"
        toolchain build "${recipe}" --platform "${PLATFORM}"
    done

    log_info "所有 recipes 编译完成"
}

# ----------------------------------------------------------------------------
# 手动构建 Python.framework(kivy-ios 无 create-framework 命令)
# ----------------------------------------------------------------------------
create_framework() {
    log_info "手动构建 Python.framework..."

    cd "${KIVY_IOS_DIR}"
    local dist="${KIVY_IOS_DIR}/dist"
    local fw="${FRAMEWORKS_DIR}/${PYTHON_FRAMEWORK}"

    # 检查构建产物
    local libpython="${dist}/lib/iphoneos/libpython3.11.a"
    if [[ ! -f "${libpython}" ]]; then
        log_error "未找到 ${libpython},请确认 toolchain build python3 已成功"
        exit 1
    fi

    mkdir -p "${fw}/Resources/lib/python3.11" "${fw}/Headers"

    # 1. 动态库:静态库合并为 Python.framework/Python
    #    -force_load 确保所有 builtin 模块符号进入动态库
    log_info "链接动态库..."
    xcrun -sdk iphoneos clang -arch arm64 -dynamiclib \
        -force_load "${dist}/lib/iphoneos/libpython3.11.a" \
        -force_load "${dist}/lib/iphoneos/libffi.a" \
        -force_load "${dist}/lib/iphoneos/libssl.a" \
        -force_load "${dist}/lib/iphoneos/libcrypto.a" \
        -lz -lbz2 -lsqlite3 -liconv \
        -framework Foundation \
        -install_name @rpath/Python.framework/Python \
        -o "${fw}/Python"

    # 2. 标准库:python311.zip(CPython 按 <PYTHONHOME>/lib/python311.zip 定位)
    log_info "复制标准库..."
    cp "${dist}/root/python3/lib/python311.zip" "${fw}/Resources/lib/python311.zip"

    # 3. site-packages(第三方纯 Python 包安装目标)
    log_info "复制 site-packages..."
    cp -R "${dist}/root/python3/lib/python3.11/site-packages" \
        "${fw}/Resources/lib/python3.11/site-packages"

    # 4. Info.plist(framework 必需)
    cat > "${fw}/Resources/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Python</string>
    <key>CFBundleIdentifier</key>
    <string>org.python.python</string>
    <key>CFBundleName</key>
    <string>Python</string>
    <key>CFBundlePackageType</key>
    <string>FMWK</string>
    <key>CFBundleShortVersionString</key>
    <string>3.11.6</string>
</dict>
</plist>
PLIST

    # 5. Headers(Embed Frameworks 的 RemoveHeadersOnCopy 会在打包 app 时删除,不影响运行)
    log_info "复制 Headers..."
    cp -R "${dist}/root/python3/include/python3.11/." "${fw}/Headers/"

    log_info "Python.framework 已构建: ${fw}"
}

# ----------------------------------------------------------------------------
# 安装纯 Python 依赖到 framework 的 site-packages
# ----------------------------------------------------------------------------
install_pure_python_deps() {
    log_info "安装纯 Python 依赖..."

    local site_packages="${FRAMEWORKS_DIR}/${PYTHON_FRAMEWORK}/Resources/lib/python3.11/site-packages"

    if [[ ! -d "${site_packages}" ]]; then
        log_error "未找到 site-packages: ${site_packages}"
        exit 1
    fi

    if [[ ! -f "${PROJECT_ROOT}/ios-requirements.txt" ]]; then
        log_error "未找到 ios-requirements.txt"
        exit 1
    fi

    # --no-deps:传递依赖已在 ios-requirements.txt 中显式列出,避免拉入不需要的包
    pip3 install \
        --target "${site_packages}" \
        --no-deps \
        -r "${PROJECT_ROOT}/ios-requirements.txt" || \
        log_warn "部分依赖安装失败,请检查 ios-requirements.txt"

    # 删除桌面架构的 C 扩展(.so/.dylib 为 macOS 架构,iOS 无法加载)
    # MarkupSafe/charset-normalizer/SQLAlchemy 均有纯 Python 回退,删除后功能正常
    find "${site_packages}" -name "*.so" -delete
    find "${site_packages}" -name "*.dylib" -delete

    log_info "纯 Python 依赖安装完成"
}

# ----------------------------------------------------------------------------
# 验证
# ----------------------------------------------------------------------------
verify_framework() {
    log_info "验证 Python.framework..."

    local fw="${FRAMEWORKS_DIR}/${PYTHON_FRAMEWORK}"

    if [[ ! -f "${fw}/Python" ]]; then
        log_error "framework 二进制缺失: ${fw}/Python"
        exit 1
    fi
    log_info "framework 二进制: $(file "${fw}/Python")"

    if [[ ! -f "${fw}/Resources/lib/python311.zip" ]]; then
        log_error "标准库缺失: ${fw}/Resources/lib/python311.zip"
        exit 1
    fi
    log_info "标准库: python311.zip ($(du -h "${fw}/Resources/lib/python311.zip" | cut -f1))"

    if [[ ! -d "${fw}/Resources/lib/python3.11/site-packages" ]]; then
        log_error "site-packages 缺失"
        exit 1
    fi

    if [[ ! -f "${fw}/Headers/Python.h" ]]; then
        log_warn "Python.h 缺失(不影响运行,仅影响 Xcode 索引)"
    fi

    log_info "验证完成"
    echo ""
    echo "============================================================"
    log_info "Python.framework 构建成功!"
    log_info "位置: ${fw}"
    log_info "下一步: 用 Xcode 打开 ios/DormManagement.xcodeproj 并构建"
    echo "============================================================"
}

# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
main() {
    echo "============================================================"
    echo "  宿舍管理系统 - iOS Python.framework 构建脚本"
    echo "============================================================"
    echo ""

    check_environment
    build_recipes
    create_framework
    install_pure_python_deps
    verify_framework
}

main "$@"