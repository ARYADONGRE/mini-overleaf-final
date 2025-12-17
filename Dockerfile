FROM python:3.9-slim

# Install the "Academic Super-Set" of LaTeX packages
# FIXED: Replaced 'texlive-generic-recommended' with 'texlive-plain-generic'
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-bibtex-extra \
    texlive-publishers \
    texlive-science \
    texlive-plain-generic \
    texlive-lang-english \
    latexmk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]