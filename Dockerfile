# Use a lightweight Python base image
FROM python:3.9-slim

# Install minimal LaTeX dependencies
# texlive-latex-base: The core engine
# texlive-fonts-recommended: Standard fonts to avoid errors
# texlive-latex-extra: Common packages like 'article', 'geometry' (Optional, adds size)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-fonts-recommended \
    texlive-latex-extra \
    && rm -rf /var/lib/apt/lists/*

# Set up the app
WORKDIR /app
COPY . /app

# Install Python requirements
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port
EXPOSE 5000

# Command to run the app using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]