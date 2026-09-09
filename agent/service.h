/* service.h - Agent服务生命周期管理接口声明 */
#ifndef SERVICE_H
#define SERVICE_H

#include "config.h"
#include "collector.h"
#include "reporter.h"

#define MIGRATION_MAX_RETRIES 3

typedef struct {
    AgentConfig  *config;
    SystemInfo   *last_info;
    Reporter     *reporter;
    int           heartbeat_counter;
    int           consecutive_failures;
    int           reregister_count;   /* 401重新注册计数器，防止死循环 */
    int           offline_mode;
    int           migration_fail_count;
    int           migration_confirmed;
    int           running;            /* 运行标志，用于优雅退出 */
    char          info_hash[MAX_FP_LEN];       /* 当前系统信息哈希 */
} Agent;

/* 创建Agent实例 */
Agent* agent_create(AgentConfig *config);

/* 运行Agent主循环 */
void agent_run(Agent *a);

/* 销毁Agent实例 */
void agent_destroy(Agent *a);

/* ---- 开机自启 ---- */
void ensure_autostart(void);
void remove_autostart(void);

/* ---- IPC命名管道 ---- */
void start_ipc_server(Agent *agent);
int  send_ipc_command(const char *command);

/* ---- CLI命令 ---- */
int execute_stop(void);
int execute_uninstall(void);
int execute_edit_info(void);

/* ---- 配置窗口（兜底方案） ---- */
int showSetupWindow(char *server_url, size_t url_bufsize,
                    char *api_key, size_t key_bufsize);

/* ---- 信息编辑窗口 ---- */
int show_info_editor(const AgentConfig *current,
                     char *location, size_t loc_bufsize,
                     char *department, size_t dept_bufsize,
                     char *responsible_person, size_t resp_bufsize);

#endif /* SERVICE_H */