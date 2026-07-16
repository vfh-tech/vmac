import os
import tempfile

from mcp_memory_bank_server import (
    apply_section_patch,
    initialize_memory_bank,
    read_entire_bank,
    update_memory_block,
    read_core_md,
    memory_bank_health,
    collect_health_report,
)


def test_reinit_preserves_filled_core():
    with tempfile.TemporaryDirectory() as root:
        initialize_memory_bank("Demo", root)
        update_memory_block(root, "context", "# CTX_CUSTOM")
        update_memory_block(root, "product", "# PROD_CUSTOM")
        out = initialize_memory_bank("DemoRenamed", root, initial_analysis="SHOULD_NOT_WIPE")
        assert "[Memory Bank: Active]" in out
        assert "Re-init" in out or "dipertahankan" in out.lower() or "existing" in out.lower()
        bank = read_entire_bank(root)
        assert "# CTX_CUSTOM" in bank
        assert "# PROD_CUSTOM" in bank
        assert "SHOULD_NOT_WIPE" not in bank  # initial_analysis tidak menimpa architecture existing
        assert read_core_md(root, "context") == "# CTX_CUSTOM"


def test_reinit_fills_missing_core_only():
    with tempfile.TemporaryDirectory() as root:
        initialize_memory_bank("Demo", root)
        # hapus satu core di DB via re-path: simulasikan dengan overwrite file lalu...
        # lebih sederhana: init, hapus baris lewat sqlite
        import sqlite3
        db = os.path.join(root, "mcp_memory_bank.db")
        conn = sqlite3.connect(db)
        conn.execute("DELETE FROM memory_core WHERE file_type = 'tech'")
        conn.commit()
        conn.close()
        initialize_memory_bank("Demo", root)
        bank = read_entire_bank(root)
        assert "Tech Stack" in bank or "tech" in bank.lower()


def test_apply_section_patch_replaces_body():
    src = "# T\n\n## Alpha\n\nold-a\n\n## Beta\n\nold-b\n"
    out = apply_section_patch(src, "Alpha", "new-a")
    assert "## Alpha" in out
    assert "new-a" in out
    assert "old-a" not in out
    assert "## Beta" in out
    assert "old-b" in out


def test_apply_section_patch_appends_missing():
    src = "# T\n\n## Alpha\n\na\n"
    out = apply_section_patch(src, "Gamma", "g-body")
    assert "## Gamma" in out
    assert "g-body" in out
    assert "## Alpha" in out


def test_update_memory_block_patch_mode():
    with tempfile.TemporaryDirectory() as root:
        initialize_memory_bank("Demo", root)
        update_memory_block(root, "context", "# Current Context\n\n## Fokus\n\nold\n\n## Next\n\nn1\n")
        r = update_memory_block(
            root, "context", "fresh", mode="patch", section="Fokus"
        )
        assert "Sukses" in r
        body = read_core_md(root, "context")
        assert "fresh" in body
        assert "old" not in body
        assert "## Next" in body
        assert "n1" in body


def test_update_patch_rejects_brief_and_bad_args():
    with tempfile.TemporaryDirectory() as root:
        initialize_memory_bank("Demo", root)
        r1 = update_memory_block(root, "brief", "x", mode="patch", section="Scope")
        assert "brief" in r1.lower() or "Peringatan" in r1
        r2 = update_memory_block(root, "context", "x", mode="patch", section="")
        assert "Error" in r2 or "section" in r2.lower()
        r3 = update_memory_block(root, "context", "x", mode="nope")
        assert "Error" in r3 or "mode" in r3.lower()


def test_health_ok_after_init():
    with tempfile.TemporaryDirectory() as root:
        initialize_memory_bank("Demo", root)
        rep = collect_health_report(root)
        assert rep["status"] == "ok"
        assert rep["project_registered"] is True
        assert set(rep["core_in_db"]) == set(["brief", "product", "context", "architecture", "tech"])
        text = memory_bank_health(root)
        assert "ok" in text.lower() or "sehat" in text.lower() or "OK" in text


def test_health_missing_uninitialized():
    with tempfile.TemporaryDirectory() as root:
        rep = collect_health_report(root)
        assert rep["status"] == "missing"
        text = memory_bank_health(root)
        assert "missing" in text.lower() or "belum" in text.lower()


def test_health_degraded_missing_md():
    with tempfile.TemporaryDirectory() as root:
        initialize_memory_bank("Demo", root)
        os.remove(os.path.join(root, ".vmac", "rules", "memory-bank", "context.md"))
        rep = collect_health_report(root)
        assert rep["status"] == "degraded"
        assert "context" in rep["core_md_missing"]
