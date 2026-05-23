import os
import sys
import sqlite3
import logging
import contextlib
from datetime import datetime
from typing import Optional
from mcp.server.fastmcp import FastMCP

# =====================================================================
# CONFIGURATION & LOGGING (PRODUCTION READY)
# =====================================================================
# PENTING: Semua log HARUS diarahkan ke sys.stderr. 
# sys.stdout digunakan secara eksklusif oleh protokol MCP untuk komunikasi JSON-RPC.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("mcp-memory-bank")

# Inisialisasi FastMCP Server
mcp = FastMCP("Memory Bank SQLite")

# =====================================================================
# DATABASE UTILITIES & SCHEMA INITIALIZATION
# =====================================================================
def normalize_path(path: str) -> str:
    """Standardisasi path untuk menghindari duplikasi akibat trailing slash atau relative path."""
    return os.path.abspath(os.path.expanduser(path))

def get_db_path(root_path: str) -> str:
    """Mendapatkan path database SQLite di root proyek target."""
    return os.path.join(normalize_path(root_path), "mcp_memory_bank.db")

def init_db(conn: sqlite3.Connection, db_path: str):
    """Inisialisasi skema database jika belum terbentuk."""
    logger.info(f"Menginisialisasi database di: {db_path}")
    # 1. Tabel Projects
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL,
            root_path TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # 2. Tabel Memory Core (brief, product, context, architecture, tech)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_core (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            file_type TEXT CHECK(file_type IN ('brief', 'product', 'context', 'architecture', 'tech')) NOT NULL,
            content TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(project_id, file_type)
        );
    """)
    
    # 3. Tabel Tasks (Pekerjaan Repetitif / SOP)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            task_name TEXT NOT NULL,
            description TEXT,
            files_to_modify TEXT,
            steps TEXT NOT NULL,
            gotchas TEXT,
            last_performed DATE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    logger.info("Inisialisasi skema database SQLite berhasil dilakukan.")

@contextlib.contextmanager
def get_db_connection(root_path: str):
    """Membuat koneksi ke database SQLite dinamis di root proyek target dengan penutupan otomatis."""
    db_path = get_db_path(root_path)
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    # Mengaktifkan Foreign Key support di SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    
    # Inisialisasi skema tabel otomatis
    init_db(conn, db_path)
    try:
        yield conn
    finally:
        conn.close()

# =====================================================================
# PROJECT SCANNING & FILE UTILITIES
# =====================================================================
def scan_project(root_path: str) -> dict:
    """Memindai proyek secara rekursif untuk mendeteksi teknologi dan arsitektur dasar."""
    detected = {
        "languages": [],
        "frameworks_and_tools": [],
        "config_files": [],
        "structure": []
    }
    
    # Direktori yang dilewati saat scanning
    exclude_dirs = {
        '.git', '.venv', 'venv', 'node_modules', '__pycache__', 
        'dist', 'build', 'out', '.idea', '.vscode', '.vmac'
    }
    
    try:
        for root, dirs, files in os.walk(root_path):
            # Batasi kedalaman folder yang dipindai agar cepat
            depth = root[len(root_path):].count(os.sep)
            if depth > 2:
                dirs[:] = []
                continue
                
            # Filter direktori yang dikecualikan
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for file in files:
                if file == 'package.json':
                    detected["frameworks_and_tools"].append("Node.js / npm ecosystem")
                    detected["config_files"].append(file)
                elif file == 'pyproject.toml':
                    detected["frameworks_and_tools"].append("Python (uv/poetry)")
                    detected["config_files"].append(file)
                elif file == 'requirements.txt':
                    detected["frameworks_and_tools"].append("Python (pip)")
                    detected["config_files"].append(file)
                elif file == 'go.mod':
                    detected["languages"].append("Go")
                    detected["config_files"].append(file)
                elif file == 'composer.json':
                    detected["languages"].append("PHP")
                    detected["config_files"].append(file)
                elif file == 'Cargo.toml':
                    detected["languages"].append("Rust")
                    detected["config_files"].append(file)
                elif file.endswith('.py') and 'Python' not in detected["languages"]:
                    detected["languages"].append("Python")
                elif (file.endswith('.js') or file.endswith('.ts') or file.endswith('.jsx') or file.endswith('.tsx')) and 'JavaScript/TypeScript' not in detected["languages"]:
                    detected["languages"].append("JavaScript/TypeScript")
                elif file.endswith('.go') and 'Go' not in detected["languages"]:
                    detected["languages"].append("Go")
                elif file.endswith('.php') and 'PHP' not in detected["languages"]:
                    detected["languages"].append("PHP")
            
            # Catat struktur direktori tingkat pertama dan kedua
            rel_path = os.path.relpath(root, root_path)
            if rel_path == '.':
                detected["structure"].append("- / (Root)")
            else:
                indent = "  " * depth
                detected["structure"].append(f"{indent}- {os.path.basename(root)}/")
                
    except Exception as e:
        logger.error(f"Error saat scanning proyek: {str(e)}")
        
    return detected



# =====================================================================
# MCP TOOLS IMPLEMENTATION
# =====================================================================

@mcp.tool()
def initialize_memory_bank(project_name: str, root_path: str, initial_analysis: Optional[str] = "") -> str:
    """
    Mendaftarkan proyek baru dan menginisialisasi 5 file core utama Memory Bank ke dalam SQLite lokal proyek.
    Gunakan tool ini ketika user meminta 'initialize memory bank'.
    """
    norm_path = normalize_path(root_path)
    logger.info(f"Menerima permintaan inisialisasi untuk project '{project_name}' di {norm_path}")
    
    # Deteksi info proyek secara otomatis
    detected = scan_project(norm_path)
    
    lang_info = ", ".join(detected["languages"]) if detected["languages"] else "Tidak spesifik"
    tool_info = ", ".join(detected["frameworks_and_tools"]) if detected["frameworks_and_tools"] else "Tidak spesifik"
    config_info = ", ".join(detected["config_files"]) if detected["config_files"] else "Tidak ditemukan"
    structure_info = "\n".join(detected["structure"])
    
    # Template default menggunakan info deteksi proyek nyata
    default_content = {
        "brief": (
            f"# Brief - {project_name}\n\n"
            f"Dokumen fondasi scope dan requirement proyek. Ditulis secara manual oleh developer.\n\n"
            f"## Deskripsi Proyek\n"
            f"- Proyek: {project_name}\n"
            f"- Path: {norm_path}\n"
        ),
        "product": (
            f"# Product Vision - {project_name}\n\n"
            f"## Kenapa proyek ini ada\n"
            f"- Menjawab kebutuhan akan...\n\n"
            f"## Masalah yang diselesaikan\n"
            f"- ...\n\n"
            f"## Goal user experience\n"
            f"- ..."
        ),
        "context": (
            f"# Current Context\n\n"
            f"- **Fokus Sekarang**: Inisialisasi proyek dan sinkronisasi memori pertama.\n"
            f"- **Perubahan Terakhir**: Pembentukan struktur Memory Bank dengan database SQLite lokal di root proyek.\n"
            f"- **Langkah Berikutnya**: Mulai mengidentifikasi fitur dan mendokumentasikannya."
        ),
        "architecture": (
            f"# Architecture - {project_name}\n\n"
            f"## Sistem Arsitektur\n"
            f"- Pola Arsitektur: ...\n\n"
            f"## Struktur Direktori Utama (Terdeteksi)\n"
            f"```text\n"
            f"{structure_info}\n"
            f"```\n\n"
            f"## Komponen Utama\n"
            f"- ..."
        ),
        "tech": (
            f"# Tech Stack & Constraints - {project_name}\n\n"
            f"## Teknologi Utama\n"
            f"- Bahasa pemrograman terdeteksi: {lang_info}\n"
            f"- Framework / Ekosistem: {tool_info}\n\n"
            f"## Dependencies\n"
            f"- Berkas konfigurasi terdeteksi: {config_info}\n\n"
            f"## Constraints Teknis\n"
            f"- ..."
        )
    }
    
    if initial_analysis:
        default_content["architecture"] += f"\n\n## Analisis Awal Tambahan:\n{initial_analysis}"
        
    try:
        # Hubungkan ke database lokal proyek
        with get_db_connection(norm_path) as conn:
            cursor = conn.cursor()
            
            # Bersihkan dan daftarkan ulang proyek di DB lokal proyek sendiri
            cursor.execute(
                "INSERT INTO projects (project_name, root_path) VALUES (?, ?) "
                "ON CONFLICT(root_path) DO UPDATE SET project_name=excluded.project_name",
                (project_name, norm_path)
            )
            
            cursor.execute("SELECT id FROM projects WHERE root_path = ?", (norm_path,))
            project_id = cursor.fetchone()["id"]
            
            # Simpan 5 core files ke SQLite
            for file_type, content in default_content.items():
                cursor.execute("""
                    INSERT INTO memory_core (project_id, file_type, content, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(project_id, file_type) DO UPDATE SET content=excluded.content, updated_at=CURRENT_TIMESTAMP
                """, (project_id, file_type, content))
                
            conn.commit()
            
        summary = (
            f"[Memory Bank: Active] Inisialisasi Berhasil! Proyek '{project_name}' telah dikunci di SQLite lokal root proyek.\n"
            f"Database SQLite (`mcp_memory_bank.db`) telah dibuat dengan 5 core files.\n"
            f"Gunakan `read_entire_bank` untuk memulihkan konteks di sesi berikutnya."
        )
        return summary
    except Exception as e:
        error_msg = f"Gagal menginisialisasi memory bank: {str(e)}"
        logger.error(error_msg)
        return f"[Memory Bank: Missing] Error: {error_msg}"


@mcp.tool()
def read_entire_bank(root_path: str) -> str:
    """
    MANDATORI: Dipanggil di AWAL SETIAP TUGAS oleh LLM untuk memulihkan seluruh konteks memori.
    Membaca seluruh isi Core Files proyek dari SQLite.
    """
    norm_path = normalize_path(root_path)
    logger.info(f"Membaca seluruh bank memori untuk path: {norm_path}")

    try:
        with get_db_connection(norm_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id, project_name FROM projects WHERE root_path = ?", (norm_path,))
            project = cursor.fetchone()

            if not project:
                return (
                    f"[Memory Bank: Missing]\n"
                    f"Proyek pada path '{norm_path}' belum diinisialisasi.\n"
                    f"Jalankan 'initialize memory bank' terlebih dahulu."
                )

            project_id = project["id"]
            project_name = project["project_name"]

            cursor.execute("SELECT file_type, content, updated_at FROM memory_core WHERE project_id = ?", (project_id,))
            rows = cursor.fetchall()

            cursor.execute("SELECT task_name, description FROM tasks WHERE project_id = ?", (project_id,))
            task_rows = cursor.fetchall()

        output = [
            f"[Memory Bank: Active]",
            f"# MEMORY BANK CONTEXT FOR: {project_name.upper()}",
            f"**Path Proyek:** {norm_path}",
            f"**Waktu Sinkronisasi:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            "---"
        ]

        core_data = {row["file_type"]: (row["content"], row["updated_at"]) for row in rows}
        order = ["brief", "product", "context", "architecture", "tech"]

        for file_type in order:
            if file_type in core_data:
                content, updated_at = core_data[file_type]
                output.append(f"\n## File: {file_type}.md (Last Updated: {updated_at})")
                output.append(content)
                output.append("\n---")

        if task_rows:
            output.append("\n## Available Repetitive Tasks (SOP) in Database:")
            for t in task_rows:
                output.append(f"- **{t['task_name']}**: {t['description']}")

        return "\n".join(output)
        
    except Exception as e:
        logger.error(f"Error saat membaca bank memori: {str(e)}")
        return f"[Memory Bank: Missing] Error internal saat membaca database: {str(e)}"


@mcp.tool()
def update_memory_block(root_path: str, file_type: str, new_content: str) -> str:
    """
    Memperbarui satu blok file core tertentu (brief, product, context, architecture, tech) di SQLite.
    Gunakan ini secara otomatis di akhir task (terutama untuk 'context') atau saat ada perubahan pola.
    """
    norm_path = normalize_path(root_path)
    
    if file_type not in ['brief', 'product', 'context', 'architecture', 'tech']:
        return f"Error: Tipe file '{file_type}' tidak valid. Harus salah satu dari core files."
        
    # Validasi proteksi untuk brief.md
    if file_type == 'brief':
        return (
            "Peringatan Keamanan: Berkas 'brief.md' adalah dokumen fondasi scope proyek yang HANYA boleh diubah secara manual "
            "oleh developer. Pembaruan otomatis melalui tool ini diblokir untuk menjaga integritas scope proyek."
        )
        
    logger.info(f"Mengupdate block '{file_type}' untuk proyek di {norm_path}")
    
    try:
        # Hubungkan ke database lokal proyek
        with get_db_connection(norm_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM projects WHERE root_path = ?", (norm_path,))
            project = cursor.fetchone()
            
            if not project:
                return f"Error: Proyek di path '{norm_path}' belum diinisialisasi. Jalankan inisialisasi terlebih dahulu."
                
            project_id = project["id"]
            
            cursor.execute("""
                INSERT INTO memory_core (project_id, file_type, content, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(project_id, file_type) DO UPDATE SET content=excluded.content, updated_at=CURRENT_TIMESTAMP
            """, (project_id, file_type, new_content))
            conn.commit()
            
        return f"Sukses: Blok memori '{file_type}.md' berhasil diperbarui di SQLite database."
    except Exception as e:
        logger.error(f"Gagal mengupdate blok memori: {str(e)}")
        return f"Error saat memperbarui database: {str(e)}"


@mcp.tool()
def add_repetitive_task(root_path: str, task_name: str, description: str, steps: str, files_to_modify: Optional[str] = "", gotchas: Optional[str] = "") -> str:
    """
    Menambahkan template prosedur kerja repetitif (SOP) ke dalam database.
    Dipanggil saat ada perintah 'add task' atau 'store this as a task'.
    """
    norm_path = normalize_path(root_path)
    logger.info(f"Menambahkan tugas repetitif baru '{task_name}' untuk proyek di {norm_path}")
    
    try:
        # Hubungkan ke database lokal proyek
        with get_db_connection(norm_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM projects WHERE root_path = ?", (norm_path,))
            project = cursor.fetchone()
            
            if not project:
                return f"Error: Proyek di path '{norm_path}' tidak ditemukan. Jalankan inisialisasi proyek terlebih dahulu."
                
            project_id = project["id"]
            
            cursor.execute("""
                INSERT INTO tasks (project_id, task_name, description, files_to_modify, steps, gotchas, last_performed)
                VALUES (?, ?, ?, ?, ?, ?, DATE('now'))
            """, (project_id, task_name, description, files_to_modify, steps, gotchas))
            conn.commit()

        return f"Sukses: Tugas repetitif (SOP) '{task_name}' berhasil disimpan ke SQLite."
    except Exception as e:
        logger.error(f"Gagal menyimpan tugas repetitif: {str(e)}")
        return f"Error saat menyimpan tugas ke database: {str(e)}"


@mcp.tool()
def read_task(root_path: str, task_name: str) -> str:
    """
    Membaca detail lengkap satu SOP/tugas repetitif dari database SQLite.
    Gunakan saat need to follow atau review satu SOP spesifik tanpa membaca seluruh bank.
    """
    norm_path = normalize_path(root_path)
    logger.info(f"Membaca detail task '{task_name}' untuk proyek di {norm_path}")

    try:
        with get_db_connection(norm_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM projects WHERE root_path = ?", (norm_path,))
            project = cursor.fetchone()

            if not project:
                return f"Error: Proyek di '{norm_path}' belum diinisialisasi."

            project_id = project["id"]
            cursor.execute(
                "SELECT * FROM tasks WHERE project_id = ? AND task_name = ?",
                (project_id, task_name)
            )
            task = cursor.fetchone()

            if not task:
                return f"Error: Task '{task_name}' tidak ditemukan di proyek '{norm_path}'."

            return (
                f"## SOP: {task['task_name']}\n"
                f"**Deskripsi:** {task['description']}\n"
                f"**Files to Modify:** {task['files_to_modify'] or '-'}\n"
                f"**Steps:**\n{task['steps']}\n"
                f"**Gotchas:** {task['gotchas'] or '-'}\n"
                f"**Last Performed:** {task['last_performed']}"
            )
    except Exception as e:
        logger.error(f"Error saat membaca task: {str(e)}")
        return f"Error: {str(e)}"


def main():
    logger.info("Memulai MCP Memory Bank SQLite Server via STDIO...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()