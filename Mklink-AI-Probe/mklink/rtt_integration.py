"""
MKLink Serial Bridge — RTT 源码集成工具。

零外部依赖（仅 stdlib pathlib/shutil），零内部依赖。
检查项目中是否已集成 RTT，按需复制打包的 SEGGER RTT 源文件。
自动将 RTT 文件添加到 Keil 工程并插入初始化代码。
"""

from __future__ import annotations

import re
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional


_RTT_SRC_FILES = ["SEGGER_RTT.c", "SEGGER_RTT_printf.c", "rtt_heartbeat_template.c"]
_RTT_INC_FILES = ["SEGGER_RTT.h", "SEGGER_RTT_Conf.h"]
# 复制到项目时 rtt_heartbeat_template.c 重命名为 rtt_heartbeat.c
_RTT_HEARTBEAT_SRC = "rtt_heartbeat_template.c"
_RTT_HEARTBEAT_DST = "rtt_heartbeat.c"
_ALL_RTT_FILES = _RTT_SRC_FILES + _RTT_INC_FILES


def get_bundled_rtt_dir() -> Path:
    """返回技能打包的 rtt_sources/ 目录路径。"""
    return Path(__file__).parent / "rtt_sources"


def check_rtt_sources_bundled() -> bool:
    """验证 rtt_sources/ 下所有必需文件存在。"""
    d = get_bundled_rtt_dir()
    return all((d / f).exists() for f in _ALL_RTT_FILES)


def check_rtt_in_project(src_dir: str, inc_dir: str) -> dict:
    """检查项目中是否已有 RTT 源文件。

    Returns:
        {"integrated": bool, "found_src": [...], "found_inc": [...],
         "missing_src": [...], "missing_inc": [...]}
    """
    src = Path(src_dir)
    inc = Path(inc_dir)

    found_src = [f for f in _RTT_SRC_FILES if (src / f).exists()]
    found_inc = [f for f in _RTT_INC_FILES if (inc / f).exists()]
    missing_src = [f for f in _RTT_SRC_FILES if f not in found_src]
    missing_inc = [f for f in _RTT_INC_FILES if f not in found_inc]

    integrated = len(missing_src) == 0 and len(missing_inc) == 0

    return {
        "integrated": integrated,
        "found_src": found_src,
        "found_inc": found_inc,
        "missing_src": missing_src,
        "missing_inc": missing_inc,
    }


def integrate_rtt_sources(src_dir: str, inc_dir: str) -> dict:
    """将打包的 RTT 源文件复制到项目目录。

    不覆盖已有文件。

    Returns:
        {"success": bool, "copied": [...], "skipped": [...], "errors": [...]}
    """
    bundled = get_bundled_rtt_dir()
    if not check_rtt_sources_bundled():
        return {
            "success": False,
            "copied": [],
            "skipped": [],
            "errors": ["RTT 源文件未打包，请检查技能目录 rtt_sources/"],
        }

    src = Path(src_dir)
    inc = Path(inc_dir)
    src.mkdir(parents=True, exist_ok=True)
    inc.mkdir(parents=True, exist_ok=True)

    copied = []
    skipped = []
    errors = []

    for fname in _RTT_SRC_FILES:
        # rtt_heartbeat_template.c 复制时重命名为 rtt_heartbeat.c
        dst_name = _RTT_HEARTBEAT_DST if fname == _RTT_HEARTBEAT_SRC else fname
        dst = src / dst_name
        if dst.exists():
            skipped.append(str(dst))
            continue
        try:
            shutil.copy2(bundled / fname, dst)
            copied.append(str(dst))
        except OSError as e:
            errors.append(f"复制 {fname} 失败: {e}")

    for fname in _RTT_INC_FILES:
        dst = inc / fname
        if dst.exists():
            skipped.append(str(dst))
            continue
        try:
            shutil.copy2(bundled / fname, dst)
            copied.append(str(dst))
        except OSError as e:
            errors.append(f"复制 {fname} 失败: {e}")

    return {
        "success": len(errors) == 0,
        "copied": copied,
        "skipped": skipped,
        "errors": errors,
    }


def _backup_file(path: Path) -> Path:
    """备份文件到同目录的 .bak 文件。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_suffix(path.suffix + f".bak.{ts}")
    shutil.copy2(path, backup_path)
    return backup_path


def _get_indent(line: str) -> str:
    """获取行的前导空白。"""
    return line[:len(line) - len(line.lstrip())] if line.strip() else ""


def _is_already_guarded(new_lines: list[str]) -> bool:
    """检查当前位置是否已在 #ifdef USE_RTT 保护内。

    向上查找最近的预处理器指令：如果是 #ifdef USE_RTT 则已保护，
    如果是 #endif 或其他 #ifdef 则未保护。
    """
    for line in reversed(new_lines[-10:]):
        s = line.strip()
        if s == "":
            continue
        if s.startswith("#ifdef") and "USE_RTT" in s:
            return True
        if (s.startswith("#endif") or s.startswith("#ifdef") or
                s.startswith("#if ") or s.startswith("#ifndef")):
            return False
    return False


def _upgrade_rtt_guards(content: str) -> tuple[str, list[str]]:
    """将已有但未加宏保护的 RTT 代码升级为 #ifdef USE_RTT 保护。

    处理场景：
    1. #include "SEGGER_RTT.h" → 包裹 #ifdef USE_RTT / #endif
    2. 连续的 RTT 初始化块（注释 + Init + printf）→ 整块包裹
    3. 多行 SEGGER_RTT_printf 调用 → 整条语句包裹

    Returns:
        (修改后的内容, 变更说明列表)
    """
    # 已经升级过（SEGGER_RTT.h 被 USE_RTT 保护）
    if re.search(r"#ifdef\s+USE_RTT\s*\n\s*#include\s*[\"<]SEGGER_RTT\.h[\">]", content):
        return content, []

    if "SEGGER_RTT" not in content:
        return content, []

    lines = content.split("\n")
    new_lines: list[str] = []
    changes: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        is_rtt_include = bool(re.match(r'#include\s*["<]SEGGER_RTT\.h[">]', stripped))
        is_rtt_code = "SEGGER_RTT" in stripped and not stripped.startswith("#")

        if (is_rtt_include or is_rtt_code) and not _is_already_guarded(new_lines):
            indent = _get_indent(line)
            new_lines.append(f"{indent}#ifdef USE_RTT")

            # 收集连续的 RTT 相关行（含多行语句）
            while i < len(lines):
                s = lines[i].strip()
                if "SEGGER_RTT" in s:
                    new_lines.append(lines[i])
                    i += 1
                    continue
                # 多行续行：上一行以逗号结尾（语句未完成）
                if new_lines and new_lines[-1].rstrip().endswith(","):
                    new_lines.append(lines[i])
                    i += 1
                    continue
                break

            new_lines.append(f"{indent}#endif")
            changes.append("wrapped RTT code with USE_RTT guard")
            continue

        new_lines.append(line)
        i += 1

    return "\n".join(new_lines), changes


def add_rtt_to_iar_project(
    ewp_path: str,
    src_dir: str,
    inc_dir: str,
) -> dict:
    """将 RTT 源文件添加到 IAR 工程（.ewp）。

    IAR EWP 文件结构:
    - <file> 元素包含 <name>$PROJ_DIR$/path/to/file.c</name>

    自动备份原工程文件。

    Args:
        ewp_path: .ewp 文件路径
        src_dir: RTT 源文件目录（相对路径，相对于 ewp 所在目录）
        inc_dir: RTT 头文件目录（相对路径，相对于 ewp 所在目录）

    Returns:
        {"success": bool, "backup_path": str, "errors": [...]}
    """
    ewp = Path(ewp_path)
    if not ewp.exists():
        return {
            "success": False,
            "backup_path": "",
            "errors": [f"工程文件不存在: {ewp_path}"],
        }

    # 备份
    backup_path = _backup_file(ewp)
    errors = []

    try:
        tree = ET.parse(str(ewp))
        root = tree.getroot()
    except ET.ParseError as e:
        return {
            "success": False,
            "backup_path": str(backup_path),
            "errors": [f"XML 解析失败: {e}"],
        }

    if root.tag != "project":
        return {
            "success": False,
            "backup_path": str(backup_path),
            "errors": [f"无效的 EWP 文件，根节点应为 project，实际为 {root.tag}"],
        }

    # 检查是否已集成（查找是否已有 SEGGER_RTT 相关文件）
    for file_elem in root.findall("file"):
        name_elem = file_elem.find("name")
        if name_elem is not None and name_elem.text:
            if "SEGGER_RTT" in name_elem.text:
                return {
                    "success": True,
                    "backup_path": str(backup_path),
                    "errors": ["SEGGER_RTT 文件已存在于工程中，未做修改"],
                }

    # 计算相对路径（相对于 ewp 所在目录）
    base_dir = ewp.parent.resolve()
    src_abs = Path(src_dir).resolve() if not Path(src_dir).is_absolute() else Path(src_dir)
    inc_abs = Path(inc_dir).resolve() if not Path(inc_dir).is_absolute() else Path(inc_dir)

    # 转为相对于 ewp 目录的路径
    try:
        src_rel = src_abs.relative_to(base_dir)
        inc_rel = inc_abs.relative_to(base_dir)
    except ValueError:
        # 如果不在同一路径树下，使用绝对路径（但保持 $PROJ_DIR$ 前缀）
        src_rel = src_abs
        inc_rel = inc_abs

    # IAR 使用 $PROJ_DIR$ 前缀表示项目目录
    src_proj_dir = "$PROJ_DIR$/" + str(src_rel).replace("\\", "/")
    inc_proj_dir = "$PROJ_DIR$/" + str(inc_rel).replace("\\", "/")

    # 在 </project> 结束标签前添加 file 元素
    # IAR 的 file 元素直接在 project 下
    for fname in _RTT_SRC_FILES:
        file_elem = ET.Element("file")
        name_elem = ET.SubElement(file_elem, "name")
        name_elem.text = src_proj_dir + "/" + fname
        root.append(file_elem)

    for fname in _RTT_INC_FILES:
        file_elem = ET.Element("file")
        name_elem = ET.SubElement(file_elem, "name")
        name_elem.text = inc_proj_dir + "/" + fname
        root.append(file_elem)

    # 写回 XML
    tree.write(
        str(ewp),
        encoding="utf-8",
        xml_declaration=True,
    )

    return {
        "success": True,
        "backup_path": str(backup_path),
        "errors": errors,
    }


def add_rtt_to_keil_project(
    uvprojx_path: str,
    src_dir: str,
    inc_dir: str,
) -> dict:
    """将 RTT 源文件添加到 Keil 工程（.uvprojx）。

    自动备份原工程文件。

    Args:
        uvprojx_path: .uvprojx 文件路径
        src_dir: RTT 源文件目录（相对路径，相对于 uvprojx 所在目录）
        inc_dir: RTT 头文件目录（相对路径，相对于 uvprojx 所在目录）

    Returns:
        {"success": bool, "backup_path": str, "errors": [...]}
    """
    uvprojx = Path(uvprojx_path)
    if not uvprojx.exists():
        return {
            "success": False,
            "backup_path": "",
            "errors": [f"工程文件不存在: {uvprojx_path}"],
        }

    # 备份
    backup_path = _backup_file(uvprojx)
    errors = []

    try:
        tree = ET.parse(str(uvprojx))
        root = tree.getroot()
    except ET.ParseError as e:
        return {
            "success": False,
            "backup_path": str(backup_path),
            "errors": [f"XML 解析失败: {e}"],
        }

    # 注册命名空间（Keil uvprojx 使用自定义命名空间）
    ns = {"": ""}
    for elem in root.iter():
        if elem.tag.startswith("{"):
            ns["ns"] = elem.tag[1:elem.tag.index("}")]
            ET.register_namespace("", ns["ns"])
            break

    # 查找 Target 节点
    targets = root.findall(".//Target")
    if not targets:
        return {
            "success": False,
            "backup_path": str(backup_path),
            "errors": ["未找到 Target 节点"],
        }

    target = targets[0]
    base_dir = uvprojx.parent

    # 解析为相对于 uvprojx 目录的路径
    # src_dir/inc_dir 可能是绝对路径或相对于 project_root 的路径
    # 需要转转為相對於 uvprojx 所在目錄 (MDK-ARM) 的相對路徑
    src_abs = Path(src_dir).resolve() if not Path(src_dir).is_absolute() else Path(src_dir)
    inc_abs = Path(inc_dir).resolve() if not Path(inc_dir).is_absolute() else Path(inc_dir)

    # 计算相对于 uvprojx 父目录的相对路径
    parent_dir = base_dir.parent  # 项目根目录
    src_rel = Path(src_abs).relative_to(parent_dir)
    inc_rel = Path(inc_abs).relative_to(parent_dir)

    # 转换为 Windows 反斜杠路径格式
    src_rel_win = str(src_rel).replace("/", "\\")
    inc_rel_win = str(inc_rel).replace("/", "\\")

    # 查找 Groups 节点
    groups_node = target.find("Groups")
    if groups_node is None:
        groups_node = ET.SubElement(target, "Groups")

    # 检查是否已存在 SEGGER_RTT 分组
    for group in groups_node.findall("Group"):
        name_el = group.find("GroupName")
        if name_el is not None and name_el.text == "SEGGER_RTT":
            return {
                "success": True,
                "backup_path": str(backup_path),
                "errors": ["SEGGER_RTT 分组已存在，未做修改"],
            }

    # 创建新分组
    rtt_group = ET.SubElement(groups_node, "Group")
    ET.SubElement(rtt_group, "GroupName").text = "SEGGER_RTT"

    # 添加源文件（使用相对于 uvprojx 目录的路径）
    # 正确结构: <Files><File><FileName/><FileType/><FilePath/></File></Files>
    for fname in _RTT_SRC_FILES:
        files_el = ET.SubElement(rtt_group, "Files")
        file_el = ET.SubElement(files_el, "File")
        ET.SubElement(file_el, "FileName").text = fname
        ET.SubElement(file_el, "FileType").text = "1"  # C source
        ET.SubElement(file_el, "FilePath").text = str(Path("..") / src_rel_win / fname)

    # 添加头文件（FileType=5 为头文件）
    for fname in _RTT_INC_FILES:
        files_el = ET.SubElement(rtt_group, "Files")
        file_el = ET.SubElement(files_el, "File")
        ET.SubElement(file_el, "FileName").text = fname
        ET.SubElement(file_el, "FileType").text = "5"  # header file
        ET.SubElement(file_el, "FilePath").text = str(Path("..") / inc_rel_win / fname)

    # 写回 XML（保留格式）
    tree.write(
        str(uvprojx),
        encoding="utf-8",
        xml_declaration=True,
    )

    return {
        "success": True,
        "backup_path": str(backup_path),
        "errors": errors,
    }


def add_rtt_init_to_main(main_c_path: str) -> dict:
    """在 main.c 中添加 SEGGER_RTT 初始化代码（USE_RTT 宏保护）。

    1. 添加 #ifdef USE_RTT / #include "SEGGER_RTT.h" / #endif
    2. 在 System_Init() 之后添加 #ifdef USE_RTT / SEGGER_RTT_Init() / #endif

    Returns:
        {"success": bool, "backup_path": str, "added_include": bool,
         "added_init": bool, "warnings": [...], "errors": [...]}
    """
    main_path = Path(main_c_path)
    if not main_path.exists():
        return {
            "success": False,
            "backup_path": "",
            "added_include": False,
            "added_init": False,
            "warnings": [],
            "errors": [f"main.c 不存在: {main_c_path}"],
        }

    backup_path = _backup_file(main_path)
    errors = []
    warnings = []

    try:
        content = main_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = main_path.read_text(encoding="gbk")
        has_gbk = True
    else:
        has_gbk = False

    # 升级步骤：将已有但未加宏保护的 RTT 代码包裹 #ifdef USE_RTT
    if "SEGGER_RTT" in content and "#ifdef USE_RTT" not in content:
        content, upgrade_changes = _upgrade_rtt_guards(content)
        for change in upgrade_changes:
            warnings.append(f"已升级: {change}")

    lines = content.split("\n")
    new_lines = []

    # 检查是否已有 SEGGER_RTT_Init 调用
    has_existing_init = "SEGGER_RTT_Init" in content
    # 检查是否已有 SEGGER_RTT.h include
    has_existing_include = 'SEGGER_RTT.h' in content

    added_include = has_existing_include
    added_init = has_existing_init

    if has_existing_init:
        warnings.append("SEGGER_RTT_Init() 已存在于 main.c 中，跳过初始化代码添加")
    if has_existing_include:
        warnings.append("SEGGER_RTT.h 已包含，跳过 include 添加")

    for i, line in enumerate(lines):
        new_lines.append(line)

        # 2. 在 System_Init() 调用后添加 SEGGER_RTT_Init()
        if not added_init and "System_Init()" in line:
            indent = "    " if line.startswith("    ") else ""
            new_lines.append(f"{indent}#ifdef USE_RTT")
            new_lines.append(f'{indent}    SEGGER_RTT_Init();')
            new_lines.append(f'{indent}    SEGGER_RTT_printf(0, "[RTT] Initialized\\r\\n");')
            new_lines.append(f"{indent}#endif")
            added_init = True

    # 添加 include（插入到最后一个 #include 之后）
    if not added_include:
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("#include") and "SEGGER_RTT" not in line:
                insert_pos = i + 1

        # 插入 #ifdef USE_RTT 保护的 include
        new_lines.insert(insert_pos, '#ifdef USE_RTT')
        new_lines.insert(insert_pos + 1, '#include "SEGGER_RTT.h"')
        new_lines.insert(insert_pos + 2, '#endif')
        added_include = True

    new_content = "\n".join(new_lines)

    try:
        main_path.write_text(new_content, encoding="utf-8")
    except UnicodeDecodeError:
        main_path.write_text(new_content, encoding="gbk")

    # 写入后验证
    verify = verify_rtt_init_in_main(main_c_path)
    if not verify["verified"]:
        errors.append(f"验证失败: RTT 初始化代码未正确写入 main.c")
        if not verify["has_include"]:
            errors.append("  - #include \"SEGGER_RTT.h\" 未找到")
        if not verify["has_init_call"]:
            errors.append("  - SEGGER_RTT_Init() 调用未找到")

    return {
        "success": len(errors) == 0,
        "backup_path": str(backup_path),
        "added_include": added_include,
        "added_init": added_init,
        "warnings": warnings,
        "errors": errors,
        "verified": verify["verified"],
    }


def verify_rtt_init_in_main(main_c_path: str) -> dict:
    """重新读取 main.c，验证 RTT 初始化代码是否正确放置。

    Returns:
        {"verified": bool, "has_include": bool, "has_init_call": bool, "errors": [...]}
    """
    main_path = Path(main_c_path)
    if not main_path.exists():
        return {
            "verified": False,
            "has_include": False,
            "has_init_call": False,
            "errors": [f"main.c 不存在: {main_c_path}"],
        }

    try:
        content = main_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = main_path.read_text(encoding="gbk")

    has_include = "SEGGER_RTT.h" in content
    has_init_call = "SEGGER_RTT_Init" in content
    verified = has_include and has_init_call

    errors = []
    if not has_include:
        errors.append('#include "SEGGER_RTT.h" 未找到')
    if not has_init_call:
        errors.append("SEGGER_RTT_Init() 调用未找到")

    return {
        "verified": verified,
        "has_include": has_include,
        "has_init_call": has_init_call,
        "errors": errors,
    }


def add_rtt_macro_to_defines(
    project_root: str,
    uvprojx_path: str | None = None,
    ewp_path: str | None = None,
) -> dict:
    """在工程文件中添加 USE_RTT 宏到预处理器定义。

    - Keil: 在 .uvprojx 的 VariousControls > Define 中追加 USE_RTT
    - IAR: 在 .ewp 的 ICCARM > CCDefines 中追加 <state>USE_RTT</state>

    Returns:
        {"success": bool, "ide_type": str, "macro_added": bool, "errors": [...]}
    """
    from mklink.iar_parser import find_ewp
    from mklink.keil_parser import find_uvprojx

    root = Path(project_root).resolve()

    # 优先尝试 IAR
    if ewp_path is None:
        ewp_path = find_ewp(root)

    if ewp_path:
        return _add_macro_to_iar(ewp_path)

    # 回退到 Keil
    if uvprojx_path is None:
        mdk_arm = root / "MDK-ARM"
        if mdk_arm.exists():
            uvprojx_list = list(mdk_arm.glob("*.uvprojx"))
            if uvprojx_list:
                uvprojx_path = str(uvprojx_list[0])
        if uvprojx_path is None:
            uvprojx_path = find_uvprojx(root)

    if uvprojx_path:
        return _add_macro_to_keil(uvprojx_path)

    return {
        "success": False,
        "ide_type": "unknown",
        "macro_added": False,
        "errors": ["未找到 Keil 或 IAR 工程文件，无法添加 USE_RTT 宏"],
    }


def _add_macro_to_keil(uvprojx_path: str) -> dict:
    """在 Keil .uvprojx 工程中添加 USE_RTT 宏。"""
    uvprojx = Path(uvprojx_path)
    if not uvprojx.exists():
        return {
            "success": False,
            "ide_type": "Keil",
            "macro_added": False,
            "errors": [f"工程文件不存在: {uvprojx_path}"],
        }

    try:
        tree = ET.parse(str(uvprojx))
        root = tree.getroot()
    except ET.ParseError as e:
        return {
            "success": False,
            "ide_type": "Keil",
            "macro_added": False,
            "errors": [f"XML 解析失败: {e}"],
        }

    # 查找 Define 元素
    define_el = root.find(".//VariousControls/Define")
    if define_el is None:
        return {
            "success": False,
            "ide_type": "Keil",
            "macro_added": False,
            "errors": ["未找到 VariousControls/Define 节点"],
        }

    current = define_el.text or ""
    defines = [d.strip() for d in current.split(",") if d.strip()]

    if "USE_RTT" in defines:
        return {
            "success": True,
            "ide_type": "Keil",
            "macro_added": False,
            "errors": ["USE_RTT 宏已存在于工程定义中，跳过"],
        }

    defines.append("USE_RTT")
    define_el.text = ", ".join(defines)

    tree.write(str(uvprojx), encoding="utf-8", xml_declaration=True)

    return {
        "success": True,
        "ide_type": "Keil",
        "macro_added": True,
        "errors": [],
    }


def _add_macro_to_iar(ewp_path: str) -> dict:
    """在 IAR .ewp 工程中添加 USE_RTT 宏。"""
    ewp = Path(ewp_path)
    if not ewp.exists():
        return {
            "success": False,
            "ide_type": "IAR",
            "macro_added": False,
            "errors": [f"工程文件不存在: {ewp_path}"],
        }

    try:
        tree = ET.parse(str(ewp))
        root = tree.getroot()
    except ET.ParseError as e:
        return {
            "success": False,
            "ide_type": "IAR",
            "macro_added": False,
            "errors": [f"XML 解析失败: {e}"],
        }

    if root.tag != "project":
        return {
            "success": False,
            "ide_type": "IAR",
            "macro_added": False,
            "errors": [f"无效的 EWP 文件，根节点应为 project，实际为 {root.tag}"],
        }

    # 查找 ICCARM settings 中的 CCDefines
    for config in root.findall("configuration"):
        for settings in config.findall("settings"):
            sname_el = settings.find("name")
            if sname_el is not None and sname_el.text == "ICCARM":
                for data in settings.findall("data"):
                    for option in data.findall("option"):
                        name_el = option.find("name")
                        if name_el is not None and name_el.text == "CCDefines":
                            # 检查是否已有 USE_RTT
                            for state in option.findall("state"):
                                if state.text and state.text.strip() == "USE_RTT":
                                    return {
                                        "success": True,
                                        "ide_type": "IAR",
                                        "macro_added": False,
                                        "errors": ["USE_RTT 宏已存在于工程定义中，跳过"],
                                    }
                            # 追加 USE_RTT
                            new_state = ET.SubElement(option, "state")
                            new_state.text = "USE_RTT"
                            tree.write(str(ewp), encoding="utf-8", xml_declaration=True)
                            return {
                                "success": True,
                                "ide_type": "IAR",
                                "macro_added": True,
                                "errors": [],
                            }

    return {
        "success": False,
        "ide_type": "IAR",
        "macro_added": False,
        "errors": ["未找到 ICCARM/CCDefines 节点"],
    }


def full_rtt_integrate(
    project_root: str,
    uvprojx_path: str | None = None,
    ewp_path: str | None = None,
    src_dir: str = "src",
    inc_dir: str = "inc",
    main_c_path: str | None = None,
) -> dict:
    """完整的 RTT 集成流程。

    1. 复制 RTT 源文件到项目
    2. 将文件添加到 Keil 或 IAR 工程
    3. 在 main.c 中添加初始化代码（USE_RTT 宏保护）
    4. 在工程中添加 USE_RTT 宏定义

    Returns:
        详细的结果字典
    """
    from mklink.iar_parser import find_ewp
    from mklink.keil_parser import find_uvprojx

    results = {
        "copy": None,
        "keil": None,
        "iar": None,
        "main": None,
        "macro": None,
        "success": False,
    }

    # 1. 复制源文件
    copy_result = integrate_rtt_sources(src_dir, inc_dir)
    results["copy"] = copy_result
    if not copy_result["success"]:
        results["errors"] = copy_result.get("errors", [])
        return results

    success = True

    # 2. 找到工程文件并添加文件
    root = Path(project_root).resolve()
    detected_ewp = ewp_path
    detected_uvprojx = uvprojx_path

    # 优先使用传入的 ewp_path
    if detected_ewp is None:
        detected_ewp = find_ewp(root)

    if detected_ewp:
        iar_result = add_rtt_to_iar_project(detected_ewp, src_dir, inc_dir)
        results["iar"] = iar_result
    else:
        # 回退到 Keil
        if detected_uvprojx is None:
            mdk_arm = root / "MDK-ARM"
            if mdk_arm.exists():
                uvprojx_list = list(mdk_arm.glob("*.uvprojx"))
                if uvprojx_list:
                    detected_uvprojx = str(uvprojx_list[0])

        if detected_uvprojx:
            keil_result = add_rtt_to_keil_project(detected_uvprojx, src_dir, inc_dir)
            results["keil"] = keil_result

    # 3. 找到 main.c 并添加初始化代码
    if main_c_path is None:
        main_c_path = str(root / "src" / "main.c")
        if not Path(main_c_path).exists():
            main_c_path = str(root / "main.c")

    if Path(main_c_path).exists():
        main_result = add_rtt_init_to_main(main_c_path)
        results["main"] = main_result
        if not main_result["success"]:
            success = False
    else:
        success = False
        results["main_error"] = f"main.c 未找到: {main_c_path}"

    # 4. 在工程中添加 USE_RTT 宏
    macro_result = add_rtt_macro_to_defines(
        project_root,
        uvprojx_path=detected_uvprojx,
        ewp_path=detected_ewp,
    )
    results["macro"] = macro_result
    if not macro_result["success"]:
        success = False

    results["success"] = success
    return results


# ============================================================================
# 全量脚本化：rtt-integrate --static-addr
# ============================================================================

def _find_main_c(project_root: Path) -> Path | None:
    """在项目中查找 main.c 真实路径。

    候选位置（按优先级）：
    1. applications/main.c
    2. src/main.c
    3. main.c（项目根）
    4. User/main.c
    """
    candidates = [
        project_root / "applications" / "main.c",
        project_root / "src" / "main.c",
        project_root / "main.c",
        project_root / "User" / "main.c",
    ]
    for c in candidates:
        if c.exists():
            return c
    # 回退：递归搜索
    matches = list(project_root.glob("**/main.c"))
    return matches[0] if matches else None


def _register_keil_files(uvprojx_path: str, file_entries: list[tuple[str, str]]) -> dict:
    """在 Keil uvprojx 中注册源文件到指定 Group。

    Args:
        uvprojx_path: 工程文件路径
        file_entries: [(group_name, file_path), ...] 列表

    Returns:
        {"success": bool, "added": [...], "skipped": [...], "errors": [...]}
    """
    import xml.etree.ElementTree as ET
    uvprojx = Path(uvprojx_path)
    if not uvprojx.exists():
        return {"success": False, "added": [], "skipped": [], "errors": [f"工程文件不存在: {uvprojx_path}"]}

    try:
        tree = ET.parse(str(uvprojx))
        root_el = tree.getroot()
    except ET.ParseError as e:
        return {"success": False, "added": [], "skipped": [], "errors": [f"XML 解析失败: {e}"]}

    target = root_el.find(".//Target")
    if target is None:
        return {"success": False, "added": [], "skipped": [], "errors": ["未找到 Target 节点"]}

    groups_el = target.find("Groups")
    if groups_el is None:
        groups_el = ET.SubElement(target, "Groups")

    added = []
    skipped = []
    errors = []

    for group_name, file_path in file_entries:
        file_path = file_path.replace("/", "\\")
        file_name = Path(file_path).name

        # 找或创建 Group
        group_el = None
        for g in groups_el.findall("Group"):
            gn = g.find("GroupName")
            if gn is not None and gn.text == group_name:
                group_el = g
                break
        if group_el is None:
            group_el = ET.SubElement(groups_el, "Group")
            ET.SubElement(group_el, "GroupName").text = group_name
            ET.SubElement(group_el, "Files")
        files_el = group_el.find("Files")
        if files_el is None:
            files_el = ET.SubElement(group_el, "Files")

        # 检查是否已存在
        exists = False
        for f in files_el.findall("File"):
            fp = f.find("FilePath")
            if fp is not None and fp.text == file_path:
                exists = True
                skipped.append(file_path)
                break
        if not exists:
            file_el = ET.SubElement(files_el, "File")
            ET.SubElement(file_el, "FileName").text = file_name
            ET.SubElement(file_el, "FileType").text = "1"
            ET.SubElement(file_el, "FilePath").text = file_path
            added.append(f"{group_name}/{file_path}")

    if added:
        try:
            tree.write(str(uvprojx), encoding="utf-8", xml_declaration=True)
        except OSError as e:
            return {"success": False, "added": [], "skipped": skipped,
                    "errors": [f"写工程文件失败: {e}"]}

    return {"success": len(errors) == 0, "added": added, "skipped": skipped, "errors": errors}


def _update_scatter_for_rtt(sct_path: str, static_addr: str, rtt_size: int = 0x1000) -> dict:
    """更新 scatter 文件，添加 RW_IRAM_RTT 段（静态 RTT 模式）。

    操作：
    1. 备份 scatter
    2. 找到 RW_IRAM1 段，缩小其 size 以让出 RTT 区域
    3. 在 RW_IRAM1 段后插入 RW_IRAM_RTT 段

    Returns:
        {"success": bool, "backup": str, "changes": [...], "errors": [...]}
    """
    import re
    sct = Path(sct_path)
    if not sct.exists():
        return {"success": False, "backup": None, "changes": [], "errors": [f"scatter 不存在: {sct_path}"]}

    backup = _backup_file(sct)

    try:
        text = sct.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return {"success": False, "backup": str(backup), "changes": [], "errors": [f"读 scatter 失败: {e}"]}

    changes = []

    # 如果已有 RW_IRAM_RTT，跳过
    if re.search(r"\bRW_IRAM_RTT\b", text):
        changes.append("RW_IRAM_RTT 已存在，跳过")
        return {"success": True, "backup": str(backup), "changes": changes, "errors": []}

    # 找到 RW_IRAM1 段的 size 字段
    # 匹配模式：RW_IRAM1 0x20000200 0x<HEX>
    m = re.search(r"(\bRW_IRAM1\s+0x[0-9a-fA-F]+\s+)0x[0-9a-fA-F]+(\s*\{)", text)
    if not m:
        return {"success": False, "backup": str(backup), "changes": [],
                "errors": ["未找到 RW_IRAM1 段，无法插入 RW_IRAM_RTT"]}

    old_size_match = re.search(r"\bRW_IRAM1\s+0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+", text)
    if not old_size_match:
        return {"success": False, "backup": str(backup), "changes": [], "errors": ["无法解析 RW_IRAM1 size"]}
    old_size = int(old_size_match.group(0).split()[-1], 16)
    new_size = old_size - rtt_size

    if new_size <= 0:
        return {"success": False, "backup": str(backup), "changes": [],
                "errors": [f"RW_IRAM1 size {old_size:#x} 不足以让出 {rtt_size:#x}"]}

    new_size_str = f"0x{new_size:08X}"
    rtt_size_str = f"0x{rtt_size:08X}"

    # 替换 size
    new_text = re.sub(
        r"(\bRW_IRAM1\s+0x[0-9a-fA-F]+\s+)0x[0-9a-fA-F]+",
        rf"\g<1>{new_size_str}",
        text, count=1
    )

    # 在 RW_IRAM1 段结束的 '}' 后插入 RW_IRAM_RTT 段
    # 找到 RW_IRAM1 块
    block_pattern = re.compile(
        r"(\bRW_IRAM1\s+0x[0-9a-fA-F]+\s+" + re.escape(new_size_str) +
        r"\s*\{[^}]*\}\s*)",
        re.DOTALL
    )
    block_m = block_pattern.search(new_text)
    if not block_m:
        return {"success": False, "backup": str(backup), "changes": [],
                "errors": ["无法定位 RW_IRAM1 段结束位置"]}

    insert = (
        f"\n  ; RTT static area - {static_addr} (mklink-flash 静态 RTT 模式)\n"
        f"  RW_IRAM_RTT {static_addr} {rtt_size_str}  {{\n"
        f"   *.o (.segger_rtt_ops)\n"
        f"  }}"
    )
    new_text = new_text[:block_m.end()] + insert + new_text[block_m.end():]

    try:
        sct.write_text(new_text, encoding="utf-8")
    except OSError as e:
        return {"success": False, "backup": str(backup), "changes": [],
                "errors": [f"写 scatter 失败: {e}"]}

    changes.append(f"RW_IRAM1: {old_size:#x} → {new_size:#x}")
    changes.append(f"RW_IRAM_RTT 新增: {static_addr} {rtt_size_str}")
    return {"success": True, "backup": str(backup), "changes": changes, "errors": []}


def _add_static_macro_to_keil(uvprojx_path: str, macro: str = "MKLINK_RTT_STATIC") -> dict:
    """在 Keil uvprojx 的 Define 中添加指定宏。"""
    import xml.etree.ElementTree as ET
    uvprojx = Path(uvprojx_path)
    if not uvprojx.exists():
        return {"success": False, "added": False, "errors": [f"工程文件不存在: {uvprojx_path}"]}

    try:
        tree = ET.parse(str(uvprojx))
        root_el = tree.getroot()
    except ET.ParseError as e:
        return {"success": False, "added": False, "errors": [f"XML 解析失败: {e}"]}

    define_el = root_el.find(".//VariousControls/Define")
    if define_el is None:
        return {"success": False, "added": False, "errors": ["未找到 VariousControls/Define 节点"]}

    defines = [d.strip() for d in (define_el.text or "").split(",") if d.strip()]
    if macro in defines:
        return {"success": True, "added": False, "errors": [f"{macro} 已存在"]}

    backup = _backup_file(uvprojx)
    defines.append(macro)
    define_el.text = ", ".join(defines)
    tree.write(str(uvprojx), encoding="utf-8", xml_declaration=True)
    return {"success": True, "added": True, "backup": str(backup), "errors": []}


def full_rtt_integrate_v2(
    project_root: str,
    static_addr: str | None = None,
    uvprojx_path: str | None = None,
    ewp_path: str | None = None,
    src_dir: str = "src",
    inc_dir: str = "inc",
    main_c_path: str | None = None,
) -> dict:
    """完整的 RTT 集成流程（v2 全自动化版）。

    步骤：
    1. 复制 RTT 源文件 + 心跳源到项目
    2. 注册源文件到 Keil uvprojx 文件组
    3. 找 main.c 并加 #include + SEGGER_RTT_Init()
    4. 在 uvprojx <Define> 加 USE_RTT 宏
    5. （如果 static_addr 提供）加 MKLINK_RTT_STATIC 宏
    6. （如果 static_addr 提供）更新 scatter 加 RW_IRAM_RTT 段
    7. （如果 static_addr 提供）注册 rtt_heartbeat.c 到 applications Group

    任何步骤失败自动回滚已做的修改。
    """
    from mklink.iar_parser import find_ewp
    from mklink.keil_parser import find_uvprojx

    root = Path(project_root).resolve()
    backups = []  # (path, backup_path) tuples
    results = {
        "copy": None, "register": None, "main": None,
        "macro_use_rtt": None, "macro_static": None,
        "scatter": None, "register_heartbeat": None,
        "success": False, "errors": [],
    }

    def _track_backup(backup_path: Path | None):
        if backup_path and backup_path.exists():
            backups.append(str(backup_path))

    def _rollback():
        for backup_path in reversed(backups):
            try:
                backup = Path(backup_path)
                if backup.suffix.startswith(".bak."):
                    original = Path(backup.stem.split(".bak.")[0])
                    if original.exists():
                        original.unlink()
                    shutil.copy2(backup, original)
                    backup.unlink()
            except OSError as e:
                results["errors"].append(f"回滚 {backup_path} 失败: {e}")

    # 0. 检测工程（Keil 优先，uvprojx 存在时忽略 ewp）
    if uvprojx_path is None:
        uvprojx_path = find_uvprojx(root)
    if ewp_path is None and uvprojx_path is None:
        # 仅在找不到 Keil 项目时才回退到 IAR
        ewp_path = find_ewp(root)
    if uvprojx_path is None and ewp_path is None:
        results["errors"].append("未找到 Keil 或 IAR 工程文件")
        return results

    # 仅支持 Keil 自动化（IAR 自动化留作后续）
    if uvprojx_path is None and ewp_path:
        results["errors"].append("IAR 项目全自动化集成暂未实现，请手动完成或转用 Keil")
        return results

    # 1. 复制 RTT 源文件
    copy_result = integrate_rtt_sources(str(src_dir), str(inc_dir))
    results["copy"] = copy_result
    if not copy_result["success"]:
        results["errors"].extend(copy_result.get("errors", []))
        return results

    # 2. 注册源文件到 Keil uvprojx（用绝对路径，与 add_rtt_to_keil_project 风格一致）
    abs_src_dir = str(Path(src_dir).resolve())
    register_entries = [
        ("SEGGER_RTT", f"{abs_src_dir}\\SEGGER_RTT.c"),
        ("SEGGER_RTT", f"{abs_src_dir}\\SEGGER_RTT_printf.c"),
    ]
    if static_addr:
        # 心跳源已复制到 src_dir（与 SEGGER_RTT.c 一起）
        heartbeat_path = f"{abs_src_dir}\\{_RTT_HEARTBEAT_DST}"
        register_entries.append(("applications", heartbeat_path))
    register_result = _register_keil_files(uvprojx_path, register_entries)
    results["register"] = register_result
    if not register_result["success"]:
        results["errors"].extend(register_result.get("errors", []))
        _rollback()
        return results

    # 3. 找 main.c 并加初始化代码
    if main_c_path is None:
        main_c = _find_main_c(root)
        if main_c is None:
            results["errors"].append(f"main.c 未找到（搜索路径: {root}）")
            _rollback()
            return results
        main_c_path = str(main_c)

    main_result = add_rtt_init_to_main(main_c_path)
    results["main"] = main_result
    if not main_result["success"]:
        results["errors"].extend(main_result.get("errors", []))
        _rollback()
        return results

    # 4. 加 USE_RTT 宏
    macro_result = _add_macro_to_keil(uvprojx_path)
    results["macro_use_rtt"] = macro_result
    if not macro_result["success"]:
        results["errors"].extend(macro_result.get("errors", []))
        _rollback()
        return results

    # 5-7. 静态模式额外步骤
    if static_addr:
        # 5. 加 MKLINK_RTT_STATIC 宏
        static_macro_result = _add_static_macro_to_keil(uvprojx_path)
        results["macro_static"] = static_macro_result
        if not static_macro_result["success"]:
            results["errors"].extend(static_macro_result.get("errors", []))
            _rollback()
            return results

        # 6. 更新 scatter
        from mklink.keil_parser import find_scatter_file
        sct_path = find_scatter_file(uvprojx_path)
        if sct_path:
            sct_result = _update_scatter_for_rtt(sct_path, static_addr)
            results["scatter"] = sct_result
            if not sct_result["success"]:
                results["errors"].extend(sct_result.get("errors", []))
                _rollback()
                return results
        else:
            results["errors"].append("uvprojx 中未找到 ScatterFile，无法自动更新 scatter")
            _rollback()
            return results

    results["success"] = True
    return results


def generate_rtt_usage_example() -> str:
    """返回 RTT 集成后的 C 代码使用示例。"""
    return """\
// 所有 RTT 代码被 USE_RTT 宏保护，关闭宏即可禁用所有 RTT 输出。
//
// 在 Keil 中控制: Options → C/C++ → Preprocessor Symbols → Define 中添加/移除 USE_RTT
// 在 IAR 中控制: Project → Options → C/C++ Compiler → Preprocessor → Defined symbols 中添加/移除 USE_RTT
//
// 生产固件时移除 USE_RTT 宏即可，无需修改代码。

// 在需要使用 RTT 的文件中使用:
#ifdef USE_RTT
#include "SEGGER_RTT.h"
#endif

// 使用 RTT 输出调试信息（需在 USE_RTT 宏保护内）:
#ifdef USE_RTT
    SEGGER_RTT_Init();
    SEGGER_RTT_printf(0, "Hello RTT! count=%d\\n", count);
#endif

// === RTT 控制块存储方式（两种模式）===
//
// 模式 0 (默认) — 动态搜寻：无需特殊 C 代码，链接器自动放置 _SEGGER_RTT，
//                   PC 端从 MAP/ELF 解析地址，探针固件运行时扫描。
//
// 模式 1 — 静态编译：在 C 代码中用 SEGGER_RTT_SECTION 宏把控制块固定到
//                 已知地址，PC 端用 uvprojx+scatter 静态解析段地址作为 CB 精确地址。
//                 适合调试期间想要稳定 CB 地址、避免扫描的场合。
//
// 模式 1 启用步骤（以 Keil 为例）：
//   1) 在 scatter (.sct) 加段：RW_IRAM_RTT 0x2001F800 0x00000800 { *.o (.segger_rtt_ops) }
//   2) project.uvprojx 的 <Define> 追加: SEGGER_RTT_SECTION=.segger_rtt_ops
//   3) 重新编译
//   4) 切换 .mklink/rtt_config.json:rtt_storage_mode = 1（GUI 高置配置处可选）
//   5) mklink rtt-integrate 会自动检测到静态地址并写回 rtt_addr

// 注意事项:
// - SEGGER_RTT.c 和 SEGGER_RTT_printf.c 已添加到工程的 SEGGER_RTT 分组
// - SEGGER_RTT.h 和 SEGGER_RTT_Conf.h 已放在项目的头文件目录中
// - SEGGER_RTT_Conf.h 中可调整 BUFFER_SIZE_UP (默认 1024) 和 BUFFER_SIZE_DOWN (默认 16)
"""
