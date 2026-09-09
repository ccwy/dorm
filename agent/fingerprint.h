/* fingerprint.h - 设备指纹接口声明 */
#ifndef FINGERPRINT_H
#define FINGERPRINT_H

#include "config.h"

/* 生成设备指纹: SHA-256(hostname + "|" + mac_address + "|" + disk_serial)
 * 结果写入buf，为64字符hex字符串 + null终止符
 * 内部自动采集hostname、mac_address、disk_serial
 */
void fingerprint_generate(char *buf, size_t bufsize);

/* 获取系统盘(C:)卷序列号 */
void get_disk_serial(char *buf, size_t bufsize);

/* 计算系统信息哈希: SHA-256(hostname|os_name|os_version|cpu_model|cpu_cores|total_memory_mb|mac_address|logged_in_user)
 * 用于心跳请求中检测信息变更，避免每次心跳都发送完整信息
 * 结果写入buf，为64字符hex字符串 + null终止符
 */
void compute_info_hash(const SystemInfo *info, char *buf, size_t bufsize);

#endif /* FINGERPRINT_H */