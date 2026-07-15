import os
import tempfile

from mcp_memory_bank_server import (
    initialize_memory_bank,
    read_entire_bank,
    update_memory_block,
    read_core_md,
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
