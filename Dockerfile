# Multi-architecture (linux/amd64, linux/arm64) image for the pinging tools.
# python:3.12-slim publishes both arches, so this Dockerfile builds as-is on
# ARM and AMD hosts and via `docker buildx` for cross-building.
FROM python:3.12-slim

# tzdata lets the CSV send-timestamps use a local timezone via `-e TZ=...`
# (defaults to UTC otherwise).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (numpy for measurement/stats; matplotlib/seaborn/scipy
# for plotting). Installed from prebuilt wheels for both arches.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Application code.
COPY ping3.py main.py plot_from_file.py /app/
COPY pingpkg/ /app/pingpkg/

# Run headless: matplotlib saves PNGs without a GUI backend.
ENV MPLBACKEND=Agg

# Measurement outputs (ping<count>.csv and the *.png plots) are written to the
# working directory; mount a host directory at /data to keep them.
WORKDIR /data
VOLUME ["/data"]

# `docker run <img>`            -> runs ping3.py (interactive prompts)
# `docker run <img> /app/plot_from_file.py ping100.csv` -> runs the plotter
ENTRYPOINT ["python3"]
CMD ["/app/ping3.py"]
