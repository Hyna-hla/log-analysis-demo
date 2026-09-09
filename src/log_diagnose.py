#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demo 1 / 日志诊断器 (Log Diagnoser)
-----------------------------------
输入 : 一个原始日志文件 (如 error.log)
流程 : 读取 -> 自动提取异常/错误 -> 分类与聚类 -> 生成 Markdown 诊断报告
用法 :
    python log_diagnose.py <logfile> [-o report.md] [--top N]
依赖 : 仅 Python 标准库
"""

import argparse
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------------------
# 1. 分类规则：按关键字把异常归并到可读类别 (命中即归类，顺序即优先级)
# ----------------------------------------------------------------------------
CATEGORY_RULES = [
    ("数据库 / SQL",      re.compile(r"(sql|database|db\b|operationalerror|integrityerror|deadlock|connection refused.*3306|psycopg|sqlite)", re.I)),
    ("网络 / 超时",        re.compile(r"(timeout|timed out|connection reset|connection refused|broken pipe|dns|unreachable|socket|econnreset|etimedout)", re.I)),
    ("空值 / 键缺失",      re.compile(r"(nullpointer|keyerror|key not found|nonetype|attributeerror.*nonetype|\bnone\b.*attribute|undefined is not)", re.I)),
    ("权限 / 认证",        re.compile(r"(permission|denied|unauthor|forbidden|401|403|auth|token|credential|access is denied)", re.I)),
    ("内存 / 资源",        re.compile(r"(memoryerror|out of memory|\boom\b|no space left|too many open files|resource temporarily)", re.I)),
    ("类型 / 参数",        re.compile(r"(typeerror|valueerror|numberformatexception|invalid argument|illegalargument|cannot unpack|expected.*got)", re.I)),
    ("语法 / 缩进",        re.compile(r"(syntaxerror|indentationerror|taberror|unexpected token|parse error)", re.I)),
    ("依赖 / 导入",        re.compile(r"(modulenotfound|importerror|cannot find module|no module named|classnotfound|nosuchmethod)", re.I)),
]
DEFAULT_CATEGORY = "其它 / 未分类"

SEVERITY_ORDER = ["FATAL", "ERROR", "WARN", "INFO", "DEBUG", "UNKNOWN"]
SEVERITY_RE = re.compile(r"\b(FATAL|CRITICAL|ERROR|WARN(?:ING)?|INFO|DEBUG|TRACE)\b", re.I)
TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?|\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2})")

# 异常首行：Python 异常 / Java 风格异常类
EXC_HEAD_RE = re.compile(
    r"^\s*(?:[\w$.]+\.)*[A-Za-z_]\w*(?:Error|Exception|Fault|Failure)\b(?:\s*:.*)?$"
)
PY_TB_START = re.compile(r"^Traceback \(most recent call last\):")


def classify(text: str) -> str:
    for name, pat in CATEGORY_RULES:
        if pat.search(text):
            return name
    return DEFAULT_CATEGORY


def normalize_signature(text: str) -> str:
    """把数字/十六进制/引号内容抹掉，让同类异常聚成同一签名。"""
    s = text.strip()
    s = re.sub(r"0x[0-9a-fA-F]+", "0x?", s)
    s = re.sub(r"['\"`].*?['\"`]", "'?'", s)
    s = re.sub(r"\b\d+\b", "N", s)
    return s[:160]


def parse_severity(line: str) -> str:
    m = SEVERITY_RE.search(line)
    if not m:
        return "UNKNOWN"
    sev = m.group(1).upper().replace("WARNING", "WARN").replace("CRITICAL", "FATAL")
    return sev if sev in SEVERITY_ORDER else "UNKNOWN"


# ----------------------------------------------------------------------------
# 2. 提取：把日志切成普通行 + 异常块(Python traceback / Java stacktrace)
# ----------------------------------------------------------------------------
def extract_events(lines):
    events = []          # 每个 event: {severity, category, signature, head, block, lineno, ts}
    i, n = 0, len(lines)
    while i < n:
        line = lines[i].rstrip("\n")

        # Python traceback 块
        if PY_TB_START.search(line):
            block = [line]
            j = i + 1
            head = line
            while j < n:
                cur = lines[j].rstrip("\n")
                block.append(cur)
                # 块结束：非缩进、且不是以 "File " / "During handling" 开头
                if cur and not cur.startswith((" ", "\t")) and not cur.startswith("During handling"):
                    head = cur  # 最后一行才是真正异常
                    break
                j += 1
            sig_text = head if head != line else line
            _append_event(events, _mk_event(i + 1, sig_text, block, force_sev="ERROR"))
            i = j + 1 if j < n else j
            continue

        # Java 风格：异常首行 + 若干 "at ..." 栈帧
        if EXC_HEAD_RE.match(line) and ("Error" in line or "Exception" in line):
            block = [line]
            j = i + 1
            while j < n and re.match(r"^\s+at [\w$.<>]+", lines[j]):
                block.append(lines[j].rstrip("\n"))
                j += 1
            while j < n and re.match(r"^\s*(Caused by:|\.\.\. \d+ more)", lines[j]):
                block.append(lines[j].rstrip("\n"))
                j += 1
            _append_event(events, _mk_event(i + 1, line, block, force_sev="ERROR"))
            i = j
            continue

        # 普通的 ERROR / FATAL / WARN 单行
        sev = parse_severity(line)
        if sev in ("FATAL", "ERROR", "WARN"):
            events.append(_mk_event(i + 1, line, [line], force_sev=sev))
        i += 1
    return events


def _append_event(events, ev):
    """若上一条是紧邻的 ERROR/WARN/FATAL 单行导语，则把它并入当前异常块，避免重复计数。"""
    if events:
        prev = events[-1]
        if (len(prev["block"]) == 1 and prev["lineno"] == ev["lineno"] - 1
                and prev["severity"] in ("ERROR", "WARN", "FATAL")):
            ev["block"] = prev["block"] + ev["block"]
            ev["lineno"] = prev["lineno"]
            sev_rank = {"FATAL": 3, "ERROR": 2, "WARN": 1}
            if sev_rank.get(prev["severity"], 0) > sev_rank.get(ev["severity"], 0):
                ev["severity"] = prev["severity"]
            events.pop()
    events.append(ev)


def _mk_event(lineno, sig_text, block, force_sev=None):
    sev = force_sev or parse_severity(sig_text)
    ts = TS_RE.search(sig_text)
    return {
        "lineno": lineno,
        "severity": sev,
        "category": classify(sig_text),
        "signature": normalize_signature(sig_text),
        "head": sig_text.strip(),
        "block": block,
        "ts": ts.group(1) if ts else "-",
    }


# ----------------------------------------------------------------------------
# 3. 生成 Markdown 报告
# ----------------------------------------------------------------------------
ADVICE = {
    "数据库 / SQL":   "检查连接池配置、慢查询与索引；确认数据库实例存活、凭据与连接数上限。",
    "网络 / 超时":    "确认下游服务与 DNS；为外部调用设置合理的超时/重试/熔断，并核对网络策略与端口。",
    "空值 / 键缺失":  "在取值处增加判空与默认值/校验；对外部输入做 schema 校验，避免直接下标访问。",
    "权限 / 认证":    "核对 Token/密钥是否过期、账号角色与资源 ACL；排查 401/403 的鉴权中间件链路。",
    "内存 / 资源":    "排查内存泄漏与大对象；增加资源上限与释放逻辑，必要时扩容并开启内存监控告警。",
    "类型 / 参数":    "在入口处做参数类型与范围校验；复现触发输入并补充单元测试覆盖边界值。",
    "语法 / 缩进":    "该类错误通常无法上线；运行静态检查/linter，确认部署的是可编译版本。",
    "依赖 / 导入":    "锁定并重装依赖版本，核对运行环境与 requirements/lock 文件是否一致。",
    "其它 / 未分类":  "保留原始上下文，结合发布记录与上下游日志进一步定位。",
}


def build_report(path: Path, events, total_lines, top: int) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sev_counter = Counter(e["severity"] for e in events)
    cat_counter = Counter(e["category"] for e in events)
    sig_counter = Counter(e["signature"] for e in events)

    by_cat = defaultdict(list)
    for e in events:
        by_cat[e["category"]].append(e)

    fatal_err = sev_counter.get("FATAL", 0) + sev_counter.get("ERROR", 0)
    risk = "高" if fatal_err >= 10 else ("中" if fatal_err else "低(仅告警)")

    out = []
    out.append(f"# 日志诊断报告 — `{path.name}`\n")
    out.append(f"> 由 `log_diagnose.py` 自动生成于 {now}\n")

    out.append("## 1. 总览\n")
    out.append("| 指标 | 数值 |")
    out.append("| --- | --- |")
    out.append(f"| 日志总行数 | {total_lines} |")
    out.append(f"| 提取到的异常/告警事件 | {len(events)} |")
    out.append(f"| FATAL + ERROR | {fatal_err} |")
    out.append(f"| 异常类别数 | {len(cat_counter)} |")
    out.append(f"| 综合风险等级 | **{risk}** |")
    timestamps = [e["ts"] for e in events if e["ts"] != "-"]
    if timestamps:
        out.append(f"| 首个事件时间 | {min(timestamps)} |")
        out.append(f"| 末个事件时间 | {max(timestamps)} |")
    out.append("")

    out.append("## 2. 严重级别分布\n")
    out.append("| 级别 | 次数 |")
    out.append("| --- | ---: |")
    for sev in SEVERITY_ORDER:
        if sev_counter.get(sev):
            out.append(f"| {sev} | {sev_counter[sev]} |")
    out.append("")

    out.append("## 3. 异常分类统计\n")
    out.append("| 类别 | 次数 | 占比 | 处置建议 |")
    out.append("| --- | ---: | ---: | --- |")
    total = max(len(events), 1)
    for cat, cnt in cat_counter.most_common():
        pct = f"{cnt / total * 100:.1f}%"
        out.append(f"| {cat} | {cnt} | {pct} | {ADVICE.get(cat, '')} |")
    out.append("")

    out.append(f"## 4. Top {min(top, len(sig_counter))} 高频异常签名\n")
    out.append("| # | 次数 | 类别 | 签名(已归一化) |")
    out.append("| ---: | ---: | --- | --- |")
    for idx, (sig, cnt) in enumerate(sig_counter.most_common(top), 1):
        cat = next(e["category"] for e in events if e["signature"] == sig)
        out.append(f"| {idx} | {cnt} | {cat} | `{sig.replace('|', '/')}` |")
    out.append("")

    out.append("## 5. 分类证据(代表性堆栈)\n")
    for cat, evs in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        rep = max(evs, key=lambda e: len(e["block"]))  # 优先展示最完整的堆栈
        out.append(f"### {cat} （共 {len(evs)} 次，首次出现于第 {rep['lineno']} 行）\n")
        out.append("```")
        out.extend(rep["block"][:18])
        if len(rep["block"]) > 18:
            out.append(f"... (省略 {len(rep['block']) - 18} 行)")
        out.append("```\n")

    out.append("## 6. 结论与下一步\n")
    top_cat = cat_counter.most_common(1)[0][0] if cat_counter else "-"
    out.append(f"- 主要矛盾是 **{top_cat}**，占全部事件的 "
               f"{(cat_counter[top_cat] / total * 100):.1f}%，应优先处置。")
    for cat, _ in cat_counter.most_common(3):
        out.append(f"- **{cat}**：{ADVICE.get(cat, '')}")
    out.append("- 建议为上述高频异常签名配置监控告警，并在修复后回归验证日志中不再复现。\n")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="日志诊断器：提取异常 -> 分类 -> Markdown 报告")
    ap.add_argument("logfile", help="原始日志文件路径")
    ap.add_argument("-o", "--output", default="report/log-report.md", help="报告输出路径")
    ap.add_argument("--top", type=int, default=5, help="高频签名展示数量")
    args = ap.parse_args()

    path = Path(args.logfile)
    if not path.exists():
        sys.exit(f"[错误] 找不到日志文件: {path}")

    with path.open("r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    events = extract_events(lines)
    report = build_report(path, events, len(lines), args.top)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")

    print(f"[完成] 共 {len(lines)} 行，提取事件 {len(events)} 个")
    print(f"[输出] 报告已写入: {out_path.resolve()}")


if __name__ == "__main__":
    main()
