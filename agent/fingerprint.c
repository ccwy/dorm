/* fingerprint.c - 设备指纹实现 */
#include "fingerprint.h"
#include "collector.h"
#include <windows.h>
#include <iphlpapi.h>
#include <stdio.h>
#include <string.h>

/* MinGW SDK may not define these when targeting older Windows */
#ifndef CALG_SHA_256
#define CALG_SHA_256 0x0000800c
#endif
#ifndef PROV_RSA_AES
#define PROV_RSA_AES 24
#endif

/* safe_strncpy: strncpy with guaranteed null-termination */
static void safe_strncpy(char *dst, const char *src, size_t bufsize) {
    snprintf(dst, bufsize, "%s", src);
}

/* get_disk_serial: 获取系统盘卷序列号
 * 使用 GetVolumeInformationW 获取C:卷序列号
 */
void get_disk_serial(char *buf, size_t bufsize) {
    DWORD serial = 0;
    if (GetVolumeInformationW(L"C:\\", NULL, 0, &serial, NULL, NULL, NULL, 0)) {
        snprintf(buf, bufsize, "%08lX", serial);
    } else {
        safe_strncpy(buf, "unknown", bufsize);
    }
}

/* get_primary_mac: 获取主MAC地址（用于指纹计算）
 * 使用 GetAdaptersInfo 获取第一个非回环适配器的MAC
 */
static void get_primary_mac(char *buf, size_t bufsize) {
    ULONG bufLen = 0;
    GetAdaptersInfo(NULL, &bufLen);
    if (bufLen == 0) {
        safe_strncpy(buf, "unknown", bufsize);
        return;
    }

    PIP_ADAPTER_INFO adapterInfo = (PIP_ADAPTER_INFO)malloc(bufLen);
    if (!adapterInfo) {
        safe_strncpy(buf, "unknown", bufsize);
        return;
    }

    if (GetAdaptersInfo(adapterInfo, &bufLen) == ERROR_SUCCESS) {
        PIP_ADAPTER_INFO adapter = adapterInfo;
        while (adapter) {
            if (adapter->Type != MIB_IF_TYPE_LOOPBACK && adapter->AddressLength >= 6) {
                snprintf(buf, bufsize, "%02X:%02X:%02X:%02X:%02X:%02X",
                         adapter->Address[0], adapter->Address[1], adapter->Address[2],
                         adapter->Address[3], adapter->Address[4], adapter->Address[5]);
                free(adapterInfo);
                return;
            }
            adapter = adapter->Next;
        }
    }
    free(adapterInfo);
    safe_strncpy(buf, "unknown", bufsize);
}

/* fingerprint_generate: 生成设备指纹
 * 算法：SHA-256(hostname + "|" + mac_address + "|" + disk_serial)
 * 返回64字符hex字符串
 * 内部自动采集hostname、mac_address、disk_serial
 */
void fingerprint_generate(char *buf, size_t bufsize) {
    if (!buf || bufsize < MAX_FP_LEN) {
        if (buf) buf[0] = '\0';
        return;
    }

    /* 采集三个指纹因子 */
    char hostname[64] = {0};
    char mac_address[18] = {0};
    char disk_serial[32] = {0};

    /* 获取主机名 */
    wchar_t whostname[64];
    DWORD hostsize = sizeof(whostname) / sizeof(wchar_t);
    if (GetComputerNameExW(ComputerNameDnsHostname, whostname, &hostsize))
        wide_to_utf8(whostname, hostname, sizeof(hostname));
    else
        safe_strncpy(hostname, "unknown", sizeof(hostname));

    /* 获取主MAC地址 */
    get_primary_mac(mac_address, sizeof(mac_address));

    /* 获取磁盘序列号 */
    get_disk_serial(disk_serial, sizeof(disk_serial));

    /* 拼接组合字符串 */
    char combined[512];
    snprintf(combined, sizeof(combined), "%s|%s|%s", hostname, mac_address, disk_serial);

    /* 使用Windows Cryptography API计算SHA-256 */
    HCRYPTPROV hProv = 0;
    HCRYPTHASH hHash = 0;
    DWORD hashLen = 32;
    BYTE hashData[32];

    if (CryptAcquireContext(&hProv, NULL, NULL, PROV_RSA_AES, CRYPT_VERIFYCONTEXT) &&
        CryptCreateHash(hProv, CALG_SHA_256, 0, 0, &hHash)) {
        CryptHashData(hHash, (BYTE*)combined, (DWORD)strlen(combined), 0);
        CryptGetHashParam(hHash, HP_HASHVAL, hashData, &hashLen, 0);
        CryptDestroyHash(hHash);
        CryptReleaseContext(hProv, 0);
    } else {
        /* CryptAcquireContext失败，回退到PROV_RSA_FULL */
        if (CryptAcquireContext(&hProv, NULL, NULL, PROV_RSA_FULL, CRYPT_VERIFYCONTEXT) &&
            CryptCreateHash(hProv, CALG_SHA_256, 0, 0, &hHash)) {
            CryptHashData(hHash, (BYTE*)combined, (DWORD)strlen(combined), 0);
            CryptGetHashParam(hHash, HP_HASHVAL, hashData, &hashLen, 0);
            CryptDestroyHash(hHash);
            CryptReleaseContext(hProv, 0);
        } else {
            /* SHA-256不可用，使用简单哈希（极低概率） */
            memset(hashData, 0, sizeof(hashData));
            for (size_t i = 0; i < strlen(combined); i++)
                hashData[i % 32] ^= (BYTE)combined[i];
        }
    }

    /* 转为hex字符串 */
    for (DWORD i = 0; i < hashLen && i * 2 < bufsize - 1; i++) {
        snprintf(buf + i * 2, bufsize - i * 2, "%02x", hashData[i]);
    }
    buf[hashLen * 2] = '\0';
}

/* compute_info_hash: 计算系统信息哈希
 * 算法：SHA-256(hostname|os_name|os_version|cpu_model|cpu_cores|total_memory_mb|mac_address|logged_in_user)
 * 用于心跳请求中检测信息变更
 */
void compute_info_hash(const SystemInfo *info, char *buf, size_t bufsize) {
    if (!buf || bufsize < MAX_FP_LEN || !info) {
        if (buf) buf[0] = '\0';
        return;
    }

    /* 拼接系统信息关键字段 */
    char combined[1024];
    snprintf(combined, sizeof(combined), "%s|%s|%s|%s|%d|%lu|%s|%s",
             info->hostname, info->os_name, info->os_version,
             info->cpu_model, info->cpu_cores, info->total_memory_mb,
             info->mac_address, info->logged_in_user);

    /* 使用Windows Cryptography API计算SHA-256（与fingerprint_generate相同模式） */
    HCRYPTPROV hProv = 0;
    HCRYPTHASH hHash = 0;
    DWORD hashLen = 32;
    BYTE hashData[32];

    if (CryptAcquireContext(&hProv, NULL, NULL, PROV_RSA_AES, CRYPT_VERIFYCONTEXT) &&
        CryptCreateHash(hProv, CALG_SHA_256, 0, 0, &hHash)) {
        CryptHashData(hHash, (BYTE*)combined, (DWORD)strlen(combined), 0);
        CryptGetHashParam(hHash, HP_HASHVAL, hashData, &hashLen, 0);
        CryptDestroyHash(hHash);
        CryptReleaseContext(hProv, 0);
    } else {
        if (CryptAcquireContext(&hProv, NULL, NULL, PROV_RSA_FULL, CRYPT_VERIFYCONTEXT) &&
            CryptCreateHash(hProv, CALG_SHA_256, 0, 0, &hHash)) {
            CryptHashData(hHash, (BYTE*)combined, (DWORD)strlen(combined), 0);
            CryptGetHashParam(hHash, HP_HASHVAL, hashData, &hashLen, 0);
            CryptDestroyHash(hHash);
            CryptReleaseContext(hProv, 0);
        } else {
            memset(hashData, 0, sizeof(hashData));
            for (size_t i = 0; i < strlen(combined); i++)
                hashData[i % 32] ^= (BYTE)combined[i];
        }
    }

    /* 转为hex字符串 */
    for (DWORD i = 0; i < hashLen && i * 2 < bufsize - 1; i++) {
        snprintf(buf + i * 2, bufsize - i * 2, "%02x", hashData[i]);
    }
    buf[hashLen * 2] = '\0';
}