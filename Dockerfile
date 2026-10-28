FROM python:3.11-slim

# Runtime libraries required by opencv-python
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies before copying source for better layer caching.
# We list the pyproject.toml runtime deps explicitly so the layer is
# invalidated only when deps change, not on every source edit.
COPY pyproject.toml .
RUN pip install --no-cache-dir \
        numpy matplotlib scipy pandas h5py Pillow \
        "fastapi>=0.110" "pydantic>=2.5" "uvicorn[standard]>=0.29" \
        "python-multipart>=0.0.9" "httpx>=0.27" jsonschema \
        scikit-image scikit-learn opencv-python

COPY src/ src/
RUN pip install --no-cache-dir --no-deps -e .

# Bind on 0.0.0.0 so the port is reachable from other containers.
ENV BRANDLENS_HOST=0.0.0.0

EXPOSE 8000

CMD ["python", "-m", "brandlens.api"]
