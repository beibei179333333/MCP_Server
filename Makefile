.PHONY: install run test docker docker-up docker-down logs clean fmt

VENV  := .venv
PY    := $(VENV)/bin/python
PIP   := $(VENV)/bin/pip

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@if [ ! -f .env ]; then cp .env.example .env; echo "→ 已生成 .env，请编辑后启动"; fi

run:
	$(PY) run.py

test:
	$(PY) -m pytest -q

docker:
	docker build -t telegram-allinone-bot:latest .

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

logs:
	@if [ -f logs/bot.log ]; then tail -f logs/bot.log; else docker compose logs -f bot; fi

clean:
	rm -rf $(VENV) __pycache__ */__pycache__ */*/__pycache__ logs/*.log data/bot.db data/*.session-journal

fmt:
	$(PY) -m black bot/ run.py 2>/dev/null || true
