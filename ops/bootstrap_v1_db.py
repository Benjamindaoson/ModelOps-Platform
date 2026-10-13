"""Upgrade only the owned v1 development SQLite database, with verified backup."""
from pathlib import Path
import sqlite3,os,json,sys
ROOT=Path(__file__).resolve().parents[1]
def main():
    db=ROOT/"Evidence/v1/modelops.sqlite"
    backup=db.with_name("modelops.pre-serving.sqlite")
    with sqlite3.connect(db) as source:
        cols={x[1] for x in source.execute("PRAGMA table_info(deployments)")}
        if "quantization" in cols:return 0
        if "model_type" not in {x[1] for x in source.execute("PRAGMA table_info(model_artifacts)")}:
            raise RuntimeError("Not a verified v1 development schema")
        if "worker" not in {x[1] for x in source.execute("PRAGMA table_info(finetune_jobs)")}:
            raise RuntimeError("Not a verified training lifecycle schema")
        with sqlite3.connect(backup) as destination:source.backup(destination)
    sys.path.insert(0,str(ROOT/"control-plane"))
    from alembic import command
    from alembic.config import Config
    os.environ["MODELOPS_DATABASE_URL"]="sqlite:///"+str(db)
    cfg=Config(str(ROOT/"control-plane/alembic.ini"))
    command.stamp(cfg,"0005_training_state")
    command.upgrade(cfg,"head")
    with sqlite3.connect(db) as source:check=source.execute("PRAGMA integrity_check").fetchone()[0]
    (ROOT/"Evidence/v1/live-sqlite-migration.json").write_text(json.dumps({
      "owned_database":str(db),"backup":str(backup),"revision":"0006_serving_configuration","integrity_check":check},indent=2))
    if check!="ok":raise RuntimeError("Database integrity failed")
    return 0
if __name__=="__main__":raise SystemExit(main())
