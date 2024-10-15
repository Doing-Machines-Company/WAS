release: playwright install && unzip -o compressedState.zip dominos/* -d ./
web: gunicorn --worker-class eventlet -w 1 flaskdemo:app
