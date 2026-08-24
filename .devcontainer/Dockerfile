FROM texlive/texlive:latest

RUN apt-get update && apt-get install -y --no-install-recommends python3-pip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt .
RUN pip install --break-system-packages --no-cache-dir -r requirements.txt

COPY . .

CMD ["bash"]
