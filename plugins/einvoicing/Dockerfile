FROM python:3.12-slim
WORKDIR /opt/einvoicing
COPY . /opt/einvoicing
ENV PYTHONPATH=/opt/einvoicing
RUN pip install --no-cache-dir fastapi uvicorn sqlalchemy cryptography pyjwt
EXPOSE 8090
CMD ["python", "-m", "uvicorn", "einvoicing.main:app", "--host", "0.0.0.0", "--port", "8090"]
