"""Actual SQLite metadata backup/restore; not full Kubernetes/object-store disaster recovery."""
from pathlib import Path
import sqlite3,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def main():
    e=ROOT/"Evidence/v1";dest=e/"backups";dest.mkdir(exist_ok=True,mode=0o700)
    original=e/"modelops.sqlite";backup=dest/"metadata.sqlite";restored=dest/"restored.sqlite"
    def tables(conn):
        names=[x[0] for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name:conn.execute('SELECT COUNT(*) FROM "'+name.replace('"','""')+'"').fetchone()[0] for name in sorted(names)}
    with sqlite3.connect(original) as src,sqlite3.connect(backup) as dst:
        before=tables(src);src.backup(dst)
    with sqlite3.connect(backup) as src,sqlite3.connect(restored) as dst:src.backup(dst)
    with sqlite3.connect(restored) as conn:
        after=tables(conn);integrity=conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign=list(conn.execute("PRAGMA foreign_key_check"))
        ids={name:[x[0] for x in conn.execute('SELECT id FROM "'+name+'" ORDER BY id')]
            for name in ["model_artifacts","finetune_jobs","evaluation_records","deployments"]}
    with sqlite3.connect(original) as conn:
        source_ids={name:[x[0] for x in conn.execute('SELECT id FROM "'+name+'" ORDER BY id')] for name in ids}
    hashes={str(p.relative_to(e)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [backup,restored]}
    valid=before==after and ids==source_ids and integrity=="ok" and not foreign
    (e/"native-backup-restore.json").write_text(json.dumps({"status":"PASS" if valid else "FAILED",
       "schema":"modelops.native-metadata-backup.v1","source":str(original),"backup":str(backup),
       "restored":str(restored),"row_counts":after,"ids_preserved":ids==source_ids,"integrity":integrity,
       "foreign_key_errors":foreign,"hashes":hashes,
       "scope":"Real SQLite metadata restore; checkpoint binaries remain in original private owned storage; not full DR"},indent=2))
    if not valid:raise RuntimeError("Metadata recovery verification failed")
    print("NATIVE_METADATA_RESTORE_PASS",after)
if __name__=="__main__":main()
