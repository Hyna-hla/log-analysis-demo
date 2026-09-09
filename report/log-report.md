# 日志诊断报告 — `error.log`

> 由 `log_diagnose.py` 自动生成于 2026-09-09 11:50:37

## 1. 总览

| 指标 | 数值 |
| --- | --- |
| 日志总行数 | 80 |
| 提取到的异常/告警事件 | 16 |
| FATAL + ERROR | 13 |
| 异常类别数 | 8 |
| 综合风险等级 | **高** |
| 首个事件时间 | 2026-09-09 08:01:44 |
| 末个事件时间 | 2026-09-09 08:07:22 |

## 2. 严重级别分布

| 级别 | 次数 |
| --- | ---: |
| FATAL | 2 |
| ERROR | 11 |
| WARN | 3 |

## 3. 异常分类统计

| 类别 | 次数 | 占比 | 处置建议 |
| --- | ---: | ---: | --- |
| 网络 / 超时 | 4 | 25.0% | 确认下游服务与 DNS；为外部调用设置合理的超时/重试/熔断，并核对网络策略与端口。 |
| 其它 / 未分类 | 3 | 18.8% | 保留原始上下文，结合发布记录与上下游日志进一步定位。 |
| 数据库 / SQL | 3 | 18.8% | 检查连接池配置、慢查询与索引；确认数据库实例存活、凭据与连接数上限。 |
| 空值 / 键缺失 | 2 | 12.5% | 在取值处增加判空与默认值/校验；对外部输入做 schema 校验，避免直接下标访问。 |
| 权限 / 认证 | 1 | 6.2% | 核对 Token/密钥是否过期、账号角色与资源 ACL；排查 401/403 的鉴权中间件链路。 |
| 内存 / 资源 | 1 | 6.2% | 排查内存泄漏与大对象；增加资源上限与释放逻辑，必要时扩容并开启内存监控告警。 |
| 类型 / 参数 | 1 | 6.2% | 在入口处做参数类型与范围校验；复现触发输入并补充单元测试覆盖边界值。 |
| 依赖 / 导入 | 1 | 6.2% | 锁定并重装依赖版本，核对运行环境与 requirements/lock 文件是否一致。 |

## 4. Top 5 高频异常签名

| # | 次数 | 类别 | 签名(已归一化) |
| ---: | ---: | --- | --- |
| 1 | 4 | 网络 / 超时 | `TimeoutError: upstream timed out after 3000ms` |
| 2 | 2 | 数据库 / SQL | `sqlite3.OperationalError: database is locked` |
| 3 | 2 | 空值 / 键缺失 | `AttributeError: '?' object has no attribute '?'` |
| 4 | 1 | 其它 / 未分类 | `N-N-N N:N:N WARN  http.client upstream /inventory slow, cost=812ms` |
| 5 | 1 | 数据库 / SQL | `N-N-N N:N:N WARN  db.pool connection usage N% (N/N)` |

## 5. 分类证据(代表性堆栈)

### 网络 / 超时 （共 4 次，首次出现于第 6 行）

```
2026-09-09 08:02:03 ERROR order.svc failed to create order for uid=1001
Traceback (most recent call last):
  File "/srv/app/order/service.py", line 88, in create_order
    inventory = self.client.get_sku(sku_id)
  File "/srv/app/http/client.py", line 210, in get_sku
    raise TimeoutError("upstream timed out after 3000ms")
TimeoutError: upstream timed out after 3000ms
```

### 其它 / 未分类 （共 3 次，首次出现于第 76 行）

```
2026-09-09 08:08:40 FATAL app.core unrecoverable state, shutting down
java.lang.IllegalStateException: Connection pool has been closed
	at com.app.Pool.borrow(Pool.java:58)
	at com.app.App.main(App.java:21)
```

### 数据库 / SQL （共 3 次，首次出现于第 21 行）

```
2026-09-09 08:03:02 ERROR billing.repo insert invoice failed
Traceback (most recent call last):
  File "/srv/app/billing/repo.py", line 154, in insert
    cursor.execute(sql, params)
sqlite3.OperationalError: database is locked
```

### 空值 / 键缺失 （共 2 次，首次出现于第 26 行）

```
2026-09-09 08:03:40 ERROR profile.api get profile failed uid=2045
Traceback (most recent call last):
  File "/srv/app/profile/api.py", line 41, in get
    city = profile.address.city
AttributeError: 'NoneType' object has no attribute 'city'
```

### 权限 / 认证 （共 1 次，首次出现于第 31 行）

```
2026-09-09 08:04:10 ERROR auth.mw token verify failed uid=guest
Traceback (most recent call last):
  File "/srv/app/auth/middleware.py", line 66, in verify
    claims = jwt.decode(tok, secret)
PermissionError: [Errno 13] access is denied: token signature invalid
```

### 内存 / 资源 （共 1 次，首次出现于第 44 行）

```
2026-09-09 08:05:48 FATAL worker.oom worker-3 crashed
java.lang.OutOfMemoryError: Java heap space
	at com.app.Worker.run(Worker.java:132)
	at java.base/java.lang.Thread.run(Thread.java:833)
```

### 类型 / 参数 （共 1 次，首次出现于第 48 行）

```
2026-09-09 08:06:02 ERROR report.gen render failed
Traceback (most recent call last):
  File "/srv/app/report/gen.py", line 25, in render
    total = price * qty
TypeError: unsupported operand type(s) for *: 'str' and 'int'
```

### 依赖 / 导入 （共 1 次，首次出现于第 58 行）

```
2026-09-09 08:07:01 ERROR plugin.load cannot load plugin etl
Traceback (most recent call last):
  File "/srv/app/plugin/loader.py", line 19, in load
    module = importlib.import_module(name)
ModuleNotFoundError: No module named 'pandas'
```

## 6. 结论与下一步

- 主要矛盾是 **网络 / 超时**，占全部事件的 25.0%，应优先处置。
- **网络 / 超时**：确认下游服务与 DNS；为外部调用设置合理的超时/重试/熔断，并核对网络策略与端口。
- **其它 / 未分类**：保留原始上下文，结合发布记录与上下游日志进一步定位。
- **数据库 / SQL**：检查连接池配置、慢查询与索引；确认数据库实例存活、凭据与连接数上限。
- 建议为上述高频异常签名配置监控告警，并在修复后回归验证日志中不再复现。
