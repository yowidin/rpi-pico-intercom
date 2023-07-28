try:
    import network
    USE_MOCK_WIFI = False
except ModuleNotFoundError:
    USE_MOCK_WIFI = True

import json
import time


class MockWifi:
    def __init__(self):
        pass

    def is_connected(self):
        return True

    def scan(self):
        return [(b'First', b'ABCDEF', 11, -44, 5, 3), (b'Second', b'FEDCBA', 11, -42, 5, 2),
                (b'Third', b'012345', 1, -62, 5, 2)]

    def get_mac(self):
        return b'12345'

    def update_config(self, ssid: str, password: str):
        # Nothing to do here
        return


class PicoWiFi:
    COUNTRY_CODE = 'DE'
    HOST_NAME = 'Intercom'
    DEFAULT_SSID = 'RpiIntercom'
    DEFAULT_PASSWORD = 'HostMePlenty'
    CONFIG_FILE = 'config.json'
    CONNECTION_RETRIES = 10

    def __init__(self):
        self.ssid = PicoWiFi.DEFAULT_SSID
        self.password = PicoWiFi.DEFAULT_PASSWORD
        self.should_host = self._load_config()
        self.wlan = None

        # Always set up the country code, otherwise the network won't start
        network.country(PicoWiFi.COUNTRY_CODE)
        network.hostname(PicoWiFi.HOST_NAME)

        if self.should_host:
            self._host()
        else:
            self._connect()

    def _host(self):
        print(f'Hosting an Access point {self.ssid} / {self.password}')

        self.wlan = network.WLAN(network.AP_IF)
        self.wlan.config(essid=self.ssid, password=self.password)
        self.wlan.active(True)

        if not self._wait_for_connection():
            print('Could not host the access point, rebooting')

            from machine import reset
            reset()

    def _connect(self):
        print(f'Connecting to {self.ssid} / {self.password}')

        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.wlan.connect(self.ssid, self.password)

        print('Waiting for connection...')
        if not self._wait_for_connection():
            self.wlan.disconnect()

            # Reset to the default SSID and password
            self.ssid = PicoWiFi.DEFAULT_SSID
            self.password = PicoWiFi.DEFAULT_PASSWORD

            # We couldn't connect, try hosting instead
            self.should_host = True
            self._host()

    def _wait_for_connection(self) -> bool:
        for i in range(PicoWiFi.CONNECTION_RETRIES):
            status = self.wlan.status()
            print(f'Waiting for connection: {status}')

            if status == network.STAT_IDLE or status == network.STAT_CONNECTING:
                time.sleep(1)
            elif status == network.STAT_WRONG_PASSWORD:
                print('Wrong password')
                break
            elif status == network.STAT_NO_AP_FOUND:
                print('No AP found')
                break
            elif status == network.STAT_CONNECT_FAIL:
                print('Connection failed')
                break
            elif status == network.STAT_GOT_IP:
                print('Connected')
                break

        status = self.wlan.status()
        print(f'Waiting done: {status}')
        return status == network.STAT_GOT_IP

    def _load_config(self) -> bool:
        """ :return True if we should host as access point """
        try:
            with open(PicoWiFi.CONFIG_FILE, 'r') as f:
                contents = f.read()
                print(f'File contents: {contents}')
                config = json.loads(contents)
                self.ssid = config['ssid']
                self.password = config['password']
                return False
        except Exception as e:
            print(f'Config load failed: {e}')
            return True

    def is_connected(self):
        return not self.should_host

    def scan(self):
        return self.wlan.scan()

    def get_mac(self):
        return self.wlan.config('mac')

    def update_config(self, ssid: str, password: str):
        with open(PicoWiFi.CONFIG_FILE, 'w') as f:
            config = {'ssid': ssid, 'password': password}
            contents = json.dumps(config)
            f.write(contents)
            f.flush()

        # Reboot and try to connect to the network, instead of hosting it
        from machine import reset
        reset()


class WiFi:
    def __init__(self):
        self.implementation = MockWifi() if USE_MOCK_WIFI else PicoWiFi()

    def is_connected(self):
        return self.implementation.is_connected()

    def scan(self):
        return self.implementation.scan()

    def get_mac(self):
        return self.implementation.get_mac()

    def update_config(self, ssid: str, password: str):
        return self.implementation.update_config(ssid, password)
