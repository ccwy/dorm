/* main.c - Asset Agent 入口点
 * WinMain + 命令行解析 + 防多实例 + 日志初始化
 */
#include "config.h"
#include "service.h"
#include "collector.h"
#include "reporter.h"
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <string.h>

/* safe_strncpy: strncpy with guaranteed null-termination */
static void safe_strncpy(char *dst, const char *src, size_t bufsize) {
    strncpy(dst, src, bufsize - 1);
    dst[bufsize - 1] = '\0';
}

#define MUTEX_NAME L"Global\\AssetAgent_SingleInstance"

#ifndef AGENT_VERSION
#define AGENT_VERSION "1.0.0"
#endif

/* g_log_file 在 config.h 中声明，service.c 中定义 */

static void print_usage(void) {
    printf("Asset Agent v%s\n", AGENT_VERSION);
    printf("用法:\n");
    printf("  AssetAgent           启动Agent服务\n");
    printf("  AssetAgent [stop|--stop]          停止运行中的Agent\n");
    printf("  AssetAgent [uninstall|--uninstall] 卸载Agent\n");
    printf("  AssetAgent [edit_info|--edit-info] 编辑资产信息\n");
    printf("  AssetAgent version   显示版本号\n");
}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nCmdShow) {
    /* 命令行参数解析 */
    int argc = 0;
    LPWSTR *argvW = CommandLineToArgvW(GetCommandLineW(), &argc);

    if (argc > 1) {
        char arg1[64] = {0};
        if (argvW && argvW[1]) {
            WideCharToMultiByte(CP_ACP, 0, argvW[1], -1, arg1, sizeof(arg1) - 1, NULL, NULL);
        }
        LocalFree(argvW);

        if (strcmp(arg1, "stop") == 0 || strcmp(arg1, "--stop") == 0) {
            return execute_stop();
        } else if (strcmp(arg1, "uninstall") == 0 || strcmp(arg1, "--uninstall") == 0) {
            return execute_uninstall();
        } else if (strcmp(arg1, "edit_info") == 0 || strcmp(arg1, "--edit-info") == 0) {
            return execute_edit_info();
        } else if (strcmp(arg1, "version") == 0) {
            printf("Asset Agent v%s\n", AGENT_VERSION);
            return 0;
        } else if (strcmp(arg1, "--help") == 0 || strcmp(arg1, "-h") == 0) {
            print_usage();
            return 0;
        }
    }
    if (argvW) LocalFree(argvW);

    /* 防多实例 */
    HANDLE hMutex = CreateMutexW(NULL, TRUE, MUTEX_NAME);
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        /* 已有实例运行，尝试发送IPC命令激活 */
        MessageBoxW(NULL, L"Asset Agent 已在运行", L"提示", MB_OK | MB_ICONINFORMATION);
        if (hMutex) CloseHandle(hMutex);
        return 1;
    }

    /* 初始化日志 */
    init_logger();
    log_write("Asset Agent v%s 启动", AGENT_VERSION);

    /* 加载配置 */
    AgentConfig *config = LoadConfig();
    if (!config) {
        log_write("配置加载失败");
        MessageBoxW(NULL, L"配置加载失败", L"错误", MB_OK | MB_ICONERROR);
        ReleaseMutex(hMutex);
        CloseHandle(hMutex);
        return 1;
    }

    /* 如果没有server_url，弹出配置窗口 */
    if (strlen(EffectiveServerURL(config)) == 0) {
        log_write("未配置服务器地址，弹出配置窗口");
        char server_url[MAX_URL_LEN] = {0};
        char api_key[MAX_KEY_LEN] = {0};
        if (showSetupWindow(server_url, sizeof(server_url),
                            api_key, sizeof(api_key)) == 0) {
            /* 用户取消或窗口创建失败 */
            log_write("配置窗口取消，退出");
            FreeConfig(config);
            ReleaseMutex(hMutex);
            CloseHandle(hMutex);
            return 0;
        }
        safe_strncpy(config->server_url, server_url, MAX_URL_LEN);
        safe_strncpy(config->api_key, api_key, MAX_KEY_LEN);
        SaveConfig(config);
    }

    /* 确保开机自启 */
    ensure_autostart();

    /* 创建并运行Agent */
    Agent *agent = agent_create(config);
    if (!agent) {
        log_write("Agent创建失败");
        FreeConfig(config);
        ReleaseMutex(hMutex);
        CloseHandle(hMutex);
        return 1;
    }

    agent_run(agent);
    agent_destroy(agent);

    /* 清理 */
    FreeConfig(config);
    if (g_log_file) {
        fclose(g_log_file);
        g_log_file = NULL;
    }
    ReleaseMutex(hMutex);
    CloseHandle(hMutex);

    return 0;
}