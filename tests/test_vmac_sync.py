import os
import time
import tempfile

from mcp_memory_bank_server import (
    CORE_TYPES,
    get_vmac_dir,
    ensure_vmac_dir,
    write_core_md,
    read_core_md,
    compile_tasks_md,
    tasks_md_path,
    initialize_memory_bank,
    read_entire_bank,
    update_memory_block,
    add_repetitive_task,
)


def test_vmac_paths_and_write_read():
    with tempfile.TemporaryDirectory() as root:
        d = get_vmac_dir(root)
        assert d.endswith(os.path.join(".vmac", "rules", "memory-bank"))
        ensure_vmac_dir(root)
        assert os.path.isdir(d)
        write_core_md(root, "context", "# hello")
        assert read_core_md(root, "context") == "# hello"
        assert os.path.isfile(os.path.join(d, "context.md"))


def test_compile_tasks_md():
    tasks = [
        {
            "task_name": "Add model",
            "description": "desc",
            "files_to_modify": "a.py",
            "steps": "1. do\n2. it",
            "gotchas": "watch X",
            "last_performed": "2026-07-15",
        }
    ]
    md = compile_tasks_md(tasks)
    assert "# Repetitive Tasks" in md
    assert "Add model" in md
    assert "watch X" in md


def test_initialize_creates_vmac_and_db():
    with tempfile.TemporaryDirectory() as root:
        out = initialize_memory_bank("Demo", root)
        assert "[Memory Bank: Active]" in out
        assert os.path.isfile(os.path.join(root, "mcp_memory_bank.db"))
        mb = os.path.join(root, ".vmac", "rules", "memory-bank")
        for name in CORE_TYPES:
            assert os.path.isfile(os.path.join(mb, f"{name}.md"))
        assert os.path.isfile(os.path.join(mb, "tasks.md"))


def test_update_writes_md_and_blocks_brief():
    with tempfile.TemporaryDirectory() as root:
        initialize_memory_bank("Demo", root)
        r = update_memory_block(root, "context", "# new ctx")
        assert "Sukses" in r
        assert read_core_md(root, "context") == "# new ctx"
        before = read_core_md(root, "brief")
        r2 = update_memory_block(root, "brief", "hack")
        assert "brief" in r2.lower() or "Peringatan" in r2
        assert read_core_md(root, "brief") == before


def test_add_task_writes_tasks_md():
    with tempfile.TemporaryDirectory() as root:
        initialize_memory_bank("Demo", root)
        add_repetitive_task(root, "T1", "d", "step1", "f.py", "g")
        body = open(tasks_md_path(root), encoding="utf-8").read()
        assert "T1" in body


def test_auto_heal_from_vmac_when_db_empty():
    with tempfile.TemporaryDirectory() as root:
        ensure_vmac_dir(root)
        write_core_md(root, "brief", "# B")
        write_core_md(root, "product", "# P")
        write_core_md(root, "context", "# C")
        write_core_md(root, "architecture", "# A")
        write_core_md(root, "tech", "# T")
        out = read_entire_bank(root)
        assert "[Memory Bank: Active]" in out
        assert "# C" in out


def test_mtime_file_wins():
    with tempfile.TemporaryDirectory() as root:
        initialize_memory_bank("Demo", root)
        time.sleep(1.1)
        write_core_md(root, "context", "# manual edit")
        out = read_entire_bank(root)
        assert "# manual edit" in out
