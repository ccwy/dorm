/* config.c - 配置管理实现 */
#include "config.h"
#include "fingerprint.h"
#include <windows.h>
#include <shlobj.h>
#include <aclapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* generate_agent_id: 生成 "ag_" + 16位hex字符串 */
static void generate_agent_id(char *buf, size_t bufsize) {
    HCRYPTPROV hProv;
    BYTE bytes[8];
    if (CryptAcquireContext(&hProv, NULL, NULL, PROV_RSA_FULL,
                            CRYPT_VERIFYCONTEXT | CRYPT_SILENT)) {
        CryptGenRandom(hProv, 8, bytes);
        CryptReleaseContext(hProv, 0);
    } else {
        /* 回退：使用 GetTickCount + QueryPerformanceCounter */
        DWORD seed = GetTickCount();
        LARGE_INTEGER perf;
        QueryPerformanceCounter(&perf);
        seed ^= (DWORD)(perf.QuadPart & 0xFFFFFFFF);
        for (int i = 0; i < 8; i++)
            bytes[i] = (BYTE)((seed >> (i % 4 * 8)) ^ i);
    }
    snprintf(buf, bufsize, "ag_%02x%02x%02x%02x%02x%02x%02x%02x",
             bytes[0], bytes[1], bytes[2], bytes[3],
             bytes[4], bytes[5], bytes[6], bytes[7]);
}

/* local_config_path: 获取exe同目录下的config.json路径 */
static int local_config_path(char *buf, size_t bufsize) {
    if (!GetModuleFileNameA(NULL, buf, (DWORD)bufsize)) return 0;
    char *last_sep = strrchr(buf, '\\');
    if (!last_sep) return 0;
    if (strlen(last_sep + 1) + strlen("\\config.json") + 1 > bufsize) return 0;
    snprintf(last_sep + 1, bufsize - (last_sep + 1 - buf), "config.json");
    DWORD attr = GetFileAttributesA(buf);
    return (attr != INVALID_FILE_ATTRIBUTES &&
            !(attr & FILE_ATTRIBUTE_DIRECTORY));
}

/* parse_config_from_json: 从cJSON对象解析配置 */
/* safe_strncpy: strncpy with guaranteed null-termination */
static void safe_strncpy(char *dst, const char *src, size_t bufsize) {
    snprintf(dst, bufsize, "%s", src);
}

static void parse_config_from_json(cJSON *json, AgentConfig *config) {
    cJSON *item;
    if ((item = cJSON_GetObjectItem(json, "server_url")))
        safe_strncpy(config->server_url, item->valuestring, MAX_URL_LEN);
    if ((item = cJSON_GetObjectItem(json, "api_key")))
        safe_strncpy(config->api_key, item->valuestring, MAX_KEY_LEN);
    if ((item = cJSON_GetObjectItem(json, "heartbeat_interval")))
        config->heartbeat_interval = item->valueint;
    if ((item = cJSON_GetObjectItem(json, "asset_number")))
        safe_strncpy(config->asset_number, item->valuestring, MAX_FIELD_LEN);
    if ((item = cJSON_GetObjectItem(json, "device_fingerprint")))
        safe_strncpy(config->device_fingerprint, item->valuestring, MAX_FP_LEN);
    if ((item = cJSON_GetObjectItem(json, "uuid")))
        safe_strncpy(config->uuid, item->valuestring, MAX_UUID_LEN);
    if ((item = cJSON_GetObjectItem(json, "agent_id")))
        safe_strncpy(config->agent_id, item->valuestring, MAX_ID_LEN);
    if ((item = cJSON_GetObjectItem(json, "server_agent_id")))
        safe_strncpy(config->server_agent_id, item->valuestring, MAX_SERVER_ID_LEN);
    if ((item = cJSON_GetObjectItem(json, "server_url_override")))
        safe_strncpy(config->server_url_override, item->valuestring, MAX_URL_LEN);
    if ((item = cJSON_GetObjectItem(json, "location")))
        safe_strncpy(config->location, item->valuestring, MAX_FIELD_LEN);
    if ((item = cJSON_GetObjectItem(json, "department")))
        safe_strncpy(config->department, item->valuestring, MAX_FIELD_LEN);
    if ((item = cJSON_GetObjectItem(json, "responsible_person")))
        safe_strncpy(config->responsible_person, item->valuestring, MAX_FIELD_LEN);
    if ((item = cJSON_GetObjectItem(json, "allow_remote_stop")))
        config->allow_remote_stop = item->valueint ? 1 : 0;
}

/* read_json_file: 读取文件并解析为cJSON对象 */
static cJSON* read_json_file(const char *path) {
    FILE *fp = fopen(path, "rb");
    if (!fp) return NULL;
    fseek(fp, 0, SEEK_END);
    long fsize = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    char *data = (char*)malloc(fsize + 1);
    if (!data) { fclose(fp); return NULL; }
    fread(data, 1, fsize, fp);
    data[fsize] = '\0';
    fclose(fp);
    cJSON *json = cJSON_Parse(data);
    free(data);
    return json;
}

/* ensure_device_fingerprint: 确保设备指纹已生成 */
static void ensure_device_fingerprint(AgentConfig *config) {
    if (config->device_fingerprint[0] != '\0') return;
    fingerprint_generate(config->device_fingerprint, MAX_FP_LEN);
}

/* LoadConfig: 加载配置，优先级为 服务端下发 > 同目录config.json > ProgramData/config.json > 首次配置窗口 */
AgentConfig* LoadConfig(void) {
    AgentConfig *config = (AgentConfig*)calloc(1, sizeof(AgentConfig));
    if (!config) return NULL;
    config->heartbeat_interval = 10;

    /* 1. 尝试从exe同目录读取 config.json（下载时注入的配置） */
    char local_path[MAX_PATH];
    if (local_config_path(local_path, MAX_PATH)) {
        cJSON *json = read_json_file(local_path);
        if (json) {
            parse_config_from_json(json, config);
            cJSON_Delete(json);
            if (config->agent_id[0] == '\0')
                generate_agent_id(config->agent_id, MAX_ID_LEN);
            ensure_device_fingerprint(config);
            /* 确保ProgramData目录也有配置（用于自启动后的配置查找） */
            CreateDirectoryA(PROGRAM_DATA_DIR, NULL);
            SaveConfigTo(config, PROGRAM_DATA_CFG);
            return config;
        }
    }

    /* 2. 尝试从 ProgramData 读取（自启动后exe路径可能不同） */
    cJSON *json = read_json_file(PROGRAM_DATA_CFG);
    if (json) {
        parse_config_from_json(json, config);
        cJSON_Delete(json);
        if (config->agent_id[0] == '\0') {
            generate_agent_id(config->agent_id, MAX_ID_LEN);
            SaveConfig(config);
        }
        ensure_device_fingerprint(config);
        SaveConfig(config);
        return config;
    }

    /* 3. 无任何配置文件，返回空配置（将触发配置窗口） */
    generate_agent_id(config->agent_id, MAX_ID_LEN);
    ensure_device_fingerprint(config);
    return config;
}

/* EffectiveServerURL: 获取当前生效的服务器URL */
const char* EffectiveServerURL(const AgentConfig *config) {
    return (config->server_url_override[0] != '\0')
           ? config->server_url_override : config->server_url;
}

/* ApplyServerUpdate: 应用服务端下发的配置更新 */
void ApplyServerUpdate(AgentConfig *config, const char *new_url, int new_interval) {
    log_write("收到服务端配置更新: server_url=%s", new_url);
    safe_strncpy(config->server_url_override, new_url, MAX_URL_LEN);
    if (new_interval >= 10 && new_interval <= 600)
        config->heartbeat_interval = new_interval;
    SaveConfig(config);
}

/* build_config_json: 将配置序列化为cJSON对象 */
static cJSON* build_config_json(const AgentConfig *config) {
    cJSON *root = cJSON_CreateObject();
    if (config->server_url[0])
        cJSON_AddStringToObject(root, "server_url", config->server_url);
    if (config->api_key[0])
        cJSON_AddStringToObject(root, "api_key", config->api_key);
    cJSON_AddNumberToObject(root, "heartbeat_interval", config->heartbeat_interval);
    if (config->asset_number[0])
        cJSON_AddStringToObject(root, "asset_number", config->asset_number);
    if (config->device_fingerprint[0])
        cJSON_AddStringToObject(root, "device_fingerprint", config->device_fingerprint);
    if (config->uuid[0])
        cJSON_AddStringToObject(root, "uuid", config->uuid);
    if (config->agent_id[0])
        cJSON_AddStringToObject(root, "agent_id", config->agent_id);
    if (config->server_agent_id[0])
        cJSON_AddStringToObject(root, "server_agent_id", config->server_agent_id);
    if (config->server_url_override[0])
        cJSON_AddStringToObject(root, "server_url_override", config->server_url_override);
    if (config->location[0])
        cJSON_AddStringToObject(root, "location", config->location);
    if (config->department[0])
        cJSON_AddStringToObject(root, "department", config->department);
    if (config->responsible_person[0])
        cJSON_AddStringToObject(root, "responsible_person", config->responsible_person);
    cJSON_AddBoolToObject(root, "allow_remote_stop", config->allow_remote_stop ? 1 : 0);
    return root;
}

/* SaveConfig: 保存到ProgramData默认路径 */
int SaveConfig(const AgentConfig *config) {
    CreateDirectoryA(PROGRAM_DATA_DIR, NULL);
    return SaveConfigTo(config, PROGRAM_DATA_CFG);
}

/* SaveConfigTo: 保存到指定路径 */
int SaveConfigTo(const AgentConfig *config, const char *path) {
    cJSON *root = build_config_json(config);
    if (!root) return -1;
    char *data = cJSON_Print(root);
    cJSON_Delete(root);
    if (!data) return -1;
    WCHAR wpath[MAX_PATH] = {0};
    MultiByteToWideChar(CP_ACP, 0, path, -1, wpath, MAX_PATH);
    FILE *fp = fopen(path, "w");
    if (!fp) { free(data); return -1; }
    fputs(data, fp);
    fclose(fp);
#ifdef _WIN32
    /* 设置文件权限：仅当前用户可读写（文档§9.4要求） */
    PSID pCurrentUserSID = NULL;
    HANDLE hToken = NULL;
    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &hToken)) {
        DWORD dwNeeded = 0;
        GetTokenInformation(hToken, TokenUser, NULL, 0, &dwNeeded);
        if (GetLastError() == ERROR_INSUFFICIENT_BUFFER) {
            PTOKEN_USER pTokenUser = (PTOKEN_USER)malloc(dwNeeded);
            if (pTokenUser && GetTokenInformation(hToken, TokenUser, pTokenUser, dwNeeded, &dwNeeded)) {
                pCurrentUserSID = pTokenUser->User.Sid;
                EXPLICIT_ACCESSW ea = {0};
                ea.grfAccessPermissions = FILE_GENERIC_READ | FILE_GENERIC_WRITE;
                ea.grfAccessMode = SET_ACCESS;
                ea.grfInheritance = NO_INHERITANCE;
                ea.Trustee.TrusteeForm = TRUSTEE_IS_SID;
                ea.Trustee.TrusteeType = TRUSTEE_IS_USER;
                ea.Trustee.ptstrName = (LPWSTR)pCurrentUserSID;
                PACL pNewACL = NULL;
                if (SetEntriesInAclW(1, &ea, NULL, &pNewACL) == ERROR_SUCCESS) {
                    SetNamedSecurityInfoW(wpath, SE_FILE_OBJECT,
                        DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                        NULL, NULL, pNewACL, NULL);
                    LocalFree(pNewACL);
                }
            }
            if (pTokenUser) free(pTokenUser);
        }
        CloseHandle(hToken);
    }
#endif
    free(data);
    return 0;
}

/* FreeConfig: 释放配置内存 */
void FreeConfig(AgentConfig *config) {
    free(config);
}