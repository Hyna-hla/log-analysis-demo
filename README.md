# Log Analysis Demo — 日志诊断器

一条命令把原始 `error.log` 变成结构化的 Markdown 诊断报告：**自动提取异常 → 分类聚类 → 定位主因 → 给出处置建议**。纯 Python 标准库实现，无需安装任何第三方依赖。

## Problem

线上服务吐出成百上千行日志，人工逐行排查存在三个痛点：

- Python traceback / Java stacktrace 跨多行，肉眼容易漏掉真正的异常末行；
- 异常种类混杂（超时、数据库锁、空指针、鉴权、OOM……），分不清哪类是主要矛盾；
- 同样的错误反复刷屏，无法快速看出高频签名与时间分布。

目标：用脚本自动完成「提取 → 归一化 → 分类 → 统计 → 出报告」，让人只看报告就能决定先修什么。

## Approach

```
error.log
   │  逐行扫描，识别 Python traceback 块 / Java 堆栈块 / 单行 ERROR·WARN
   ▼
异常提取（把跨行堆栈合并为一个事件，并吸收其上方的 ERROR 导语，避免重复计数）
   │  抹除数字、十六进制、引号内容得到“归一化签名”
   ▼
规则分类（数据库/网络超时/空值/鉴权/内存/类型/语法/依赖 …）
   │  按严重级别、类别、签名聚合统计
   ▼
Markdown 报告（总览 + 级别分布 + 分类占比 + Top 高频签名 + 堆栈证据 + 修复建议）
```

关键设计：

1. **事件而非行**：一个完整堆栈只算一个事件，严重级别取导语与异常中的更高者。
2. **签名归一化**：`uid=1001` / `uid=1002` 归并为同一签名，才能统计“出现了几次”。
3. **证据可追溯**：每个类别都附上代表性原始堆栈，报告结论可回溯到日志原文。

## Tools

| 工具 | 用途 |
| --- | --- |
| Python 3 | 解析、正则匹配、聚合统计、生成报告（仅标准库 `re/collections/pathlib/argparse`） |
| Git | 版本管理 |
| VS Code | 开发与调试 |

## Investigation

运行：

```bash
python src/log_diagnose.py samples/error.log -o report/log-report.md
```

对样例 `samples/error.log`（80 行混合日志）的调查过程：

1. 共提取 **16 个事件**（ERROR 13、WARN 3，含 2 个 FATAL 级故障）。
2. 分类后发现 **网络/超时占 25%（4 次）**，全部是 `TimeoutError: upstream timed out after 3000ms`，且每次都导致下单失败——这是主要矛盾。
3. 其次是数据库 `database is locked`（2 次）、空值 `'NoneType' has no attribute`（2 次），以及 OOM、鉴权失败、类型错误、缺依赖各 1 次。
4. 完整证据与逐类建议见自动生成的 [`report/log-report.md`](report/log-report.md)。

## Result

- 输入 80 行原始日志，**秒级**输出一份可直接发给团队的 Markdown 诊断报告；
- 自动定位首要问题为**下游库存服务超时**，并按类别给出可执行的处置顺序；
- 换任何同格式日志即可复用：`python src/log_diagnose.py <你的日志>`，规则表在源码顶部 `CATEGORY_RULES`，可按团队技术栈扩展。

## 目录结构

```
log-analysis-demo/
├─ src/log_diagnose.py      # 诊断器主程序
├─ samples/error.log        # 样例日志
└─ report/log-report.md     # 自动生成的诊断报告
```
