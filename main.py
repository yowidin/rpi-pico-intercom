from server import run
from wifi import USE_MOCK_WIFI
import time

time.sleep(5)

try:
    run()
except Exception as e:
    print(f'Error: {e}')

    if not USE_MOCK_WIFI:
        import machine
        machine.reset()
