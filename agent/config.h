/* config.h - 配置结构体与接口声明 */
#ifndef CONFIG_H
#define CONFIG_H

#include "cJSON.h"
#include <stdio.h>

#define MAX_URL_LEN      256
#define MAX_KEY_LEN      64
#define MAX_ID_LEN       32
#define MAX_FIELD_LEN    128
#define MAX_FP_LEN       65       /* SHA-256 hex = 64 chars + null */
#define MAX_UUID_LEN     37       /* UUID v4 = 36 chars + null */
#define MAX_SERVER_ID_LEN 64      /* 服务端分配ID缓冲区 */

#define PROGRAM_DATA_DIR   "C:\\ProgramData\\AssetAgent"
#define PROGRAM_DATA_CFG   "C:\\ProgramData\\AssetAgent\\config.json"

typedef struct {
    char server_url[MAX_URL_LEN];
    char api_key[MAX_KEY_LEN];
    int  heartbeat_interval;
    char asset_number[MAX_FIELD_LEN];
    char device_fingerprint[MAX_FP_LEN];  /* 设备指纹（硬件绑定哈希） */
    char uuid[MAX_UUID_LEN];              /* 服务端分配的UUID v4 */
    char agent_id[MAX_ID_LEN];            /* 本地生成的agent_id（ag_前缀） */
    char server_agent_id[MAX_SERVER_ID_LEN]; /* 服务端分配的agent_id（agent_前缀） */
    char server_url_override[MAX_URL_LEN]; /* 服务端下发的URL覆盖，优先级最高 */
    char location[MAX_FIELD_LEN];          /* 存放位置（手动录入） */
    char department[MAX_FIELD_LEN];        /* 所属部门（手动录入） */
    char responsible_person[MAX_FIELD_LEN];/* 责任人（手动录入） */
    int  allow_remote_stop;                /* 是否允许通过IPC远程停止服务（默认0=不允许） */
} AgentConfig;

/* 注册响应结果结构体 */
typedef struct {
    char uuid[MAX_UUID_LEN];              /* 服务端分配的UUID */
    char server_agent_id[MAX_SERVER_ID_LEN]; /* 服务端分配的agent_id */
    int  heartbeat_interval;              /* 服务端下发的心跳间隔 */
    char server_url[MAX_URL_LEN];         /* 服务端下发的URL */
} RegisterResult;

AgentConfig* LoadConfig(void);
int  SaveConfig(const AgentConfig *config);
int  SaveConfigTo(const AgentConfig *config, const char *path);
const char* EffectiveServerURL(const AgentConfig *config);
void ApplyServerUpdate(AgentConfig *config, const char *new_url, int new_interval);
void FreeConfig(AgentConfig *config);

/* 日志接口（在 main.c 中实现） */
extern FILE *g_log_file;
void init_logger(void);
void log_write(const char *fmt, ...);

#endif /* CONFIG_H */