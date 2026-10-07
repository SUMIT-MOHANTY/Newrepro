import socket
import threading

def forward(src, dst):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 8085))
    server.listen(50)
    print("Gateway proxy listening on 0.0.0.0:8085 -> 172.17.0.2:80", flush=True)

    while True:
        client, addr = server.accept()
        upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            upstream.connect(('172.17.0.2', 80))
            t1 = threading.Thread(target=forward, args=(client, upstream), daemon=True)
            t2 = threading.Thread(target=forward, args=(upstream, client), daemon=True)
            t1.start()
            t2.start()
        except Exception as e:
            print("Upstream error:", e, flush=True)
            client.close()

if __name__ == '__main__':
    main()
