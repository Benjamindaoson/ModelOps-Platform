from .release_stage import classified_quantization_failure
def test_config_dump_is_not_root_cause_evidence():
    assert not classified_quantization_failure("Args quantization=gptq\nZMQError: ipc path is longer than107 characters")
def test_actual_quantization_exception_is_required():
    assert classified_quantization_failure("ValueError: Cannot find the config file for gptq.")

def test_pydantic_native_quantization_error_is_classified():
    assert classified_quantization_failure("Value error, Cannot find the config file for gptq [type=value_error]")
