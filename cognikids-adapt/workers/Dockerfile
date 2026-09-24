FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

# Comando padrão — cada serviço no docker-compose.yml sobrescreve com o
# worker que deve rodar (worker_analysis.py, worker_profile.py, etc.), já
# que os quatro workers compartilham a mesma imagem/dependências.
CMD ["python", "worker_ingestion.py"]
