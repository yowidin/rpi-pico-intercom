#!/usr/bin/env bash
source ./venv/bin/activate

mpremote mkdir www
mpremote cp www-raw/client.html :www/client.html
mpremote cp www-raw/server.html :www/server.html

mpremote cp main.py :main.py
mpremote cp server.py :server.py
mpremote cp servo.py :servo.py
mpremote cp wifi.py :wifi.py

mpremote reset
sleep 2
mpremote repl

deactivate