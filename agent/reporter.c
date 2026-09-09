/* reporter.c - HTTP通信实现（WinINet） */
#include "reporter.h"
#include "cJSON.h"
#include <wininet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- SSL证书验证相关常量（兼容旧版SDK） ---- */
#ifndef INTERNET_OPTION_SECURITY_FLAGS
#define INTERNET_OPTION_SECURITY_FLAGS 31
#endif
#ifndef SECURITY_FLAG_UNKNOWNCA
#define SECURITY_FLAG_UNKNOWNCA       0x0100
#endif
#ifndef SECURITY_FLAG_CERT_REV_FAILED
#define SECURITY_FLAG_CERT_REV_FAILED 0x0080
#endif
#ifndef SECURITY_FLAG_INVALID_CA
#define SECURITY_FLAG_INVALID_CA      0x0200
#endif
#ifndef SECURITY_FLAG_CERT_WRONG_USAGE
#define SECURITY_FLAG_CERT_WRONG_USAGE 0x0400
#endif
#ifndef SECURITY_FLAG_CERT_CN_INVALID
#define SECURITY_FLAG_CERT_CN_INVALID 0x0800
#endif
#ifndef SECURITY_FLAG_CERT_DATE_INVALID
#define SECURITY_FLAG_CERT_DATE_INVALID 0x1000
#endif

/* ---- URL解析 ---- */
typedef struct {
    char scheme[8];     /* "http" or "https" */
    char host[128];
    int  port;
    char path[256];
} ParsedUrl;

static int parse_url(const char *url, ParsedUrl *pu) {
    memset(pu, 0, sizeof(ParsedUrl));
    const char *p = url;
    const char *scheme_end = strstr(p, "://");
    if (!scheme_end) return -1;
    size_t scheme_len = scheme_end - p;
    if (scheme_len >= sizeof(pu->scheme)) return -1;
    memcpy(pu->scheme, p, scheme_len);
    pu->scheme[scheme_len] = '\0';
    p = scheme_end + 3;

    /* 解析host:port */
    const char *slash = strchr(p, '/');
    const char *colon = strchr(p, ':');
    if (colon && (!slash || colon < slash)) {
        size_t host_len = colon - p;
        if (host_len >= sizeof(pu->host)) return -1;
        memcpy(pu->host, p, host_len);
        pu->host[host_len] = '\0';
        pu->port = atoi(colon + 1);
    } else {
        size_t host_len = slash ? (size_t)(slash - p) : strlen(p);
        if (host_len >= sizeof(pu->host)) return -1;
        memcpy(pu->host, p, host_len);
        pu->host[host_len] = '\0';
        pu->port = (strcmp(pu->scheme, "https") == 0) ? 443 : 80;
    }

    /* 解析path */
    if (slash)
        strncpy(pu->path, slash, sizeof(pu->path) - 1);
    else
        strncpy(pu->path, "/", sizeof(pu->path) - 1);
    return 0;
}

/* ---- HTTP POST 辅助函数 ---- */
static int http_post(const char *url, const char *api_key,
                     const char *path, const char *json_body,
                     char *resp_buf, size_t resp_bufsize) {
    ParsedUrl pu;
    if (parse_url(url, &pu) != 0) {
        log_write("URL解析失败: %s", url);
        return -1;
    }

    HINTERNET hSession = InternetOpenA("AssetAgent/1.0",
        INTERNET_OPEN_TYPE_PRECONFIG, NULL, NULL, 0);
    if (!hSession) {
        log_write("InternetOpen失败: %lu", GetLastError());
        return -1;
    }

    HINTERNET hConnect = InternetConnectA(hSession, pu.host,
        (INTERNET_PORT)pu.port, NULL, NULL, INTERNET_SERVICE_HTTP, 0, 0);
    if (!hConnect) {
        log_write("InternetConnect失败: %lu", GetLastError());
        InternetCloseHandle(hSession);
        return -1;
    }

    DWORD flags = 0;
    if (strcmp(pu.scheme, "https") == 0)
        flags |= INTERNET_FLAG_SECURE;

    HINTERNET hRequest = HttpOpenRequestA(hConnect, "POST", path,
        NULL, NULL, NULL, flags, 0);
    if (!hRequest) {
        log_write("HttpOpenRequest失败: %lu", GetLastError());
        InternetCloseHandle(hConnect);
        InternetCloseHandle(hSession);
        return -1;
    }

    /* 设置请求头 */
    char headers[512];
    snprintf(headers, sizeof(headers),
        "Content-Type: application/json\r\n"
        "X-Agent-API-Key: %s\r\n",
        api_key);

    /* 发送请求 */
    BOOL ok = HttpSendRequestA(hRequest, headers, (DWORD)strlen(headers),
        (LPVOID)json_body, (DWORD)strlen(json_body));
    if (!ok) {
        log_write("HttpSendRequest失败: %lu", GetLastError());
        InternetCloseHandle(hRequest);
        InternetCloseHandle(hConnect);
        InternetCloseHandle(hSession);
        return -1;
    }

    /* 检查HTTPS证书验证结果 */
    if (strcmp(pu.scheme, "https") == 0) {
        DWORD cert_flags = 0;
        DWORD buf_len = sizeof(cert_flags);
        if (InternetQueryOptionA(hRequest, INTERNET_OPTION_SECURITY_FLAGS,
                                 &cert_flags, &buf_len)) {
            DWORD cert_errors = cert_flags & (SECURITY_FLAG_UNKNOWNCA |
                                              SECURITY_FLAG_CERT_REV_FAILED |
                                              SECURITY_FLAG_INVALID_CA |
                                              SECURITY_FLAG_CERT_WRONG_USAGE |
                                              SECURITY_FLAG_CERT_CN_INVALID |
                                              SECURITY_FLAG_CERT_DATE_INVALID);
            if (cert_errors) {
                log_write("HTTPS证书验证失败: flags=0x%lx (UNKNOWN_CA=%s REV_FAILED=%s INVALID_CA=%s WRONG_USAGE=%s CN_INVALID=%s DATE_INVALID=%s)",
                    cert_flags,
                    (cert_errors & SECURITY_FLAG_UNKNOWNCA)       ? "Y" : "N",
                    (cert_errors & SECURITY_FLAG_CERT_REV_FAILED) ? "Y" : "N",
                    (cert_errors & SECURITY_FLAG_INVALID_CA)      ? "Y" : "N",
                    (cert_errors & SECURITY_FLAG_CERT_WRONG_USAGE)? "Y" : "N",
                    (cert_errors & SECURITY_FLAG_CERT_CN_INVALID) ? "Y" : "N",
                    (cert_errors & SECURITY_FLAG_CERT_DATE_INVALID)? "Y" : "N");
                InternetCloseHandle(hRequest);
                InternetCloseHandle(hConnect);
                InternetCloseHandle(hSession);
                return -1;
            }
        }
    }

    /* 读取响应 */
    DWORD status_code = 0;
    DWORD status_len = sizeof(status_code);
    HttpQueryInfoA(hRequest, HTTP_QUERY_STATUS_CODE | HTTP_QUERY_FLAG_NUMBER,
                   &status_code, &status_len, NULL);

    if (resp_buf && resp_bufsize > 0) {
        DWORD total_read = 0;
        DWORD bytes_avail = 0;
        while (InternetQueryDataAvailable(hRequest, &bytes_avail, 0, 0) && bytes_avail > 0) {
            DWORD to_read = (bytes_avail < resp_bufsize - total_read - 1)
                            ? bytes_avail : (DWORD)(resp_bufsize - total_read - 1);
            if (to_read == 0) break;
            DWORD bytes_read = 0;
            InternetReadFile(hRequest, resp_buf + total_read, to_read, &bytes_read);
            total_read += bytes_read;
            if (bytes_read == 0) break;
        }
        resp_buf[total_read] = '\0';
    }

    InternetCloseHandle(hRequest);
    InternetCloseHandle(hConnect);
    InternetCloseHandle(hSession);

    return (status_code >= 200 && status_code < 300) ? 0 : (int)status_code;
}

/* ---- SystemInfo 转 JSON ---- */
static cJSON* system_info_to_json(const SystemInfo *info, const char *agent_id) {
    cJSON *root = cJSON_CreateObject();
    if (agent_id && agent_id[0])
        cJSON_AddStringToObject(root, "agent_id", agent_id);
    if (info->hostname[0])
        cJSON_AddStringToObject(root, "hostname", info->hostname);
    if (info->os_name[0])
        cJSON_AddStringToObject(root, "os_name", info->os_name);
    if (info->os_version[0])
        cJSON_AddStringToObject(root, "os_version", info->os_version);
    if (info->os_arch[0])
        cJSON_AddStringToObject(root, "os_arch", info->os_arch);
    if (info->cpu_model[0])
        cJSON_AddStringToObject(root, "cpu_model", info->cpu_model);
    cJSON_AddNumberToObject(root, "cpu_cores", info->cpu_cores);
    cJSON_AddNumberToObject(root, "total_memory_mb", info->total_memory_mb);
    cJSON_AddNumberToObject(root, "available_memory_mb", info->available_memory_mb);
    if (info->disks[0])
        cJSON_AddItemToObject(root, "disks", cJSON_Parse(info->disks));
    if (info->mac_address[0])
        cJSON_AddStringToObject(root, "mac_address", info->mac_address);
    if (info->ip_address[0])
        cJSON_AddStringToObject(root, "ip_address", info->ip_address);
    if (info->network_interfaces[0])
        cJSON_AddItemToObject(root, "network_interfaces", cJSON_Parse(info->network_interfaces));
    if (info->logged_in_user[0])
        cJSON_AddStringToObject(root, "logged_in_user", info->logged_in_user);
    if (info->agent_version[0])
        cJSON_AddStringToObject(root, "agent_version", info->agent_version);
    if (info->device_fingerprint[0])
        cJSON_AddStringToObject(root, "device_fingerprint", info->device_fingerprint);
    if (info->asset_number[0])
        cJSON_AddStringToObject(root, "asset_number", info->asset_number);
    if (info->location[0])
        cJSON_AddStringToObject(root, "location", info->location);
    if (info->department[0])
        cJSON_AddStringToObject(root, "department", info->department);
    if (info->responsible_person[0])
        cJSON_AddStringToObject(root, "responsible_person", info->responsible_person);
    return root;
}

/* ---- 获取当前时间戳字符串 ---- */
static void get_timestamp(char *buf, size_t bufsize) {
    SYSTEMTIME st;
    GetSystemTime(&st);
    snprintf(buf, bufsize, "%04d-%02d-%02dT%02d:%02d:%02dZ",
             st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
}

/* ---- 创建Reporter实例 ---- */
Reporter* reporter_create(const AgentConfig *config) {
    Reporter *r = (Reporter*)calloc(1, sizeof(Reporter));
    if (!r) return NULL;
    strncpy(r->server_url, EffectiveServerURL(config), MAX_URL_LEN - 1);
    strncpy(r->api_key, config->api_key, MAX_KEY_LEN - 1);
    strncpy(r->agent_id, config->agent_id, MAX_ID_LEN - 1);
    strncpy(r->uuid, config->uuid, MAX_UUID_LEN - 1);
    strncpy(r->server_agent_id, config->server_agent_id, MAX_SERVER_ID_LEN - 1);
    return r;
}

/* ---- 销毁Reporter实例 ---- */
void reporter_destroy(Reporter *r) {
    free(r);
}

/* ---- 注册：发送完整设备信息 ---- */
int reporter_register(Reporter *r, const SystemInfo *info, RegisterResult *result) {
    cJSON *root = system_info_to_json(info, r->agent_id);
    char timestamp[32];
    get_timestamp(timestamp, sizeof(timestamp));
    cJSON_AddStringToObject(root, "timestamp", timestamp);

    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!body) return -1;

    char resp[4096] = {0};
    int ret = http_post(r->server_url, r->api_key,
                        "/api/agent/register", body, resp, sizeof(resp));
    free(body);

    if (ret == 0) {
        log_write("注册成功");
        /* 解析响应中的uuid、agent_id、heartbeat_interval、server_url */
        cJSON *resp_json = cJSON_Parse(resp);
        if (resp_json) {
            cJSON *data = cJSON_GetObjectItem(resp_json, "data");
            if (data && result) {
                memset(result, 0, sizeof(RegisterResult));
                cJSON *uuid_item = cJSON_GetObjectItem(data, "uuid");
                if (uuid_item && uuid_item->valuestring && uuid_item->valuestring[0])
                    strncpy(result->uuid, uuid_item->valuestring, MAX_UUID_LEN - 1);
                cJSON *agent_id_item = cJSON_GetObjectItem(data, "agent_id");
                if (agent_id_item && agent_id_item->valuestring && agent_id_item->valuestring[0])
                    strncpy(result->server_agent_id, agent_id_item->valuestring, MAX_SERVER_ID_LEN - 1);
                cJSON *interval_item = cJSON_GetObjectItem(data, "heartbeat_interval");
                if (interval_item && interval_item->valueint > 0)
                    result->heartbeat_interval = interval_item->valueint;
                cJSON *url_item = cJSON_GetObjectItem(data, "server_url");
                if (url_item && url_item->valuestring && url_item->valuestring[0])
                    strncpy(result->server_url, url_item->valuestring, MAX_URL_LEN - 1);
            }
            cJSON_Delete(resp_json);
        }
    } else {
        log_write("注册失败: %d", ret);
    }
    return ret;
}

/* ---- 轻量心跳 ---- */
int reporter_heartbeat(Reporter *r, const char *info_hash, int migration_confirmed, char *resp_buf, size_t resp_bufsize) {
    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "agent_id", r->agent_id);
    if (r->uuid[0])
        cJSON_AddStringToObject(root, "uuid", r->uuid);
    char timestamp[32];
    get_timestamp(timestamp, sizeof(timestamp));
    cJSON_AddStringToObject(root, "timestamp", timestamp);
    /* 新增：添加info_hash字段（如果非空） */
    if (info_hash && info_hash[0]) {
        cJSON_AddStringToObject(root, "info_hash", info_hash);
    }
    /* 迁移确认标志 */
    if (migration_confirmed) {
        cJSON_AddBoolToObject(root, "migration_confirmed", 1);
    }

    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!body) return -1;

    char resp[4096] = {0};
    int ret = http_post(r->server_url, r->api_key,
                        "/api/agent/heartbeat", body, resp, sizeof(resp));
    free(body);
    /* 将响应复制到调用者提供的缓冲区 */
    if (ret == 0 && resp_buf && resp_bufsize > 0) {
        strncpy(resp_buf, resp, resp_bufsize - 1);
        resp_buf[resp_bufsize - 1] = '\0';
    }
    return ret;
}

/* ---- 带完整信息的心跳 ---- */
int reporter_heartbeat_with_info(Reporter *r, const SystemInfo *info, int migration_confirmed, char *resp_buf, size_t resp_bufsize) {
    cJSON *root = system_info_to_json(info, r->agent_id);
    if (r->uuid[0])
        cJSON_AddStringToObject(root, "uuid", r->uuid);
    char timestamp[32];
    get_timestamp(timestamp, sizeof(timestamp));
    cJSON_AddStringToObject(root, "timestamp", timestamp);
    /* 迁移确认标志 */
    if (migration_confirmed) {
        cJSON_AddBoolToObject(root, "migration_confirmed", 1);
    }

    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!body) return -1;

    char resp[4096] = {0};
    int ret = http_post(r->server_url, r->api_key,
                        "/api/agent/heartbeat", body, resp, sizeof(resp));
    free(body);
    /* 将响应复制到调用者提供的缓冲区 */
    if (ret == 0 && resp_buf && resp_bufsize > 0) {
        strncpy(resp_buf, resp, resp_bufsize - 1);
        resp_buf[resp_bufsize - 1] = '\0';
    }
    return ret;
}

/* ---- 完整信息上报 ---- */
int reporter_report(Reporter *r, const SystemInfo *info) {
    cJSON *root = system_info_to_json(info, r->agent_id);
    if (r->uuid[0])
        cJSON_AddStringToObject(root, "uuid", r->uuid);
    char timestamp[32];
    get_timestamp(timestamp, sizeof(timestamp));
    cJSON_AddStringToObject(root, "timestamp", timestamp);

    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!body) return -1;

    char resp[4096] = {0};
    int ret = http_post(r->server_url, r->api_key,
                        "/api/agent/report", body, resp, sizeof(resp));
    free(body);
    return ret;
}

/* ---- 离线通知 ---- */
int reporter_offline(Reporter *r) {
    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "agent_id", r->agent_id);
    if (r->uuid[0])
        cJSON_AddStringToObject(root, "uuid", r->uuid);
    char timestamp[32];
    get_timestamp(timestamp, sizeof(timestamp));
    cJSON_AddStringToObject(root, "timestamp", timestamp);

    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!body) return -1;

    char resp[4096] = {0};
    int ret = http_post(r->server_url, r->api_key,
                        "/api/agent/offline", body, resp, sizeof(resp));
    free(body);
    return ret;
}

/* ---- 测试指定URL的心跳可达性 ---- */
int reporter_test_heartbeat(Reporter *r, const char *url) {
    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "agent_id", r->agent_id);
    if (r->uuid[0])
        cJSON_AddStringToObject(root, "uuid", r->uuid);
    char timestamp[32];
    get_timestamp(timestamp, sizeof(timestamp));
    cJSON_AddStringToObject(root, "timestamp", timestamp);

    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!body) return -1;

    char resp[4096] = {0};
    int ret = http_post(url, r->api_key,
                        "/api/agent/heartbeat", body, resp, sizeof(resp));
    free(body);
    return ret;
}