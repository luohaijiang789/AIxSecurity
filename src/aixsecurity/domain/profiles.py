"""Supported, versioned Java scan profiles; no adapters or network dependencies."""
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class ScanProfile:
    id: str
    title: str
    description: str
    capability: str
    category: str
    review_focus: str


_PROFILES = (
    ScanProfile('sqli-intraprocedural-v1', 'SQL 注入', '请求输入进入 SQL 文本；Java 单函数污点分析。',
        'java-sqli-intraprocedural', 'sqli',
        'Check attacker control, SQL structure, execution, and effective parameter binding. Binding values does not protect SQL identifiers.'),
    ScanProfile('command-injection-intraprocedural-v1', '命令注入', '请求输入进入进程执行边界；检查命令与参数语义。',
        'java-command-injection-intraprocedural', 'command-injection',
        'Check attacker-controlled executable, shell interpretation versus direct argument passing, reachable process execution and allowlists. Runtime.exec is not automatically a shell; user-controlled arguments alone do not prove shell injection.'),
    ScanProfile('path-traversal-intraprocedural-v1', '路径穿越', '请求输入进入文件访问路径；检查目录边界。',
        'java-path-traversal-intraprocedural', 'path-traversal',
        'Check attacker-controlled path, actual file access, trusted base containment after normalization/canonicalization, allowlists, and symlink uncertainty. Path construction alone is not proof of file access. Normalization alone is not containment.'),
)
DEFAULT_PROFILE = _PROFILES[0].id


def get_profile(profile_id=DEFAULT_PROFILE):
    for profile in _PROFILES:
        if profile.id == profile_id:
            return profile
    raise ValueError('Unknown scan profile')


def list_profiles():
    return [{k:v for k,v in asdict(p).items() if k != 'review_focus'} for p in _PROFILES]


def candidate_category(candidate):
    # Legacy SQLi snapshots predate the category field; infer only known rule IDs.
    rule = candidate.get('rule_id', '')
    for profile in _PROFILES:
        if rule.endswith('aix.java.' + profile.category + '.taint'):
            supplied = candidate.get('category', profile.category)
            return profile.category if supplied == profile.category else None
    return None
