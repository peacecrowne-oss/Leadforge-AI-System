FROM python:3.11-slim

WORKDIR /app

# Install dependencies first so Docker can cache this layer independently
# of application source changes.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the backend source.
COPY . /app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
