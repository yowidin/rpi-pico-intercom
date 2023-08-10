import machine

from server import run
import time


time.sleep(5)

try:
    run()
except Exception as e:
    print(f'Error: {e}')
    machine.reset()
