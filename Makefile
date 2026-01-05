run:
	python main.py

start:
	pm2 start --interpreter uv -- run main.py