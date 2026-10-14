import json
from ops.observability.stream_metrics import StreamMeter

def event(value):
    return ("data: "+json.dumps(value)+"\n\n").encode()

def test_fragmented_role_frame_is_not_first_token_and_usage_is_not_content():
    meter=StreamMeter(start=10.0)
    role=event({"choices":[{"delta":{"role":"assistant","content":""}}]})
    text=event({"choices":[{"delta":{"content":"Paris"}}]})
    usage=event({"choices":[],"usage":{"completion_tokens":2}})
    meter.feed(role+text[:7],now=10.1)
    assert meter.first_token_s is None
    meter.feed(text[7:]+usage+b"data: [DONE]\n\n",now=10.2)
    assert round(meter.first_token_s,4)==0.2
    assert meter.output_tokens==2
    assert meter.done and meter.error is None

def test_completions_text_and_multiline_network_chunks():
    meter=StreamMeter(start=0)
    data=event({"choices":[{"text":"one"}]})+event({"usage":{"completion_tokens":1},"choices":[]})
    for i in range(0,len(data),3):meter.feed(data[i:i+3],now=0.5)
    assert meter.first_token_s==0.5 and meter.output_tokens==1

def test_missing_usage_remains_unknown_not_estimated():
    meter=StreamMeter(start=0)
    meter.feed(event({"choices":[{"text":"three words here"}]})+b"data: [DONE]\n\n",now=1)
    assert meter.output_tokens is None

def test_stream_error_and_invalid_usage_are_visible():
    meter=StreamMeter(start=0)
    meter.feed(event({"error":{"message":"engine error"}}),now=1)
    assert meter.error=="upstream_stream_error"
    meter=StreamMeter(start=0)
    meter.feed(event({"usage":{"completion_tokens":-1},"choices":[]}),now=1)
    assert meter.error=="invalid_token_usage"

def test_oversized_event_is_rejected_without_buffer_growth():
    meter=StreamMeter(start=0,max_event_bytes=50)
    meter.feed(b"x"*51,now=1)
    assert meter.error=="oversized_sse_event"
