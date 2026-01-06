FROM python:3.11.14-bookworm

# last line is dependencies for weasyprint (for generating pdfs in lafede pilot) https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#debian-11
RUN apt update && \
    apt-get install -y \
    python3-xapian \
    postgresql-client \
    gosu \
    git \
    sqlite3 \
    curl \
    jq \
    time \
    vim \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-cat \
    tesseract-ocr-spa \
    zbar-tools \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/devicehub-django

# reduce size (python specifics) -> src https://stackoverflow.com/questions/74616667/removing-pip-cache-after-installing-dependencies-in-docker-image
ENV PYTHONDONTWRITEBYTECODE=1
# here document in dockerfile src https://stackoverflow.com/questions/40359282/launch-a-cat-command-unix-into-dockerfile
RUN cat > /etc/pip.conf <<END
[install]
compile = no

[global]
no-cache-dir = True
END

COPY ./requirements.txt /opt/devicehub-django
RUN pip install -r requirements.txt
# TODO hardcoded, is ignored in requirements.txt
RUN pip install -i https://test.pypi.org/simple/ ereuseapitest==0.0.14

# TODO Is there a better way?
#   Set PYTHONPATH to include the directory with the xapian module
ENV PYTHONPATH="${PYTHONPATH}:/usr/lib/python3/dist-packages"

COPY . /opt/devicehub-django

COPY docker/devicehub-django.entrypoint.sh /

ENTRYPOINT sh /devicehub-django.entrypoint.sh
