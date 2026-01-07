FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy ETCS simulation code and configs
COPY . /app

ENV PYTHONUNBUFFERED=1

CMD ["python", "train_dmi.py"]
