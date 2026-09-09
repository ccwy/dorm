/* collect_user.h - 用户信息采集接口声明 */
#ifndef COLLECT_USER_H
#define COLLECT_USER_H

/* 采集当前Windows登录用户名 */
void collect_logged_in_user(char *buf, size_t bufsize);

#endif /* COLLECT_USER_H */