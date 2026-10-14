import socket,threading,time
from . import runtime
def test_waits_for_port_released_after_owned_server_cleanup():
    s=socket.socket();s.bind(("127.0.0.1",0));s.listen();port=s.getsockname()[1]
    threading.Thread(target=lambda:(time.sleep(.25),s.close()),daemon=True).start()
    start=time.monotonic();runtime.wait_port_release(port,2)
    assert time.monotonic()-start>=.2
def test_does_not_adopt_or_terminate_unknown_listener():
    s=socket.socket();s.bind(("127.0.0.1",0));s.listen()
    import pytest
    with pytest.raises(RuntimeError):runtime.wait_port_release(s.getsockname()[1],.1)
    assert s.fileno()>=0;s.close()
