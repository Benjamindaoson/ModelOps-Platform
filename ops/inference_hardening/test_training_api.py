from modelops.schemas import FineTuneIn
from pipelines.training.options import training_options
def test_training_job_preserves_checkpointing_and_accumulation():
    r=FineTuneIn(name="hardening-job",artifact_id="base",dataset_id="dataset",output_name="hardening-output",framework="transformers",gradient_checkpointing=True,gradient_accumulation_steps=2)
    assert r.model_dump()["gradient_checkpointing"] is True
    assert training_options(r.model_dump())=={"gradient_accumulation_steps":2,"gradient_checkpointing":True}
