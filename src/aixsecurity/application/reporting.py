"""Deterministic Markdown presentation of stored review results; no new verdicts."""
def render_markdown(report):
    summary=report.get('summary',{})
    lines=['# AIxSecurity Java 审计报告','',
        f"资产版本：`{report.get('snapshot_id','')}`",f"计划：`{report.get('plan','')}`",
        f"覆盖状态：{report.get('coverage','unknown')}",'',
        f"候选总数：{summary.get('candidate_count',0)}；尝试调查：{summary.get('attempted',0)}；完成复核：{summary.get('reviewed',0)}。",'',
        '## 固定代码版本']
    for repo in report.get('repositories',[]):
        lines.append(f"- {repo.get('url','')} @ `{repo.get('commit','')}`")
    lines.extend(['','## 发现与待确认项'])
    for index,item in enumerate(report.get('findings',[]),1):
        lines.extend(['',f"### {index}. {item.get('status','suspicious')}",
            f"仓库：{item.get('repository_url','未提供')} @ `{item.get('commit','')}`",
            f"位置：`{item.get('path','')}:{item.get('line','')}`",f"证据层级：{item.get('verification_method','unreviewed')}",
            '',item.get('reason','未提供理由')])
    lines.extend(['','## 局限与未覆盖范围'])
    lines.extend('- '+str(value) for value in report.get('limitations',[]))
    lines.extend(['','本报告不包含动态利用证明；待确认项不能当作已确认漏洞。',''])
    return '\n'.join(lines)
