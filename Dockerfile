FROM python:3.12-slim

# OCP/VTK need OpenGL and OpenMP stubs even in headless mode
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (heavy layer, cached unless deps change)
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    "cadquery==2.7.0" \
    "cadquery-ocp==7.8.1.1.post1" \
    "cqgridfinity==0.5.7" \
    "cqkit==0.5.8" \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.34"

# Copy application code
COPY src/ src/

EXPOSE 8000
CMD ["uvicorn", "gridfinity_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
