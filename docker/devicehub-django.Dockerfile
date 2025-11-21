FROM python:3.11.14-bookworm

# last line is dependencies for weasyprint (for generating pdfs in lafede pilot) https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#debian-11
RUN apt update && \
    apt-get install -y \
    python3-xapian \
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

# TODO I don't like this, but the whole ereuse-dpp works with user 1000 because of the volume mapping
#   thanks https://stackoverflow.com/questions/70520205/docker-non-root-user-best-practices-for-python-images
RUN adduser --home /opt/devicehub-django -u 1000 app

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

COPY . .
COPY docker/devicehub-django.entrypoint.sh /

# TODO this is bad for our main server
#   with the "next" docker things to apply this is no longer needed
#   or will not harm anymore
#
# no, we really need this until we apply all idhub docker perks
RUN chown -R app:app /opt/devicehub-django

USER app
ENTRYPOINT sh /devicehub-django.entrypoint.sh
