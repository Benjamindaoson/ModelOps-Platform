"""Semantic training configuration and token-weighted accumulation contracts."""
import hashlib,json

def training_options(c):
    accum=c.get("gradient_accumulation_steps",1);checkpoint=c.get("gradient_checkpointing",False)
    if not isinstance(accum,int) or isinstance(accum,bool) or not 1<=accum<=32:raise ValueError("Invalid gradient accumulation")
    if not isinstance(checkpoint,bool):raise ValueError("Gradient checkpointing must be boolean")
    return {"gradient_accumulation_steps":accum,"gradient_checkpointing":checkpoint}

def semantic_sha(c):
    keys=("method","steps","seed","batch_size","lr","lora_rank","lora_alpha","max_seq_length","dataset_sha256","base_sha256")
    identity={k:c.get(k) for k in keys};identity.update(training_options(c))
    return hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()

def microbatch_weights(labels):
    counts=[sum(x!=-100 for x in row[1:]) for row in labels];total=sum(counts)
    if not total:raise ValueError("No supervised causal tokens")
    return [c/total for c in counts]

def verify_resume_identity(saved,c):
    if saved.get("config_sha") and saved["config_sha"]!=semantic_sha(c):raise ValueError("Resume semantic configuration changed")
    if not saved.get("config_sha") and training_options(c)!={"gradient_accumulation_steps":1,"gradient_checkpointing":False}:
        raise ValueError("Legacy resume cannot change new training options")
