run:
	uv run main.py

start:
	pm2 start --interpreter uv -- run main.py