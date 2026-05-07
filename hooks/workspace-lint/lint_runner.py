#!/usr/bin/env python3
"""workspace-lint runner.

Phase 2 + 2.5：8 条 lint 全部实现

  1. l4_hc_consistency           — L4-HC-* ID 引用 vs 权威表
  2. skill_routing               — root CLAUDE.md 提到的 skill 是否存在
  3. broken_links                — markdown 链接路径 exists 检查
  4. doc_health                  — sha256 内容重复检测
  5. inventory_structure         — skill/agent 重名 + frontmatter 缺字段
  6. subproject_coverage_matrix  — 5 子项目两两组合是否有 cross 兜底
  7. orphan_candidates           — N 天 0 触发 + 没人提到（候选标记）
  8. drift_candidates            — 业务路径 mtime > CLAUDE.md mtime 候选

输出：JSON 到 stdout
退出码：0 = runner 自身正常；非 0 = runner 异常
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# ============================================================
# 数据结构
# ============================================================
@dataclass(frozen=True)
class MarkdownDoc:
    path: Path
    rel_path: str
    text: str
    lines: tuple[str, ...]
    text_without_fenced_code: str


@dataclass(frozen=True)
class InventoryItem:
    name: str
    kind: str           # "skill" | "agent"
    scope: str          # "project" | "user"
    path: Path
    enabled: bool


@dataclass
class Inventory:
    skills: dict[str, list[InventoryItem]] = field(default_factory=dict)
    agents: dict[str, list[InventoryItem]] = field(default_factory=dict)


# ============================================================
# Helpers
# ============================================================
def strip_fenced_code(text: str) -> str:
    """去掉 ``` ... ``` 围栏代码块，保留行结构（用空行替换以保留行号映射）"""
    out_lines = []
    in_fence = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out_lines.append("")
            continue
        if in_fence:
            out_lines.append("")
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def collect_target_markdown(
    workspace_root: Path,
    *,
    include_agents: bool = False,
    include_skill_references: bool = False,
) -> list[MarkdownDoc]:
    """枚举目标 markdown 文件：
    - root + 各级 CLAUDE.md（最多 4 层）
    - .claude/docs/**/*.md
    - .claude/skills/*/SKILL.md
    - 可选：.claude/agents/**/*.md
    """
    paths: list[Path] = []

    # CLAUDE.md（最多 4 层）
    for depth in range(0, 4):
        pattern = "/".join(["*"] * depth) + ("/" if depth else "") + "CLAUDE.md"
        for p in workspace_root.glob(pattern if pattern else "CLAUDE.md"):
            if p.is_file():
                paths.append(p)

    docs_dir = workspace_root / ".claude" / "docs"
    if docs_dir.is_dir():
        paths.extend([p for p in docs_dir.rglob("*.md") if p.is_file()])

    skills_dir = workspace_root / ".claude" / "skills"
    if skills_dir.is_dir():
        # 排除 .disabled/
        for skill_dir in skills_dir.iterdir():
            if skill_dir.name.startswith("."):
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.is_file():
                paths.append(skill_md)
        if include_skill_references:
            for skill_dir in skills_dir.iterdir():
                if skill_dir.name.startswith("."):
                    continue
                ref_dir = skill_dir / "reference"
                if ref_dir.is_dir():
                    paths.extend([p for p in ref_dir.rglob("*.md") if p.is_file()])

    if include_agents:
        agents_dir = workspace_root / ".claude" / "agents"
        if agents_dir.is_dir():
            for p in agents_dir.iterdir():
                if p.is_file() and p.suffix == ".md" and not p.name.startswith("."):
                    paths.append(p)

    docs: list[MarkdownDoc] = []
    seen: set[Path] = set()
    for p in paths:
        try:
            real = p.resolve()
        except OSError:
            continue
        if real in seen:
            continue
        seen.add(real)
        try:
            text = real.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            rel = str(real.relative_to(workspace_root))
        except ValueError:
            rel = str(real)
        docs.append(MarkdownDoc(
            path=real,
            rel_path=rel,
            text=text,
            lines=tuple(text.split("\n")),
            text_without_fenced_code=strip_fenced_code(text),
        ))
    return docs


def collect_inventory(
    workspace_root: Path,
    *,
    user_claude_dir: Path | None = None,
    include_disabled: bool = False,
) -> Inventory:
    """收集 user/project skills + agents 清单"""
    user_dir = user_claude_dir if user_claude_dir is not None else (Path.home() / ".claude")
    inv = Inventory()

    def add(items: dict[str, list[InventoryItem]], item: InventoryItem) -> None:
        items.setdefault(item.name, []).append(item)

    for scope, base in (("user", user_dir), ("project", workspace_root / ".claude")):
        skills_root = base / "skills"
        if skills_root.is_dir():
            for d in skills_root.iterdir():
                if d.name.startswith("."):
                    continue
                if (d / "SKILL.md").is_file():
                    add(inv.skills, InventoryItem(d.name, "skill", scope, d, True))
            disabled = skills_root / ".disabled"
            if include_disabled and disabled.is_dir():
                for d in disabled.iterdir():
                    if (d / "SKILL.md").is_file():
                        add(inv.skills, InventoryItem(d.name, "skill", scope, d, False))

        agents_root = base / "agents"
        if agents_root.is_dir():
            for f in agents_root.iterdir():
                if f.is_file() and f.suffix == ".md" and not f.name.startswith("."):
                    add(inv.agents, InventoryItem(f.stem, "agent", scope, f, True))
            disabled = agents_root / ".disabled"
            if include_disabled and disabled.is_dir():
                for f in disabled.iterdir():
                    if f.is_file() and f.suffix == ".md":
                        add(inv.agents, InventoryItem(f.stem, "agent", scope, f, False))

    return inv


# ============================================================
# Lint #1: l4_hc_consistency
# ============================================================
L4_HC_PATTERN = re.compile(r"L4-HC-[A-Z0-9-]+")


def extract_l4_hc_authority(workspace_root: Path) -> set[str]:
    """从 services/live4_go_talk/CLAUDE.md 抽 L4-HC-* 权威表

    限定只扫"硬约束清单"段落（## 标题之后到下一个 ## 之前），避免误把别处提到的
    L4-HC-* 当成权威 ID。
    """
    md = workspace_root / "services" / "live4_go_talk" / "CLAUDE.md"
    if not md.is_file():
        return set()
    try:
        text = md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()

    # 定位 "硬约束清单" 段落
    in_authority_section = False
    section_lines: list[str] = []
    for line in text.split("\n"):
        if line.startswith("## "):
            if "硬约束" in line or "硬规则" in line:
                in_authority_section = True
                continue
            elif in_authority_section:
                # 进入下一个 ## 段落，结束抽取
                break
        if in_authority_section:
            section_lines.append(line)

    section_text = "\n".join(section_lines)
    if not section_text.strip():
        # 段落定位失败 fallback：扫全文（保留原行为，避免空 authority 让 lint skip）
        section_text = text

    ids = set()
    for m in re.finditer(r"`(L4-HC-[A-Z0-9-]+)`", section_text):
        ids.add(m.group(1))
    return ids


def check_l4_hc_consistency(workspace_root: Path) -> dict:
    authority = extract_l4_hc_authority(workspace_root)
    issues: list[dict] = []
    if not authority:
        return {
            "id": "l4_hc_consistency",
            "name": "L4-HC-* ID 一致性",
            "status": "skip",
            "issues": [{"message": "权威表未找到（services/live4_go_talk/CLAUDE.md 不存在或无 L4-HC-* ID）"}],
        }
    docs = collect_target_markdown(workspace_root)
    for doc in docs:
        text_no_code = doc.text_without_fenced_code
        for line_no, line in enumerate(text_no_code.split("\n"), 1):
            for m in L4_HC_PATTERN.finditer(line):
                ref = m.group(0)
                if ref not in authority:
                    issues.append({
                        "file": doc.rel_path,
                        "line": line_no,
                        "message": f"引用了未在权威表中的 ID: {ref}",
                        "ref": ref,
                    })
    status = "fail" if issues else "pass"
    return {
        "id": "l4_hc_consistency",
        "name": "L4-HC-* ID 一致性",
        "status": status,
        "issues": issues,
        "authority_count": len(authority),
    }


# ============================================================
# Lint #2: skill_routing
# ============================================================
SKILL_NAME_PATTERN = re.compile(r"`([a-z0-9][a-z0-9-]+)`")
TRIGGER_VERB_PATTERN = re.compile(r"触发\s*`?([a-z0-9][a-z0-9-]+)`?\s*skill", re.IGNORECASE)
SHELL_TOKEN_BLACKLIST = {"make", "live3-rsync", "node_modules", "claude"}


def extract_root_skill_references(workspace_root: Path) -> set[str]:
    """只从 root CLAUDE.md 明确上下文抽 skill 名"""
    root_md = workspace_root / "CLAUDE.md"
    if not root_md.is_file():
        return set()
    try:
        text = root_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    text_no_code = strip_fenced_code(text)
    refs: set[str] = set()

    # 1) "触发 xxx skill" / "触发 `xxx` skill" 句式
    for m in TRIGGER_VERB_PATTERN.finditer(text_no_code):
        refs.add(m.group(1))

    # 2) Bug 分流矩阵：表格行末尾的 `xxx-bug-triage` / `xxx-sync` 之类
    #    保守做法：扫表格行 `| ... | \`name\` |` 形态
    for line in text_no_code.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        # 表格行里取最后一个 backtick token
        for m in SKILL_NAME_PATTERN.finditer(line):
            name = m.group(1)
            # 过滤明显不是 skill 名的 backtick（路径、shell 命令）
            if "/" in name or "." in name:
                continue
            if name in SHELL_TOKEN_BLACKLIST:
                continue
            # 至少含连字符（skill 命名约定都带 -）
            if "-" not in name:
                continue
            refs.add(name)

    # 3) "对应 `xxx-skill` skill" 简单变体
    for m in re.finditer(r"对应\s*`([a-z0-9][a-z0-9-]+)`\s*skill", text_no_code):
        refs.add(m.group(1))

    return refs


def check_skill_routing(workspace_root: Path) -> dict:
    refs = extract_root_skill_references(workspace_root)
    inv = collect_inventory(workspace_root, include_disabled=False)
    available = set(inv.skills.keys())
    issues: list[dict] = []
    for ref in sorted(refs):
        if ref not in available:
            issues.append({
                "skill_ref": ref,
                "message": f"root CLAUDE.md 提到 skill '{ref}' 但 .claude/skills/ 下不存在（或已 disabled）",
            })
    status = "fail" if issues else "pass"
    return {
        "id": "skill_routing",
        "name": "skill 路由完整性",
        "status": status,
        "issues": issues,
        "refs_count": len(refs),
        "available_count": len(available),
    }


# ============================================================
# Lint #3: broken_links
# ============================================================
MD_LINK_PATTERN = re.compile(r"(?<!\!)\[([^\]]*)\]\(([^)]+)\)")
RAW_DOC_REF_PATTERN = re.compile(r"\.claude/docs/[^\s)`'\"<>]+\.md")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "ftp://", "tel:", "data:")


def resolve_link_target(target: str, source_file: Path, workspace_root: Path) -> Path | None:
    target = target.strip()
    if not target or target.startswith("#"):
        return None
    if target.startswith(EXTERNAL_PREFIXES):
        return None
    # 去掉 #anchor 和 ?query
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return None
    target = urllib.parse.unquote(target)
    if target.startswith(".claude/") or target.startswith("/.claude/"):
        return (workspace_root / target.lstrip("/")).resolve()
    if target.startswith("/"):
        return Path(target)
    return (source_file.parent / target).resolve()


def check_broken_links(workspace_root: Path) -> dict:
    docs = collect_target_markdown(workspace_root)
    issues: list[dict] = []
    for doc in docs:
        text_no_code = doc.text_without_fenced_code
        # markdown link
        for line_no, line in enumerate(text_no_code.split("\n"), 1):
            for m in MD_LINK_PATTERN.finditer(line):
                target = m.group(2)
                resolved = resolve_link_target(target, doc.path, workspace_root)
                if resolved is None:
                    continue
                if not resolved.exists():
                    issues.append({
                        "file": doc.rel_path,
                        "line": line_no,
                        "target": target,
                        "message": f"链接指向不存在的路径: {target}",
                    })
        # raw .claude/docs/...md 引用
        # 注意：先去掉行内 backtick `xxx` 包裹的内容，避免示例代码里的不存在路径误报
        for line_no, line in enumerate(text_no_code.split("\n"), 1):
            line_no_inline = re.sub(r"`[^`]+`", "", line)
            for m in RAW_DOC_REF_PATTERN.finditer(line_no_inline):
                target = m.group(0)
                # 跳过 glob 通配符（不是真实路径，是模式表达）
                if any(c in target for c in "*?["):
                    continue
                resolved = (workspace_root / target).resolve()
                if not resolved.exists():
                    # 去重：和 markdown link 重叠的情况手动检查
                    dup = any(
                        i.get("file") == doc.rel_path
                        and i.get("line") == line_no
                        and target in (i.get("target") or "")
                        for i in issues
                    )
                    if not dup:
                        issues.append({
                            "file": doc.rel_path,
                            "line": line_no,
                            "target": target,
                            "message": f"引用了不存在的 docs 路径: {target}",
                        })
    status = "fail" if issues else "pass"
    return {
        "id": "broken_links",
        "name": "断链检测",
        "status": status,
        "issues": issues,
        "scanned_files": len(docs),
    }


# ============================================================
# Lint #4: doc_health (sha256 重复)
# ============================================================
def check_doc_health(workspace_root: Path) -> dict:
    docs = collect_target_markdown(workspace_root, include_agents=True)
    by_hash: dict[str, list[MarkdownDoc]] = {}
    for doc in docs:
        try:
            data = doc.path.read_bytes()
        except OSError:
            continue
        if not data.strip():
            continue  # 空文件跳过
        h = hashlib.sha256(data).hexdigest()
        by_hash.setdefault(h, []).append(doc)

    issues: list[dict] = []
    for h, group in by_hash.items():
        if len(group) >= 2:
            files = sorted(d.rel_path for d in group)
            size = group[0].path.stat().st_size if group[0].path.exists() else 0
            issues.append({
                "hash": h,
                "files": files,
                "size_bytes": size,
                "message": f"{len(group)} 个文件内容完全相同",
            })
    status = "warn" if issues else "pass"
    return {
        "id": "doc_health",
        "name": "文档健康（sha256 重复）",
        "status": status,
        "issues": issues,
        "scanned_files": len(docs),
    }


# ============================================================
# Lint #5: inventory_structure
# ============================================================
SUBPROJECT_NAMES = {"live3_app", "live4_go_talk", "live3_svr_api", "live3_svr_admin"}


def _parse_frontmatter(text: str) -> dict | None:
    """简单 YAML frontmatter 解析：取 --- 之间的 key: value 行"""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    fm_lines = text[3:end].strip().split("\n")
    out = {}
    for line in fm_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip("'\"")
    return out


def _check_skill_md(path: Path) -> list[str]:
    """检查 SKILL.md frontmatter 缺字段，返回 missing field 列表"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ["read_failed"]
    fm = _parse_frontmatter(text)
    if fm is None:
        return ["no_frontmatter"]
    missing = []
    for k in ("name", "description"):
        if not fm.get(k):
            missing.append(f"missing:{k}")
    return missing


def check_inventory_structure(workspace_root: Path) -> dict:
    issues = []
    user_claude = Path.home() / ".claude"
    project_claude = workspace_root / ".claude"

    # 1. user/project 同名 skill 重名检测
    user_skills = set()
    if (user_claude / "skills").is_dir():
        for d in (user_claude / "skills").iterdir():
            if d.is_dir() and not d.name.startswith(".") and (d / "SKILL.md").is_file():
                user_skills.add(d.name)
    project_skills = set()
    if (project_claude / "skills").is_dir():
        for d in (project_claude / "skills").iterdir():
            if d.is_dir() and not d.name.startswith(".") and (d / "SKILL.md").is_file():
                project_skills.add(d.name)
    overlap = user_skills & project_skills
    for name in sorted(overlap):
        issues.append({
            "type": "skill_name_overlap",
            "name": name,
            "message": f"skill '{name}' 同时在 user 和 project 存在，project 会覆盖 user",
        })

    # 2. 同样检查 agents
    user_agents = set()
    if (user_claude / "agents").is_dir():
        for f in (user_claude / "agents").iterdir():
            if f.is_file() and f.suffix == ".md" and not f.name.startswith("."):
                user_agents.add(f.stem)
    project_agents = set()
    if (project_claude / "agents").is_dir():
        for f in (project_claude / "agents").iterdir():
            if f.is_file() and f.suffix == ".md" and not f.name.startswith("."):
                project_agents.add(f.stem)
    overlap_agents = user_agents & project_agents
    for name in sorted(overlap_agents):
        issues.append({
            "type": "agent_name_overlap",
            "name": name,
            "message": f"agent '{name}' 同时在 user 和 project 存在",
        })

    # 3. SKILL.md frontmatter 缺字段
    for base, scope in ((user_claude / "skills", "user"), (project_claude / "skills", "project")):
        if not base.is_dir():
            continue
        for d in base.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue
            skill_md = d / "SKILL.md"
            if not skill_md.is_file():
                continue
            missing = _check_skill_md(skill_md)
            for m in missing:
                issues.append({
                    "type": "skill_frontmatter",
                    "scope": scope,
                    "name": d.name,
                    "file": str(skill_md.relative_to(workspace_root) if str(skill_md).startswith(str(workspace_root))
                                  else skill_md),
                    "issue": m,
                    "message": f"{scope}/{d.name}/SKILL.md frontmatter {m}",
                })

    status = "warn" if issues else "pass"
    return {
        "id": "inventory_structure",
        "name": "库存结构审计",
        "status": status,
        "issues": issues,
        "user_skills": len(user_skills),
        "project_skills": len(project_skills),
    }


# ============================================================
# Lint #6: subproject_coverage_matrix
# ============================================================
SUBPROJECT_PAIRS = [
    ("live3_app", "live4_go_talk"),
    ("live3_app", "live3_svr_api"),
    ("live3_app", "live3_svr_admin"),
    ("live4_go_talk", "live3_svr_api"),
    ("live4_go_talk", "live3_svr_admin"),
    ("live3_svr_api", "live3_svr_admin"),
]

# 子项目名 → hyphenated（_ 替换为 -）用于匹配 skill 命名约定
# live3_app → live3-app，live3_svr_api → live3-svr-api，等
def _hyphenate(name: str) -> str:
    return name.replace("_", "-")


# cross 文档命名的 short 别名（仅 cross 文档有这种短名传统）
# 实际命名：cross-live3-live4.md / cross-admin-live4.md
_CROSS_SHORT = {
    "live3_app": "live3",
    "live4_go_talk": "live4",
    "live3_svr_api": "svr-api",
    "live3_svr_admin": "admin",
}


def _find_pair_coverage(workspace_root: Path, a: str, b: str) -> dict:
    """检查一对子项目是否有 cross 文档 / triage skill / sync skill 兜底

    精确匹配 skill 全名（不用 substring/in）。
    """
    cross_dir = workspace_root / ".claude" / "docs"
    skills_dir = workspace_root / ".claude" / "skills"

    # cross 文档：cross-{a}-{b}.md（含 short 别名变体）
    cross_files = []
    a_variants = {a, _CROSS_SHORT.get(a, a), _hyphenate(a)}
    b_variants = {b, _CROSS_SHORT.get(b, b), _hyphenate(b)}
    if cross_dir.is_dir():
        candidates = set()
        for av in a_variants:
            for bv in b_variants:
                candidates.add(f"cross-{av}-{bv}.md")
                candidates.add(f"cross-{bv}-{av}.md")
        for fname in sorted(candidates):
            p = cross_dir / fname
            if p.is_file():
                cross_files.append(str(p.relative_to(workspace_root)))

    # triage / sync skill：精确匹配 {a-hyphen}-{b-hyphen}-bug-triage 等
    a_h = _hyphenate(a)
    b_h = _hyphenate(b)
    expected_triage = {
        f"{a_h}-{b_h}-bug-triage",
        f"{b_h}-{a_h}-bug-triage",
        # admin 用 sync 不用 triage
        f"{a_h}-{b_h}-sync",
        f"{b_h}-{a_h}-sync",
    }
    expected_sync = {
        f"{a_h}-{b_h}-sync",
        f"{b_h}-{a_h}-sync",
        f"{a_h}-{b_h}-realtime-sync",
        f"{b_h}-{a_h}-realtime-sync",
        f"{a_h}-{b_h}-contract-sync",
        f"{b_h}-{a_h}-contract-sync",
    }

    triage_skills = []
    sync_skills = []
    if skills_dir.is_dir():
        for d in skills_dir.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue
            n = d.name
            if n in expected_triage:
                triage_skills.append(n)
            if n in expected_sync:
                sync_skills.append(n)

    return {
        "cross_docs": cross_files,
        "triage_skills": list(set(triage_skills)),
        "sync_skills": list(set(sync_skills)),
        "has_coverage": bool(cross_files or triage_skills or sync_skills),
    }


def check_subproject_coverage_matrix(workspace_root: Path) -> dict:
    issues = []
    matrix = []
    for a, b in SUBPROJECT_PAIRS:
        cov = _find_pair_coverage(workspace_root, a, b)
        cell = {"a": a, "b": b, **cov}
        matrix.append(cell)
        if not cov["has_coverage"]:
            issues.append({
                "pair": f"{a} ↔ {b}",
                "message": f"无 cross 文档 / triage / sync skill 兜底",
            })
    status = "warn" if issues else "pass"
    return {
        "id": "subproject_coverage_matrix",
        "name": "跨子项目覆盖矩阵",
        "status": status,
        "issues": issues,
        "matrix": matrix,
        "total_pairs": len(SUBPROJECT_PAIRS),
        "covered_pairs": len(SUBPROJECT_PAIRS) - len(issues),
    }


# ============================================================
# Lint #7: orphan_candidates
# ============================================================
ORPHAN_WINDOW_DAYS = 60
ORPHAN_TOO_NEW_DAYS = 7


def _events_db_path() -> Path:
    return Path(os.environ.get(
        "LINT_EVENTS_DB",
        os.path.expanduser("~/Desktop/ai-project/data/events.db"),
    ))


def _collect_claude_md_text(workspace_root: Path) -> str:
    """读所有 CLAUDE.md + .claude/docs/ 内容拼起来用于子串检索"""
    chunks = []
    for p in workspace_root.glob("CLAUDE.md"):
        try:
            chunks.append(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            pass
    for depth in range(1, 4):
        pattern = "/".join(["*"] * depth) + "/CLAUDE.md"
        for p in workspace_root.glob(pattern):
            try:
                chunks.append(p.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                pass
    docs = workspace_root / ".claude" / "docs"
    if docs.is_dir():
        for p in docs.rglob("*.md"):
            try:
                chunks.append(p.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                pass
    return "\n".join(chunks)


def check_orphan_candidates(workspace_root: Path) -> dict:
    db_path = _events_db_path()
    if not db_path.is_file():
        return {
            "id": "orphan_candidates",
            "name": "孤儿候选",
            "status": "skip",
            "issues": [{"message": f"events.db 不存在: {db_path}"}],
        }

    inv = collect_inventory(workspace_root, include_disabled=False)
    md_text = _collect_claude_md_text(workspace_root)

    # 查 events.db：N 天内有触发的 skill/agent 名集合
    import sqlite3
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=ORPHAN_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    too_new_cutoff = (datetime.now(timezone.utc) - timedelta(days=ORPHAN_TOO_NEW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    triggered = set()
    try:
        conn = sqlite3.connect(str(db_path))
        for (name,) in conn.execute(
            "SELECT DISTINCT name FROM events WHERE ts >= ? AND name IS NOT NULL",
            (cutoff,),
        ):
            triggered.add(name)
        conn.close()
    except Exception:
        return {
            "id": "orphan_candidates",
            "name": "孤儿候选",
            "status": "skip",
            "issues": [{"message": "events.db 查询失败"}],
        }

    issues = []
    candidates_count = 0
    for kind, items_dict in (("skill", inv.skills), ("agent", inv.agents)):
        for name, items in items_dict.items():
            # 双条件：N 天 0 触发 + 名字未在任何 CLAUDE.md / docs 提到
            if name in triggered:
                continue
            if name in md_text:
                continue
            # 检查 too_new
            try:
                mtime = max(it.path.stat().st_mtime for it in items)
                from datetime import datetime as _dt, timezone as _tz
                mtime_iso = _dt.fromtimestamp(mtime, _tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                if mtime_iso >= too_new_cutoff:
                    continue  # too_new_to_judge，跳过
            except OSError:
                pass
            scope = items[0].scope
            candidates_count += 1
            issues.append({
                "kind": kind,
                "name": name,
                "scope": scope,
                "message": f"{kind} '{name}' ({scope}) {ORPHAN_WINDOW_DAYS} 天 0 触发 + CLAUDE.md/docs 未提到",
            })

    status = "warn" if issues else "pass"
    return {
        "id": "orphan_candidates",
        "name": "孤儿候选",
        "status": status,
        "issues": issues,
        "window_days": ORPHAN_WINDOW_DAYS,
        "candidates": candidates_count,
    }


# ============================================================
# Lint #8: drift_candidates
# ============================================================
DRIFT_WINDOW_DAYS = 30


def check_drift_candidates(workspace_root: Path) -> dict:
    """业务路径 mtime vs 子项目 CLAUDE.md mtime
    弱条件：业务文件最近 N 天有改动 + 子项目 CLAUDE.md 最近 N 天没改 → drift candidate
    每子项目独立 git -C 跑（root 不是 git repo）
    """
    import subprocess
    import time

    issues = []
    now_ts = time.time()
    drift_cutoff = now_ts - DRIFT_WINDOW_DAYS * 86400

    subprojects = {
        "live3_app": "clients/live3_app",
        "live4_go_talk": "services/live4_go_talk",
        "live3_svr_api": "services/live3_svr_api",
        "live3_svr_admin": "admin/live3_svr_admin",
    }

    for sub_name, rel_path in subprojects.items():
        sub_dir = workspace_root / rel_path
        claude_md = sub_dir / "CLAUDE.md"
        if not sub_dir.is_dir() or not claude_md.is_file():
            continue
        try:
            claude_mtime = claude_md.stat().st_mtime
        except OSError:
            continue

        # 子项目 CLAUDE.md 最近 N 天有改 → 不算 drift
        if claude_mtime >= drift_cutoff:
            continue

        # 用 git -C 看子项目最近修改的业务文件
        try:
            result = subprocess.run(
                ["git", "-C", str(sub_dir), "log", "--since",
                 f"{DRIFT_WINDOW_DAYS}.days.ago", "--pretty=format:%H", "-1"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                continue  # 不是 git repo 或异常
            recent_commit = result.stdout.strip()
            if not recent_commit:
                continue  # N 天内无 commit
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

        # 业务有改 + CLAUDE.md 没改 → 候选
        from datetime import datetime as _dt, timezone as _tz
        claude_mtime_iso = _dt.fromtimestamp(claude_mtime, _tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        issues.append({
            "subproject": sub_name,
            "claude_md_last_modified": claude_mtime_iso,
            "message": f"{sub_name} 业务代码近 {DRIFT_WINDOW_DAYS} 天有 commit，CLAUDE.md 近 {DRIFT_WINDOW_DAYS} 天未更新（可能漂移）",
        })

    status = "warn" if issues else "pass"
    return {
        "id": "drift_candidates",
        "name": "配置漂移候选",
        "status": status,
        "issues": issues,
        "window_days": DRIFT_WINDOW_DAYS,
    }


# ============================================================
# Main
# ============================================================
def main() -> int:
    if os.environ.get("WORKSPACE_LINT_FORCE_RUNNER_FAIL") == "1":
        print("forced runner failure", file=sys.stderr)
        return 1

    workspace_root = Path(os.environ.get(
        "LIVE_APP_PATH",
        "/Users/augus/Desktop/开发项目/live_app",
    ))

    if not workspace_root.is_dir():
        sys.stdout.write(json.dumps({
            "version": 1,
            "summary": {"total": 0, "passed": 0, "failed": 0},
            "checks": [],
            "error": {"message": f"workspace_root not found: {workspace_root}"},
        }))
        return 1

    checks: list[dict] = [
        check_l4_hc_consistency(workspace_root),
        check_skill_routing(workspace_root),
        check_broken_links(workspace_root),
        check_doc_health(workspace_root),
        check_inventory_structure(workspace_root),
        check_subproject_coverage_matrix(workspace_root),
        check_orphan_candidates(workspace_root),
        check_drift_candidates(workspace_root),
    ]

    total = len(checks)
    passed = sum(1 for c in checks if c["status"] == "pass")
    failed = sum(1 for c in checks if c["status"] == "fail")

    payload = {
        "version": 1,
        "summary": {"total": total, "passed": passed, "failed": failed},
        "checks": checks,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
