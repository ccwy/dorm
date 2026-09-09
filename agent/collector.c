/* collector.c - 系统信息采集实现 */
#include "collector.h"
#include "collect_user.h"
#include "fingerprint.h"
#include <windows.h>
#include <winnt.h>
#include <iphlpapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef AGENT_VERSION
#define AGENT_VERSION "1.0.0"
#endif

/* ---- RtlGetVersion 动态加载（兼容XP~Win11） ---- */
typedef LONG(NTAPI *RtlGetVersionPtr)(PRTL_OSVERSIONINFOW);

static int get_os_version(RTL_OSVERSIONINFOW *ovi) {
    HMODULE hNtDll = GetModuleHandleW(L"ntdll.dll");
    if (!hNtDll) return -1;
    RtlGetVersionPtr pRtlGetVersion =
        (RtlGetVersionPtr)GetProcAddress(hNtDll, "RtlGetVersion");
    if (!pRtlGetVersion) return -1;
    ovi->dwOSVersionInfoSize = sizeof(RTL_OSVERSIONINFOW);
    return (int)pRtlGetVersion(ovi);
}

/* ---- 宽字符转UTF-8 ---- */
int wide_to_utf8(const wchar_t *wstr, char *buf, size_t bufsize) {
    if (!wstr || !buf || bufsize == 0) { if (buf) buf[0] = '\0'; return -1; }
    int len = WideCharToMultiByte(CP_UTF8, 0, wstr, -1, buf, (int)bufsize, NULL, NULL);
    if (len <= 0) { buf[0] = '\0'; return -1; }
    return len - 1; /* 返回不含null终止符的长度 */
}

/* ---- 操作系统名称映射 ---- */
static void map_os_name(DWORD major, DWORD minor, DWORD build, char *buf, size_t bufsize) {
    if (major == 10) {
        if (build >= 22000)
            strncpy(buf, "Windows 11", bufsize - 1);
        else
            strncpy(buf, "Windows 10", bufsize - 1);
    } else if (major == 6 && minor == 3) {
        strncpy(buf, "Windows 8.1", bufsize - 1);
    } else if (major == 6 && minor == 2) {
        strncpy(buf, "Windows 8", bufsize - 1);
    } else if (major == 6 && minor == 1) {
        strncpy(buf, "Windows 7", bufsize - 1);
    } else if (major == 6 && minor == 0) {
        strncpy(buf, "Windows Vista", bufsize - 1);
    } else if (major == 5 && minor == 1) {
        strncpy(buf, "Windows XP", bufsize - 1);
    } else if (major == 5 && minor == 0) {
        strncpy(buf, "Windows 2000", bufsize - 1);
    } else {
        snprintf(buf, bufsize, "Windows %lu.%lu", major, minor);
    }
}

/* ---- 采集主机名 ---- */
static void collect_hostname(SystemInfo *info) {
    wchar_t wbuf[MAX_COMPUTERNAME_LENGTH + 1];
    DWORD size = MAX_COMPUTERNAME_LENGTH + 1;
    if (GetComputerNameExW(ComputerNameDnsHostname, wbuf, &size))
        wide_to_utf8(wbuf, info->hostname, MAX_HOSTNAME_LEN);
    else
        strncpy(info->hostname, "unknown", MAX_HOSTNAME_LEN - 1);
}

/* ---- 采集操作系统信息 ---- */
static void collect_os_info(SystemInfo *info) {
    RTL_OSVERSIONINFOW ovi = {0};
    if (get_os_version(&ovi) == 0) {
        map_os_name(ovi.dwMajorVersion, ovi.dwMinorVersion,
                    ovi.dwBuildNumber, info->os_name, MAX_OS_NAME_LEN);
        snprintf(info->os_version, MAX_OS_VERSION_LEN, "%lu.%lu.%lu",
                 ovi.dwMajorVersion, ovi.dwMinorVersion, ovi.dwBuildNumber);
    } else {
        strncpy(info->os_name, "Unknown", MAX_OS_NAME_LEN - 1);
        strncpy(info->os_version, "0.0.0", MAX_OS_VERSION_LEN - 1);
    }
}

/* ---- 采集系统架构 ---- */
static void collect_os_arch(SystemInfo *info) {
    SYSTEM_INFO si;
    GetNativeSystemInfo(&si);
    switch (si.wProcessorArchitecture) {
        case PROCESSOR_ARCHITECTURE_AMD64:
            strncpy(info->os_arch, "x64", MAX_OS_ARCH_LEN - 1);
            break;
        case PROCESSOR_ARCHITECTURE_INTEL:
            strncpy(info->os_arch, "x86", MAX_OS_ARCH_LEN - 1);
            break;
        case PROCESSOR_ARCHITECTURE_ARM64:
            strncpy(info->os_arch, "ARM64", MAX_OS_ARCH_LEN - 1);
            break;
        case PROCESSOR_ARCHITECTURE_ARM:
            strncpy(info->os_arch, "ARM", MAX_OS_ARCH_LEN - 1);
            break;
        default:
            strncpy(info->os_arch, "Unknown", MAX_OS_ARCH_LEN - 1);
            break;
    }
}

/* ---- 采集CPU信息 ---- */
static void collect_cpu_info(SystemInfo *info) {
    /* CPU型号：从注册表读取 */
    HKEY hKey;
    if (RegOpenKeyExW(HKEY_LOCAL_MACHINE,
            L"HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0",
            0, KEY_READ, &hKey) == ERROR_SUCCESS) {
        wchar_t wbuf[MAX_CPU_MODEL_LEN];
        DWORD bufsize = sizeof(wbuf);
        if (RegQueryValueExW(hKey, L"ProcessorNameString", NULL, NULL,
                              (LPBYTE)wbuf, &bufsize) == ERROR_SUCCESS)
            wide_to_utf8(wbuf, info->cpu_model, MAX_CPU_MODEL_LEN);
        RegCloseKey(hKey);
    }
    if (info->cpu_model[0] == '\0')
        strncpy(info->cpu_model, "Unknown", MAX_CPU_MODEL_LEN - 1);

    /* CPU核心数 */
    SYSTEM_INFO si;
    GetNativeSystemInfo(&si);
    info->cpu_cores = (int)si.dwNumberOfProcessors;
}

/* ---- 采集内存信息 ---- */
static void collect_memory_info(SystemInfo *info) {
    MEMORYSTATUSEX ms;
    ms.dwLength = sizeof(ms);
    if (GlobalMemoryStatusEx(&ms)) {
        info->total_memory_mb = (unsigned long)(ms.ullTotalPhys / (1024 * 1024));
        info->available_memory_mb = (unsigned long)(ms.ullAvailPhys / (1024 * 1024));
    }
}

/* ---- 采集磁盘信息 ---- */
static void collect_disks(SystemInfo *info) {
    wchar_t drives[256];
    DWORD len = GetLogicalDriveStringsW(sizeof(drives) / sizeof(wchar_t), drives);
    if (len == 0) { strncpy(info->disks, "[]", MAX_DISKS_JSON_LEN - 1); return; }

    cJSON *arr = cJSON_CreateArray();
    wchar_t *p = drives;
    while (*p) {
        UINT type = GetDriveTypeW(p);
        if (type == DRIVE_FIXED) {
            ULARGE_INTEGER free_avail, total, free;
            if (GetDiskFreeSpaceExW(p, &free_avail, &total, &free)) {
                char drive_letter[4];
                wide_to_utf8(p, drive_letter, sizeof(drive_letter));
                /* 去掉末尾反斜杠 */
                size_t dlen = strlen(drive_letter);
                if (dlen > 0 && drive_letter[dlen - 1] == '\\')
                    drive_letter[dlen - 1] = '\0';

                cJSON *obj = cJSON_CreateObject();
                cJSON_AddStringToObject(obj, "drive", drive_letter);
                cJSON_AddNumberToObject(obj, "total_gb",
                    (double)(total.QuadPart / (1024.0 * 1024 * 1024)));
                cJSON_AddNumberToObject(obj, "free_gb",
                    (double)(free_avail.QuadPart / (1024.0 * 1024 * 1024)));
                cJSON_AddItemToArray(arr, obj);
            }
        }
        p += wcslen(p) + 1;
    }
    char *json = cJSON_PrintUnformatted(arr);
    cJSON_Delete(arr);
    if (json) {
        strncpy(info->disks, json, MAX_DISKS_JSON_LEN - 1);
        free(json);
    }
}

/* ---- 采集网络信息（MAC、IP、网卡列表） ---- */
static void collect_network_info(SystemInfo *info) {
    /* 使用GetAdaptersInfo（XP兼容） */
    ULONG bufLen = 0;
    GetAdaptersInfo(NULL, &bufLen);
    if (bufLen == 0) {
        strncpy(info->mac_address, "unknown", MAX_MAC_LEN - 1);
        strncpy(info->ip_address, "unknown", MAX_IP_LEN - 1);
        strncpy(info->network_interfaces, "[]", MAX_IFACES_JSON_LEN - 1);
        return;
    }

    PIP_ADAPTER_INFO adapterInfo = (PIP_ADAPTER_INFO)malloc(bufLen);
    if (!adapterInfo) return;

    cJSON *ifaces = cJSON_CreateArray();
    int first_mac_set = 0, first_ip_set = 0;

    if (GetAdaptersInfo(adapterInfo, &bufLen) == ERROR_SUCCESS) {
        PIP_ADAPTER_INFO adapter = adapterInfo;
        while (adapter) {
            /* 跳过回环适配器 */
            if (adapter->Type == MIB_IF_TYPE_LOOPBACK) {
                adapter = adapter->Next;
                continue;
            }

            /* MAC地址格式化 */
            char mac_str[MAX_MAC_LEN];
            snprintf(mac_str, MAX_MAC_LEN, "%02X:%02X:%02X:%02X:%02X:%02X",
                     adapter->Address[0], adapter->Address[1], adapter->Address[2],
                     adapter->Address[3], adapter->Address[4], adapter->Address[5]);

            /* 取第一个非回环适配器的MAC和IP */
            if (!first_mac_set && adapter->AddressLength >= 6) {
                strncpy(info->mac_address, mac_str, MAX_MAC_LEN - 1);
                first_mac_set = 1;
            }

            /* IP地址：取第一个有IP的适配器 */
            if (!first_ip_set && adapter->IpAddressList.IpAddress.String[0] &&
                strcmp(adapter->IpAddressList.IpAddress.String, "0.0.0.0") != 0) {
                strncpy(info->ip_address,
                        adapter->IpAddressList.IpAddress.String, MAX_IP_LEN - 1);
                first_ip_set = 1;
            }

            /* 网卡列表JSON */
            cJSON *obj = cJSON_CreateObject();
            /* GetAdaptersInfo的Description是ANSI字符串 */
            cJSON_AddStringToObject(obj, "name", adapter->Description);
            cJSON_AddStringToObject(obj, "mac", mac_str);

            if (adapter->IpAddressList.IpAddress.String[0] &&
                strcmp(adapter->IpAddressList.IpAddress.String, "0.0.0.0") != 0) {
                cJSON_AddStringToObject(obj, "ip",
                    adapter->IpAddressList.IpAddress.String);
            } else {
                cJSON_AddStringToObject(obj, "ip", "");
            }
            cJSON_AddItemToArray(ifaces, obj);

            adapter = adapter->Next;
        }
    }
    free(adapterInfo);

    if (!first_mac_set)
        strncpy(info->mac_address, "unknown", MAX_MAC_LEN - 1);
    if (!first_ip_set)
        strncpy(info->ip_address, "unknown", MAX_IP_LEN - 1);

    char *json = cJSON_PrintUnformatted(ifaces);
    cJSON_Delete(ifaces);
    if (json) {
        strncpy(info->network_interfaces, json, MAX_IFACES_JSON_LEN - 1);
        free(json);
    }
}

/* ---- 采集所有系统信息 ---- */
SystemInfo* collector_collect(void) {
    SystemInfo *info = (SystemInfo*)calloc(1, sizeof(SystemInfo));
    if (!info) return NULL;

    collect_hostname(info);
    collect_os_info(info);
    collect_os_arch(info);
    collect_cpu_info(info);
    collect_memory_info(info);
    collect_disks(info);
    collect_network_info(info);

    /* 采集登录用户名（委托给collect_user模块） */
    collect_logged_in_user(info->logged_in_user, MAX_USERNAME_LEN);

    /* 编译时版本号 */
    strncpy(info->agent_version, AGENT_VERSION, sizeof(info->agent_version) - 1);

    return info;
}

/* ---- 释放SystemInfo ---- */
void collector_free(SystemInfo *info) {
    free(info);
}