#!/usr/bin/env bash
source ./venv/bin/activate

# mpremote cp -r www/ :
mpremote cp www/client.html :www/client.html
mpremote cp www/server.html :www/server.html

mpremote cp main.py :main.py
mpremote cp server.py :server.py
mpremote cp servo.py :servo.py
mpremote cp wifi.py :wifi.py

mpremote reset
sleep 2
mpremote repl

deactivate