/* service.c - Agent服务生命周期管理实现
 * 合并: agent生命周期 + autostart + IPC + CLI + setup_ui + info_ui
 */
#include "service.h"
#include "cJSON.h"
#include "fingerprint.h"
#include <windows.h>
#include <sddl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <shellapi.h>

/* ================================================================
 *  日志实现
 * ================================================================ */
FILE *g_log_file = NULL;

void init_logger(void) {
    CreateDirectoryA(PROGRAM_DATA_DIR, NULL);
    g_log_file = fopen(PROGRAM_DATA_DIR "\\agent.log", "a");
}

void log_write(const char *fmt, ...) {
    if (!g_log_file) return;
    SYSTEMTIME st;
    GetLocalTime(&st);
    fprintf(g_log_file, "[%04d-%02d-%02d %02d:%02d:%02d] ",
            st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
    va_list args;
    va_start(args, fmt);
    vfprintf(g_log_file, fmt, args);
    va_end(args);
    fprintf(g_log_file, "\n");
    fflush(g_log_file);
}

/* ================================================================
 *  开机自启（注册表 Run 键）
 * ================================================================ */
#define AUTOSTART_KEY_PATH L"Software\\Microsoft\\Windows\\CurrentVersion\\Run"
#define APP_NAME_W         L"AssetAgent"

void ensure_autostart(void) {
    char exe_path[MAX_PATH];
    if (!GetModuleFileNameA(NULL, exe_path, MAX_PATH)) {
        log_write("获取exe路径失败: %lu", GetLastError());
        return;
    }

    /* 检查是否已注册 */
    HKEY hKey;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, AUTOSTART_KEY_PATH,
                       0, KEY_QUERY_VALUE, &hKey) == ERROR_SUCCESS) {
        wchar_t val[MAX_PATH];
        DWORD val_size = sizeof(val);
        if (RegQueryValueExW(hKey, APP_NAME_W, NULL, NULL,
                              (LPBYTE)val, &val_size) == ERROR_SUCCESS) {
            RegCloseKey(hKey);
            return; /* 已注册 */
        }
        RegCloseKey(hKey);
    }

    /* 注册到 HKCU\...\Run（无需管理员权限） */
    wchar_t w_exe_path[MAX_PATH];
    MultiByteToWideChar(CP_ACP, 0, exe_path, -1, w_exe_path, MAX_PATH);
    if (RegOpenKeyExW(HKEY_CURRENT_USER, AUTOSTART_KEY_PATH,
                       0, KEY_SET_VALUE, &hKey) == ERROR_SUCCESS) {
        RegSetValueExW(hKey, APP_NAME_W, 0, REG_SZ,
                        (const BYTE*)w_exe_path,
                        (DWORD)(wcslen(w_exe_path) + 1) * sizeof(wchar_t));
        RegCloseKey(hKey);
        log_write("开机自启已注册");
    }
}

void remove_autostart(void) {
    HKEY hKey;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, AUTOSTART_KEY_PATH,
                       0, KEY_SET_VALUE, &hKey) == ERROR_SUCCESS) {
        RegDeleteValueW(hKey, APP_NAME_W);
        RegCloseKey(hKey);
    }
}

/* ================================================================
 *  IPC 命名管道
 * ================================================================ */
#define PIPE_NAME L"\\\\.\\pipe\\AssetAgent"
#define PIPE_BUFFER_SIZE 4096

static Agent *g_agent = NULL;

/* ipc_server_thread: 命名管道服务端线程 */
static DWORD WINAPI ipc_server_thread(LPVOID param) {
    char cmd_chan[64] = {0};

    /* 创建SDDL安全描述符：仅管理员(BA)和SYSTEM(SY)有完全控制权限 */
    PSECURITY_DESCRIPTOR pSD = NULL;
    SECURITY_ATTRIBUTES sa;
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(
            L"D:(A;;GA;;;BA)(A;;GA;;;SY)", SDDL_REVISION_1, &pSD, NULL)) {
        log_write("创建安全描述符失败: %lu", GetLastError());
        return 1;
    }
    sa.nLength = sizeof(SECURITY_ATTRIBUTES);
    sa.lpSecurityDescriptor = pSD;
    sa.bInheritHandle = FALSE;

    while (g_agent && g_agent->running) {
        HANDLE hPipe = CreateNamedPipeW(PIPE_NAME,
            PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
            1, PIPE_BUFFER_SIZE, PIPE_BUFFER_SIZE, 0, &sa);
        if (hPipe == INVALID_HANDLE_VALUE) {
            Sleep(1000);
            continue;
        }

        if (ConnectNamedPipe(hPipe, NULL) || GetLastError() == ERROR_PIPE_CONNECTED) {
            char buf[PIPE_BUFFER_SIZE] = {0};
            DWORD bytes_read = 0;
            if (ReadFile(hPipe, buf, PIPE_BUFFER_SIZE - 1, &bytes_read, NULL) && bytes_read > 0) {
                buf[bytes_read] = '\0';
                cJSON *json = cJSON_Parse(buf);
                if (json) {
                    cJSON *cmd = cJSON_GetObjectItem(json, "command");
                    if (cmd && cmd->valuestring[0]) {
                        strncpy(cmd_chan, cmd->valuestring, sizeof(cmd_chan) - 1);
                        /* 处理命令 */
                        if (strcmp(cmd_chan, "stop") == 0) {
                            log_write("收到IPC停止命令");
                            g_agent->running = 0;
                        } else if (strcmp(cmd_chan, "report_now") == 0) {
                            log_write("收到IPC立即上报命令");
                            /* 在下次心跳循环中处理 */
                        } else if (strcmp(cmd_chan, "edit_info") == 0) {
                            log_write("收到IPC编辑信息命令");
                            /* KNOWN_LIMIT: 信息编辑窗口未实现，命令已接收但无UI响应 */
                        }
                    }
                    cJSON_Delete(json);
                }
            }
        }
        DisconnectNamedPipe(hPipe);
        CloseHandle(hPipe);
    }

    /* 释放安全描述符内存 */
    if (pSD) LocalFree(pSD);
    return 0;
}

void start_ipc_server(Agent *agent) {
    g_agent = agent;
    CreateThread(NULL, 0, ipc_server_thread, NULL, 0, NULL);
}

int send_ipc_command(const char *command) {
    HANDLE hPipe = CreateFileW(PIPE_NAME, GENERIC_WRITE, 0,
                                NULL, OPEN_EXISTING, 0, NULL);
    if (hPipe == INVALID_HANDLE_VALUE) return -1;

    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "command", command);
    char *data = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);

    DWORD bytes_written = 0;
    WriteFile(hPipe, data, (DWORD)strlen(data), &bytes_written, NULL);
    free(data);
    CloseHandle(hPipe);
    return 0;
}

/* ================================================================
 *  CLI 命令
 * ================================================================ */
int execute_stop(void) {
    if (send_ipc_command("stop") == 0) {
        printf("Agent 已停止\n");
    } else {
        printf("Agent 未在运行\n");
    }
    return 0;
}

int execute_uninstall(void) {
    /* 1. 尝试通过命名管道发送stop命令 */
    send_ipc_command("stop");
    /* 2. 等待进程退出（最多10秒） */
    Sleep(10000);
    /* 3. 删除注册表Run键 */
    remove_autostart();
    /* 4. 使用Win32 API删除ProgramData目录（替代不安全的system()调用） */
    WCHAR wpath[MAX_PATH] = {0};
    MultiByteToWideChar(CP_ACP, 0, PROGRAM_DATA_DIR, -1, wpath, MAX_PATH);
    /* SHFileOperationW的pFrom需要双null终止的字符串 */
    wpath[wcslen(wpath) + 1] = L'\0';

    SHFILEOPSTRUCTW op = {0};
    op.wFunc = FO_DELETE;
    op.pFrom = wpath;
    op.fFlags = FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI;
    int result = SHFileOperationW(&op);
    if (result != 0) {
        log_write("卸载删除目录失败: 错误码 %d", result);
    } else {
        log_write("已删除安装目录: %s", PROGRAM_DATA_DIR);
    }
    printf("Agent 已卸载\n");
    return 0;
}

int execute_edit_info(void) {
    /* 加载当前配置 */
    AgentConfig *config = LoadConfig();
    if (!config) {
        printf("无法加载配置\n");
        return -1;
    }

    char location[MAX_FIELD_LEN] = {0};
    char department[MAX_FIELD_LEN] = {0};
    char responsible_person[MAX_FIELD_LEN] = {0};

    strncpy(location, config->location, MAX_FIELD_LEN - 1);
    strncpy(department, config->department, MAX_FIELD_LEN - 1);
    strncpy(responsible_person, config->responsible_person, MAX_FIELD_LEN - 1);

    if (show_info_editor(config, location, MAX_FIELD_LEN,
                         department, MAX_FIELD_LEN,
                         responsible_person, MAX_FIELD_LEN)) {
        strncpy(config->location, location, MAX_FIELD_LEN - 1);
        strncpy(config->department, department, MAX_FIELD_LEN - 1);
        strncpy(config->responsible_person, responsible_person, MAX_FIELD_LEN - 1);
        SaveConfig(config);
        printf("配置已更新\n");
    }

    FreeConfig(config);
    return 0;
}

/* ================================================================
 *  配置窗口（兜底方案）- KNOWN_LIMIT
 *
 *  已知限制：当前版本未实现Win32对话框，始终返回0（表示用户取消）。
 *  用户需通过配置文件或CLI参数设置服务器URL。
 * ================================================================ */
int showSetupWindow(char *server_url, size_t url_bufsize,
                    char *api_key, size_t key_bufsize) {
    /* KNOWN_LIMIT: 未实现Win32对话框，当前版本返回0表示用户取消 */
    /* 窗口内容：服务器地址输入框、API Key输入框、确认按钮 */
    return 0;
}

/* ================================================================
 *  信息编辑窗口 - KNOWN_LIMIT
 *
 *  已知限制：当前版本未实现Win32信息编辑对话框，始终返回0（表示用户取消）。
 *  用户需通过管理端Web界面编辑设备信息。
 * ================================================================ */
int show_info_editor(const AgentConfig *current,
                     char *location, size_t loc_bufsize,
                     char *department, size_t dept_bufsize,
                     char *responsible_person, size_t resp_bufsize) {
    /* KNOWN_LIMIT: 未实现Win32信息编辑对话框，当前版本返回0表示用户取消 */
    return 0;
}

/* ================================================================
 *  心跳响应处理
 * ================================================================ */
static void handle_heartbeat_response(Agent *a, const char *resp_json) {
    if (!resp_json || !resp_json[0]) return;

    cJSON *root = cJSON_Parse(resp_json);
    if (!root) return;

    cJSON *data = cJSON_GetObjectItem(root, "data");
    if (!data) { cJSON_Delete(root); return; }

    /* 处理 config_update */
    cJSON *config_update = cJSON_GetObjectItem(data, "config_update");
    if (config_update) {
        cJSON *new_url = cJSON_GetObjectItem(config_update, "server_url");
        cJSON *new_interval = cJSON_GetObjectItem(config_update, "heartbeat_interval");

        if (new_url && new_url->valuestring[0]) {
            log_write("收到服务器迁移通知: %s -> %s",
                      EffectiveServerURL(a->config), new_url->valuestring);

            char old_url[MAX_URL_LEN];
            strncpy(old_url, EffectiveServerURL(a->config), MAX_URL_LEN - 1);

            ApplyServerUpdate(a->config, new_url->valuestring,
                              new_interval ? new_interval->valueint : 0);

            /* 立即尝试用新URL发送心跳验证可达性 */
            int test_result = reporter_test_heartbeat(a->reporter, new_url->valuestring);
            if (test_result < 0) {
                /* 连接失败，服务器不可达 */
                log_write("新服务器连接失败(结果=%d)，回退到旧地址", test_result);
                strncpy(a->config->server_url_override, old_url, MAX_URL_LEN - 1);
                SaveConfig(a->config);
                a->migration_fail_count++;
            } else {
                log_write("新服务器可达(结果=%d)，迁移完成", test_result);
                a->migration_confirmed = 1;
                a->migration_fail_count = 0;
            }
        } else if (new_interval && new_interval->valueint >= 30 && new_interval->valueint <= 600) {
            a->config->heartbeat_interval = new_interval->valueint;
            SaveConfig(a->config);
        }
    }

    /* 处理 commands */
    cJSON *commands = cJSON_GetObjectItem(data, "commands");
    if (commands && cJSON_IsArray(commands)) {
        int cmd_count = cJSON_GetArraySize(commands);
        for (int i = 0; i < cmd_count; i++) {
            cJSON *cmd = cJSON_GetArrayItem(commands, i);
            const char *cmd_name_str = NULL;
            cJSON *interval_val = NULL;

            if (cJSON_IsString(cmd)) {
                /* 字符串格式: "report_now" / "stop" */
                cmd_name_str = cmd->valuestring;
            } else if (cJSON_IsObject(cmd)) {
                /* 对象格式: {"command": "report_now"} / {"command": "update_interval", "interval": 120} */
                cJSON *cmd_name = cJSON_GetObjectItem(cmd, "command");
                if (cmd_name && cmd_name->valuestring[0])
                    cmd_name_str = cmd_name->valuestring;
                interval_val = cJSON_GetObjectItem(cmd, "interval");
            }

            if (cmd_name_str) {
                if (strcmp(cmd_name_str, "report_now") == 0) {
                    log_write("收到远程指令: report_now");
                    SystemInfo *info = collector_collect();
                    if (info) {
                        reporter_report(a->reporter, info);
                        collector_free(info);
                    }
                } else if (strcmp(cmd_name_str, "stop") == 0) {
                    log_write("收到远程指令: stop");
                    a->running = 0;
                } else if (strcmp(cmd_name_str, "update_interval") == 0) {
                    if (interval_val && interval_val->valueint >= 30 && interval_val->valueint <= 600) {
                        a->config->heartbeat_interval = interval_val->valueint;
                        SaveConfig(a->config);
                        log_write("心跳间隔已更新为 %d 秒", interval_val->valueint);
                    }
                } else if (strcmp(cmd_name_str, "restart") == 0) {
                    log_write("收到远程指令: restart，准备重启服务");
                    /* 保存配置 */
                    SaveConfig(a->config);
                    /* 重启前上报一次 */
                    {
                        SystemInfo *info = collector_collect();
                        if (info) {
                            reporter_report(a->reporter, info);
                            collector_free(info);
                        }
                    }
                    /* 使用CreateProcess重新启动自身 */
                    {
                        char exe_path[MAX_PATH];
                        GetModuleFileNameA(NULL, exe_path, MAX_PATH);
                        STARTUPINFOA si = { sizeof(STARTUPINFOA) };
                        PROCESS_INFORMATION pi;
                        if (CreateProcessA(exe_path, NULL, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
                            CloseHandle(pi.hProcess);
                            CloseHandle(pi.hThread);
                            log_write("重启进程已创建，当前进程即将退出");
                        } else {
                            log_write("创建重启进程失败，错误码: %lu", GetLastError());
                        }
                    }
                    /* 退出当前进程 */
                    exit(0);
                }
            }
        }
    }

    /* 处理 sync_fields：服务端→客户端同步三字段 */
    cJSON *sync_fields = cJSON_GetObjectItem(data, "sync_fields");
    if (sync_fields && cJSON_IsObject(sync_fields)) {
        int changed = 0;
        cJSON *sf_item;

        sf_item = cJSON_GetObjectItem(sync_fields, "location");
        if (sf_item && cJSON_IsString(sf_item) && sf_item->valuestring[0]) {
            if (strcmp(a->config->location, sf_item->valuestring) != 0) {
                strncpy(a->config->location, sf_item->valuestring, MAX_FIELD_LEN - 1);
                a->config->location[MAX_FIELD_LEN - 1] = '\0';
                changed = 1;
            }
        }

        sf_item = cJSON_GetObjectItem(sync_fields, "department");
        if (sf_item && cJSON_IsString(sf_item) && sf_item->valuestring[0]) {
            if (strcmp(a->config->department, sf_item->valuestring) != 0) {
                strncpy(a->config->department, sf_item->valuestring, MAX_FIELD_LEN - 1);
                a->config->department[MAX_FIELD_LEN - 1] = '\0';
                changed = 1;
            }
        }

        sf_item = cJSON_GetObjectItem(sync_fields, "responsible_person");
        if (sf_item && cJSON_IsString(sf_item) && sf_item->valuestring[0]) {
            if (strcmp(a->config->responsible_person, sf_item->valuestring) != 0) {
                strncpy(a->config->responsible_person, sf_item->valuestring, MAX_FIELD_LEN - 1);
                a->config->responsible_person[MAX_FIELD_LEN - 1] = '\0';
                changed = 1;
            }
        }

        if (changed) {
            SaveConfig(a->config);
            log_write("sync_fields: 已同步服务端字段到本地配置");
        }
    }

    cJSON_Delete(root);
}

/* 迁移失败回退检查 */
static void check_migration_fallback(Agent *a) {
    if (a->migration_fail_count >= MIGRATION_MAX_RETRIES) {
        log_write("新服务器连续%d次心跳失败，自动回退到旧服务器地址",
                  MIGRATION_MAX_RETRIES);
        a->config->server_url_override[0] = '\0';
        SaveConfig(a->config);
        a->migration_fail_count = 0;
        a->migration_confirmed = 0;
    }
}

/* ================================================================
 *  Agent 生命周期
 * ================================================================ */
Agent* agent_create(AgentConfig *config) {
    Agent *a = (Agent*)calloc(1, sizeof(Agent));
    if (!a) return NULL;
    a->config = config;
    a->reporter = reporter_create(config);
    a->last_info = collector_collect();
    a->running = 1;
    return a;
}

void agent_run(Agent *a) {
    /* 初始化重新注册计数器 */
    a->reregister_count = 0;

    /* 启动IPC服务端 */
    start_ipc_server(a);

    /* 首次注册 */
    SystemInfo *info = collector_collect();
    if (info) {
        /* 填充配置中的手动字段到SystemInfo */
        strncpy(info->device_fingerprint, a->config->device_fingerprint, MAX_FP_LEN - 1);
        strncpy(info->asset_number, a->config->asset_number, MAX_FIELD_LEN - 1);
        strncpy(info->location, a->config->location, MAX_FIELD_LEN - 1);
        strncpy(info->department, a->config->department, MAX_FIELD_LEN - 1);
        strncpy(info->responsible_person, a->config->responsible_person, MAX_FIELD_LEN - 1);

        RegisterResult reg_result = {0};
        if (reporter_register(a->reporter, info, &reg_result) != 0) {
            log_write("注册失败");
        } else {
            log_write("注册成功");
            /* 保存服务端返回的uuid、agent_id、heartbeat_interval到配置 */
            int config_changed = 0;
            if (reg_result.uuid[0]) {
                strncpy(a->config->uuid, reg_result.uuid, MAX_UUID_LEN - 1);
                strncpy(a->reporter->uuid, reg_result.uuid, MAX_UUID_LEN - 1);
                config_changed = 1;
                log_write("收到服务端UUID: %s", reg_result.uuid);
            }
            if (reg_result.server_agent_id[0]) {
                strncpy(a->config->server_agent_id, reg_result.server_agent_id, MAX_SERVER_ID_LEN - 1);
                strncpy(a->reporter->server_agent_id, reg_result.server_agent_id, MAX_SERVER_ID_LEN - 1);
                config_changed = 1;
                log_write("收到服务端agent_id: %s", reg_result.server_agent_id);
            }
            if (reg_result.heartbeat_interval >= 30 && reg_result.heartbeat_interval <= 600) {
                a->config->heartbeat_interval = reg_result.heartbeat_interval;
                config_changed = 1;
                log_write("收到服务端心跳间隔: %d秒", reg_result.heartbeat_interval);
            } else if (reg_result.heartbeat_interval > 0) {
                log_write("服务端心跳间隔%d秒超出范围(30-600)，忽略", reg_result.heartbeat_interval);
            }
            if (reg_result.server_url[0]) {
                strncpy(a->config->server_url_override, reg_result.server_url, MAX_URL_LEN - 1);
                config_changed = 1;
                log_write("收到服务端URL覆盖: %s", reg_result.server_url);
            }
            if (config_changed) {
                SaveConfig(a->config);
            }
        }
        collector_free(info);
    }

    /* 心跳主循环 */
    while (a->running) {
        int interval = a->config->heartbeat_interval;
        if (a->offline_mode)
            interval = 300; /* 离线模式：5分钟一次 */

        /* 分段Sleep，便于响应IPC停止命令 */
        for (int i = 0; i < interval && a->running; i++) {
            Sleep(1000);
        }
        if (!a->running) break;

        a->heartbeat_counter++;

        /* 检测设备信息变更 */
        SystemInfo *current_info = collector_collect();
        if (!current_info) continue;

        /* 填充配置字段 */
        strncpy(current_info->device_fingerprint, a->config->device_fingerprint, MAX_FP_LEN - 1);
        strncpy(current_info->asset_number, a->config->asset_number, MAX_FIELD_LEN - 1);
        strncpy(current_info->location, a->config->location, MAX_FIELD_LEN - 1);
        strncpy(current_info->department, a->config->department, MAX_FIELD_LEN - 1);
        strncpy(current_info->responsible_person, a->config->responsible_person, MAX_FIELD_LEN - 1);

        /* 信息变更检测（使用info_hash比较） */
        compute_info_hash(current_info, a->info_hash, sizeof(a->info_hash));
        int info_changed = 0;
        if (a->last_info) {
            char last_hash[MAX_FP_LEN] = {0};
            compute_info_hash(a->last_info, last_hash, sizeof(last_hash));
            info_changed = (strcmp(a->info_hash, last_hash) != 0);
        }

        /* 发送心跳 */
        char heartbeat_resp[4096] = {0};
        int err;
        if (info_changed || a->heartbeat_counter % 30 == 0) {
            err = reporter_heartbeat_with_info(a->reporter, current_info, a->migration_confirmed, heartbeat_resp, sizeof(heartbeat_resp));
        } else {
            err = reporter_heartbeat(a->reporter, a->info_hash, a->migration_confirmed, heartbeat_resp, sizeof(heartbeat_resp));
        }

        if (err != 0) {
            a->consecutive_failures++;

            /* 处理401 uuid_mismatch：清除UUID并触发重新注册 */
            if (err == 401 && a->reregister_count < 3) {
                a->reregister_count++;
                log_write("收到401响应(UUID不匹配)，清除本地UUID并重新注册(第%d次)", a->reregister_count);

                /* 清除本地UUID */
                memset(a->config->uuid, 0, MAX_UUID_LEN);
                memset(a->reporter->uuid, 0, MAX_UUID_LEN);
                SaveConfig(a->config);

                /* 触发重新注册 */
                SystemInfo *reg_info = collector_collect();
                if (reg_info) {
                    /* 填充配置字段 */
                    strncpy(reg_info->device_fingerprint, a->config->device_fingerprint, MAX_FP_LEN - 1);
                    strncpy(reg_info->asset_number, a->config->asset_number, MAX_FIELD_LEN - 1);
                    strncpy(reg_info->location, a->config->location, MAX_FIELD_LEN - 1);
                    strncpy(reg_info->department, a->config->department, MAX_FIELD_LEN - 1);
                    strncpy(reg_info->responsible_person, a->config->responsible_person, MAX_FIELD_LEN - 1);

                    RegisterResult reg_result = {0};
                    if (reporter_register(a->reporter, reg_info, &reg_result) != 0) {
                        log_write("401触发重新注册失败");
                    } else {
                        log_write("401触发重新注册成功");
                        int config_changed = 0;
                        if (reg_result.uuid[0]) {
                            strncpy(a->config->uuid, reg_result.uuid, MAX_UUID_LEN - 1);
                            strncpy(a->reporter->uuid, reg_result.uuid, MAX_UUID_LEN - 1);
                            config_changed = 1;
                            log_write("收到新UUID: %s", reg_result.uuid);
                        }
                        if (reg_result.server_agent_id[0]) {
                            strncpy(a->config->server_agent_id, reg_result.server_agent_id, MAX_SERVER_ID_LEN - 1);
                            strncpy(a->reporter->server_agent_id, reg_result.server_agent_id, MAX_SERVER_ID_LEN - 1);
                            config_changed = 1;
                            log_write("收到新agent_id: %s", reg_result.server_agent_id);
                        }
                        if (reg_result.heartbeat_interval >= 30 && reg_result.heartbeat_interval <= 600) {
                            a->config->heartbeat_interval = reg_result.heartbeat_interval;
                            config_changed = 1;
                            log_write("收到服务端心跳间隔: %d秒", reg_result.heartbeat_interval);
                        } else if (reg_result.heartbeat_interval > 0) {
                            log_write("服务端心跳间隔%d秒超出范围(30-600)，忽略", reg_result.heartbeat_interval);
                        }
                        if (reg_result.server_url[0]) {
                            strncpy(a->config->server_url_override, reg_result.server_url, MAX_URL_LEN - 1);
                            config_changed = 1;
                            log_write("收到服务端URL覆盖: %s", reg_result.server_url);
                        }
                        if (config_changed) {
                            SaveConfig(a->config);
                        }
                        a->reregister_count = 0;  /* 重置计数器 */
                    }
                    collector_free(reg_info);
                }
                if (a->last_info) collector_free(a->last_info);
                a->last_info = current_info;
                continue;  /* 跳过本次心跳后续处理 */
            }

            if (a->consecutive_failures >= 5)
                a->offline_mode = 1;
            log_write("心跳失败(%d次连续)", a->consecutive_failures);
        } else {
            if (a->consecutive_failures > 0)
                log_write("心跳恢复");
            a->consecutive_failures = 0;
            a->offline_mode = 0;
            /* 处理心跳响应（配置更新、远程指令等） */
            handle_heartbeat_response(a, heartbeat_resp);
        }

        /* 迁移回退检查 */
        check_migration_fallback(a);

        if (a->last_info) collector_free(a->last_info);
        a->last_info = current_info;
    }

    /* 退出前发送离线通知 */
    reporter_offline(a->reporter);
    log_write("Agent 已停止");
}

void agent_destroy(Agent *a) {
    if (!a) return;
    if (a->last_info) collector_free(a->last_info);
    if (a->reporter) reporter_destroy(a->reporter);
    free(a);
}