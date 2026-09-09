/* reporter.h - HTTP通信接口声明 */
#ifndef REPORTER_H
#define REPORTER_H

#include "config.h"
#include "collector.h"

typedef struct {
    char server_url[MAX_URL_LEN];
    char api_key[MAX_KEY_LEN];
    char agent_id[MAX_ID_LEN];
    char uuid[MAX_UUID_LEN];           /* 服务端分配的UUID，心跳/上报时发送 */
    char server_agent_id[MAX_SERVER_ID_LEN]; /* 服务端分配的agent_id */
    void *hInternet;    /* HINTERNET WinINet会话句柄 */
} Reporter;

/* 创建Reporter实例 */
Reporter* reporter_create(const AgentConfig *config);

/* 销毁Reporter实例 */
void reporter_destroy(Reporter *r);

/* 注册：发送完整设备信息，成功时填充result */
int reporter_register(Reporter *r, const SystemInfo *info, RegisterResult *result);

/* 轻量心跳：发送agent_id + uuid + timestamp + info_hash，成功时resp_buf可接收响应 */
int reporter_heartbeat(Reporter *r, const char *info_hash, int migration_confirmed, char *resp_buf, size_t resp_bufsize);

/* 带完整信息的心跳，成功时resp_buf可接收响应 */
int reporter_heartbeat_with_info(Reporter *r, const SystemInfo *info, int migration_confirmed, char *resp_buf, size_t resp_bufsize);

/* 完整信息上报 */
int reporter_report(Reporter *r, const SystemInfo *info);

/* 离线通知 */
int reporter_offline(Reporter *r);

/* 测试指定URL的心跳可达性 */
int reporter_test_heartbeat(Reporter *r, const char *url);

#endif /* REPORTER_H */