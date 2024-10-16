web: playwright install && playwright install-deps && unzip -o compressedState.zip dominos/* -d ./ && gunicorn --worker-class eventlet -w 1 flaskdemo:app
