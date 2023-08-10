import socket
import json
from typing import List, Dict, Optional

import os

from wifi import WiFi, USE_MOCK_WIFI
from servo import Servo

LINE_SEPARATOR = b'\r\n'


def get_file_size(path: str) -> int:
    return os.stat(path)[6]


class Stream:
    BUF_SIZE = 128

    def __init__(self, sock: socket.socket):
        self.socket = sock
        self.contents = bytearray()
        self.read_buf = bytearray(b'\x00' * Stream.BUF_SIZE)

    def read_some(self):
        num_bytes = self.socket.recv_into(self.read_buf)
        self.contents += self.read_buf[0:num_bytes]

    def read_until(self, token: bytes) -> bytearray:
        while True:
            idx = self.contents.find(token)
            if idx == -1:
                self.read_some()
            else:
                break

        result = self.contents[0:idx]
        self.contents = self.contents[idx + len(token):]
        return result

    def read_line(self) -> bytearray:
        return self.read_until(LINE_SEPARATOR)

    def read_exact(self, num_bytes: int) -> bytearray:
        while len(self.contents) < num_bytes:
            self.read_some()

        result = self.contents[0:num_bytes]
        self.contents = self.contents[num_bytes:]
        return result


class Request:
    def __init__(self, sock: socket.socket):
        self.stream = Stream(sock)

        request_line = self.stream.read_line()
        self.method, self.uri, self.protocol = request_line.decode('utf-8').split()
        self.headers = self._parse_headers()
        self.data = self._parse_body()

    def _parse_headers(self) -> Dict[str, str]:
        result = {}
        while True:
            header_line = self.stream.read_line()
            if len(header_line) == 0:
                # An empty line denotes BODY start
                break

            name, value = header_line.decode('utf-8').split(': ', 1)
            result[name.lower()] = value
        return result

    def _parse_body(self) -> Optional[dict]:
        if 'content-length' not in self.headers:
            return None

        content_length = int(self.headers['content-length'])

        if 'content-type' not in self.headers:
            return None

        content_type = self.headers['content-type']

        if content_type != 'application/json':
            return None

        body_bytes = self.stream.read_exact(content_length)
        return json.loads(body_bytes.decode('utf-8'))

    def __str__(self):
        return f'{self.method} {self.uri}'


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
            except Exception as e:
                print(f'Error: {e}')
                if self.client is not None:
                    self.respond_with_error(500)
            finally:
                if self.client is not None:
                    self.client.close()
                    self.client = None

    def _handle_one(self):
        request = Request(self.client)
        self.request_handler(self, request)

    def _send_all(self, data: bytes):
        while len(data) != 0:
            bytes_sent = self.client.send(data)
            data = data[bytes_sent:]

    def write(self, data: bytes):
        self._send_all(data)

    def write_return_code(self, code: int):
        reason = self.RESPONSE_CODES.get(code, 'Unknown reason')
        return self.write(f"HTTP/1.1 {code} {reason}\r\n".encode())

    def write_content_type(self, content_type: str):
        return self.write(f"Content-type: {content_type}\r\n".encode())

    def write_delimiter(self):
        self.write(b'\r\n')

    def respond_with_error(self, code: int):
        self.write_return_code(code)
        self.write_content_type('text/html')
        self.write_delimiter()

        reason = self.RESPONSE_CODES.get(code, 'Unknown reason')
        message = self.ERROR_CODE_TEMPLATE % {'code': code, 'reason': reason}
        self.write(message.encode())


def handle_one_file(server: Server, path: str):
    if path.endswith('js'):
        content_type = 'text/javascript'
    elif path.endswith('css'):
        content_type = 'text/css'
    elif path.endswith('html'):
        content_type = 'text/html'
    else:
        content_type = 'text/plain'

    file_size = get_file_size(path)
    with open(path, 'r') as f:
        server.write_return_code(200)
        server.write_content_type(content_type)
        server.write(f'Content-Length: {file_size}\r\n'.encode())
        server.write_delimiter()

        buf_size = 100
        buf = f.read(buf_size)
        while len(buf) != 0:
            server.write(buf.encode())
            buf = f.read(buf_size)


def handle_scan(server: Server, _: Request):
    scan_results = server.wifi.scan()

    result = []
    for line in scan_results:
        result.append([line[0].decode('utf-8'), line[3]])

    return result


def handle_update_config(server: Server, payload: Request):
    server.wifi.update_config(payload.data['name'], payload.data['password'])
    return {}


def handle_set_state(server: Server, payload: Request):
    if payload.data['is_on']:
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


def handle_post(server: Server, request: Request):
    methods = {
        'scan': handle_scan,
        'config': handle_update_config,
        'set': handle_set_state,
        'get': handle_get_state,
        'mac': handle_get_mac,
    }

    path = request.uri[1:]

    if path not in methods:
        server.write_return_code(404)
        server.write_content_type('application/json')
        server.write_delimiter()
        server.write(b'{}')
    else:
        server.write_return_code(200)
        server.write_content_type('application/json')
        server.write_delimiter()

        response = methods[path](server, request)
        response_json = json.dumps(response)
        server.write(response_json.encode())


def basic_handler(server: Server, request: Request):
    print(f'Request: {request}')

    if request.method == 'POST':
        handle_post(server, request)
        return

    if request.method != 'GET':
        server.respond_with_error(400)
        return

    content_root = 'www/'

    is_connected = server.wifi.is_connected()
    if request.uri == '/':
        if is_connected:
            path = 'client.html'
        else:
            path = 'server.html'
    else:
        server.respond_with_error(404)
        return

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
