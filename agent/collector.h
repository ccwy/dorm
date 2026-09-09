/* collector.h - 系统信息采集接口声明 */
#ifndef COLLECTOR_H
#define COLLECTOR_H

#include "config.h"

#define MAX_HOSTNAME_LEN     64
#define MAX_OS_NAME_LEN      64
#define MAX_OS_VERSION_LEN   32
#define MAX_OS_ARCH_LEN      8
#define MAX_CPU_MODEL_LEN    128
#define MAX_MAC_LEN          18     /* XX:XX:XX:XX:XX:XX + null */
#define MAX_IP_LEN           46     /* IPv6 max length */
#define MAX_USERNAME_LEN     64
#define MAX_DISKS_JSON_LEN   2048
#define MAX_IFACES_JSON_LEN  4096

typedef struct {
    char hostname[MAX_HOSTNAME_LEN];
    char os_name[MAX_OS_NAME_LEN];
    char os_version[MAX_OS_VERSION_LEN];
    char os_arch[MAX_OS_ARCH_LEN];
    char cpu_model[MAX_CPU_MODEL_LEN];
    int  cpu_cores;
    unsigned long total_memory_mb;
    unsigned long available_memory_mb;
    char disks[MAX_DISKS_JSON_LEN];         /* JSON数组: [{"drive":"C:","total_gb":100,"free_gb":50},...] */
    char mac_address[MAX_MAC_LEN];
    char ip_address[MAX_IP_LEN];
    char network_interfaces[MAX_IFACES_JSON_LEN]; /* JSON数组: [{"name":"以太网","mac":"XX:XX:..","ip":"192.168.."},...] */
    char logged_in_user[MAX_USERNAME_LEN];
    char agent_version[32];
    char device_fingerprint[MAX_FP_LEN];
    char asset_number[MAX_FIELD_LEN];
    /* 手动录入字段 */
    char location[MAX_FIELD_LEN];
    char department[MAX_FIELD_LEN];
    char responsible_person[MAX_FIELD_LEN];
} SystemInfo;

/* 采集所有系统信息 */
SystemInfo* collector_collect(void);

/* 释放SystemInfo */
void collector_free(SystemInfo *info);

/* 宽字符转UTF-8 */
int wide_to_utf8(const wchar_t *wstr, char *buf, size_t bufsize);

#endif /* COLLECTOR_H */