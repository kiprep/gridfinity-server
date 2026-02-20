FROM python:3.12-slim

# OCP/VTK need OpenGL and X11 stubs even in headless mode
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    libxrender1 libxext6 libx11-6 libsm6 libice6 libxi6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (heavy layer, cached unless deps change)
RUN pip install --no-cache-dir \
    "cadquery==2.7.0" \
    "cadquery-ocp==7.8.1.1.post1" \
    "cqgridfinity==0.5.7" \
    "cqkit==0.5.8" \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.34"

# Copy application code and install the package
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir --no-deps . \
    && python -c "from gridfinity_server.main import app; print('Import OK')"

EXPOSE 8080
CMD ["sh", "-c", "uvicorn gridfinity_server.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
