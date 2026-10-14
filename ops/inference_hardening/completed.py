from .contracts import digest
def completed_model(record,quality_raw,valid_trial):
    try:
        return record.get("status")=="PASS" and record["quality"]["status"]=="PASS" and record["quality"]["raw_sha"]==digest(quality_raw) and len({r["id"] for r in record["trials"] if valid_trial(r)})==21
    except (KeyError,OSError,TypeError):return False
