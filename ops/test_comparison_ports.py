import socket
import pytest
from ops.run_model_comparison import available

def test_recently_closed_reusable_listener_is_not_reported_as_active():
    listener=socket.socket()
    listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind(("127.0.0.1",0));port=listener.getsockname()[1];listener.listen()
    client=socket.create_connection(("127.0.0.1",port));accepted,_=listener.accept()
    accepted.close();client.recv(1);client.close();listener.close()
    available(port)

def test_active_listener_is_never_taken_over():
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind(("127.0.0.1",0));listener.listen()
        with pytest.raises(OSError):available(listener.getsockname()[1])
