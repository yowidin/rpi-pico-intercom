import socket
import json

from io import IOBase

from wifi import WiFi
from servo import Servo


class Server:
    ERROR_CODE_TEMPLATE = """\
    <html>
        <head>
            <title>Error</title>
        </head>
        <body>
            <h1>%(code)d %(reason)s</h1>
        </body>
    </html>
    """

    RESPONSE_CODES = {
        200: 'OK',
        400: 'Bad Request',
        401: 'Unauthorized',
        404: 'Not Found',
        405: 'Method Not Allowed',
        500: 'Internal Server Error',
    }

    def __init__(self, request_handler, wifi: WiFi, servo: Servo, host='0.0.0.0', port=80):
        self.request_handler = request_handler
        self.wifi = wifi
        self.servo = servo

        self.host = host
        self.port = port
        self.address = self._get_bind_address()

        self.listen_socket = socket.socket()
        self.client = None
        self._listen()

    @staticmethod
    def _get_bind_address():
        ip_address_list = [x[-1] for x in socket.getaddrinfo('0.0.0.0', 80)]
        return ip_address_list[0]

    def _listen(self):
        self.listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listen_socket.bind(self.address)
        self.listen_socket.listen(1)

        while True:
            try:
                self.client, _ = self.listen_socket.accept()
                self._handle_one()
            except OSError as e:
                print(f'Error: {e}')
                pass
            finally:
                if self.client is not None:
                    self.client.close()
                    self.client = None

    def _handle_one(self):
        request = self.client.recv(1024)

        if len(request) == 0:
            return

        request = request.decode('utf-8')
        lines = request.split('\r\n')

        method, path, version = lines[0].split(' ')

        delimiter = None
        for i, line in enumerate(lines):
            if len(line) == 0:
                delimiter = i
                break

        payload = None
        if delimiter is not None:
            payload = lines[delimiter + 1]
            if len(payload) == 0:
                payload = None
            else:
                payload = json.loads(payload)

        self.request_handler(self, method, path, payload)

    def send(self, text):
        if isinstance(text, bytearray):
            self.client.send(text)
        else:
            self.client.send(text.encode('utf-8'))

    def flush(self):
        self.client.flush()

    def write_return_code(self, code: int):
        reason = self.RESPONSE_CODES.get(code, 'Unknown reason')
        return self.send(f"HTTP/1.1 {code} {reason}\r\n")

    def write_content_type(self, content_type: str):
        return self.send(f"Content-type: {content_type}\r\n")

    def write_delimiter(self):
        self.send('\r\n')

    def respond_with_error(self, code: int):
        self.write_return_code(code)
        self.write_content_type('text/html')
        self.write_delimiter()

        reason = self.RESPONSE_CODES.get(code, 'Unknown reason')
        self.send(self.ERROR_CODE_TEMPLATE % {'code': code, 'reason': reason})


def handle_one_file(server: Server, path: str):
    if path.endswith('js'):
        content_type = 'text/javascript'
    elif path.endswith('css'):
        content_type = 'text/css'
    elif path.endswith('html'):
        content_type = 'text/html'
    else:
        content_type = 'text/plain'

    with open(path, 'r') as f:
        server.write_return_code(200)
        server.write_content_type(content_type)
        server.write_delimiter()

        buf_size = 100
        buf = f.read(buf_size)
        while len(buf) != 0:
            server.send(buf)
            buf = f.read(buf_size)


def handle_scan(server: Server, _: dict):
    scan_results = server.wifi.scan()

    result = []
    for line in scan_results:
        result.append([line[0].decode('utf-8'), line[3]])

    return result


def handle_update_config(server: Server, payload: dict):
    server.wifi.update_config(payload['name'], payload['password'])
    return {}


def handle_set_state(server: Server, payload: dict):
    if payload['is_on']:
        server.servo.turn_on()
    else:
        server.servo.turn_off()
    return {}


def handle_get_state(server: Server, _: dict):
    is_on = server.servo.is_on()
    is_off = server.servo.is_off()
    return {'is_on': is_on, 'is_off': is_off}


def handle_get_mac(server: Server, _: dict):
    raw_mac = server.wifi.get_mac()
    return [raw_mac.hex(':')]


def handle_post(server: Server, path: str, payload: dict):
    methods = {
        'scan': handle_scan,
        'config': handle_update_config,
        'set': handle_set_state,
        'get': handle_get_state,
        'mac': handle_get_mac,
    }

    path = path[1:]

    if path not in methods:
        server.write_return_code(404)
        server.write_content_type('application/json')
        server.write_delimiter()
        server.send('{}')
    else:
        server.write_return_code(200)
        server.write_content_type('application/json')
        server.write_delimiter()
        response = methods[path](server, payload)

        class SocketWriter(IOBase):
            def write(self, data):
                server.send(data)

        json.dump(response, SocketWriter())


def basic_handler(server: Server, method: str, path: str, payload: dict):
    print(f'Request: {method} {path}')

    if method == 'POST':
        handle_post(server, path, payload)
        return

    if method != 'GET':
        server.respond_with_error(400)
        return

    content_root = 'www/'

    is_connected = server.wifi.is_connected()
    if path == '/':
        if is_connected:
            path = 'client.html'
        else:
            path = 'server.html'

    full_path = content_root + path
    try:
        handle_one_file(server, full_path)
    except OSError:
        server.respond_with_error(404)


def run():
    wifi = WiFi()
    servo = Servo()
    Server(basic_handler, wifi, servo)


if __name__ == '__main__':
    run()
