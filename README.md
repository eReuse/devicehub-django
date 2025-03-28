# Device Hub

DeviceHub is an IT Asset Management System focused on reusing devices, created under the [eReuse.org](https://www.ereuse.org) project.

## Overview

DeviceHub aims to:

- Provide a common IT Asset Management platform for donors, receivers, and IT professionals.
- Automatically collect, analyze, and share device metadata while ensuring privacy and traceability.
- Integrate with existing IT Asset Management Systems.
- Operate in a decentralized manner.

DeviceHub primarily works with three types of objects:

1. **Devices**: Including computers, smartphones, and their components.
2. **Events**: Actions performed on devices (e.g., Repair, Allocate).
3. **Accounts**: Users who perform events on devices.

## Installation

Assuming a host with debian stable

### Quickstart

For a quick start with pre-generated sample data, DeviceHub can be run directly with docker. To do so, from the root of the project run:

```bash
./docker-reset.sh
```

Note that everytime you perform the `docker-reset.sh` script, all data is lost.

Also there is a demo running in http://demo.ereuse.org/. The token for accessing the instance will be always: `token=5018dd65-9abd-4a62-8896-80f34ac66150`, but the instance will be reset every day at 4 am.

For production needs, review and change .env file properly

### Production-ready Setup

> **Warning**
> DeviceHub is not ready for production yet. The following are work in progress instructions.


The recommended way to run DeviceHub in production is using Docker. This allows for easy deployment and management of the application and its dependencies.

#### Prerequisites

Devicehub can run comfortably in a server with 2GB of RAM and 2 CPU cores. The recommended way to run DeviceHub in production is using Docker. This allows for easy deployment and management of the application and its dependencies.

Devicehub must be ran with UID 1000, so is recommended to create a user with this UID. This can be done by running the following command:

```bash
sudo useradd -u 1000 -m devicehub
sudo adduser devicehub docker
```

Clone the repository:

```bash
git clone https://farga.pangea.org/ereuse/devicehub-django
cd devicehub-django
cp .env.example .env
```

TODO Revisar https://gitea.pangea.org/ereuse/devicehub-django/pulls/58

Now, just run the following command to start the application:

```bash
docker-compose up -d
```

#### Running Devicehub with HTTPS

The recommended way to run DeviceHub with HTTPS is using a reverse proxy. The following example uses Nginx, but you can use any other reverse proxy. Here there is an example of how to run DeviceHub with HTTPS using Nginx:

```nginx
server {
  root /var/www/html;
  index index.html index.htm;

  listen 443;
  server_name YOUR_FQDN;

#  include tls_params;
  client_max_body_size 10G;
  client_body_buffer_size 400M;

  location / {
    proxy_pass http://INTERNAL_DEVICEHUB_IP:8001;
    include proxy_params;
  }

    ssl_certificate /etc/letsencrypt/live/YOUR_FQDN/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/YOUR_FQDN/privkey.pem; # managed by Certbot
}

server {
    if ($host = YOUR_FQDN) {
        return 301 https://$host$request_uri;
    } # managed by Certbot

  listen 80;
  server_name YOUR_FQDN;
  return 404; # managed by Certbot
}
```

Note that `proxy_params` contains:

```nginx
proxy_set_header Host $http_host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Robots-Tag "noindex, nofollow, nosnippet, noarchive";
proxy_set_header X-Permitted-Cross-Domain-Policies "none";
proxy_connect_timeout 600;
proxy_send_timeout 600;
proxy_read_timeout 600;
```

## Running from baremetal

### Prerequisites

- Python 3.10
- pip
- virtualenv

Specially when developing, is quite convenient to run DeviceHub from a virtual environment. To start with this deployment, create a virtual environment to isolate our project dependencies:

```bash
python -m venv env
source env/bin/activate
pip install -r requirements.txt
```

### System Dependencies

#### Xapian

Now, install the xapian dependencies (xapian library and python bindings)

```bash
sudo apt-get install python3-xapian libxapian-dev
```

Allow the virtual environment to use system-installed packages:

```bash
export PYTHONPATH="${PYTHONPATH}:/usr/lib/python3/dist-packages"
```

#### Environment Variables

Now, configure the environment variables. For this, we will expand a `.env` file. For a quickstart with localhost, you can use the default values in the `.env.example` file:

```bash
cp .env.example .env
```

Now, expand the environment variables:

```bash
source .env
```

### Migrations

Now, apply migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

Also, we can add some dummy data into the database to play along:

```bash
python manage.py add_institution Pangea
python manage.py add_user Pangea user@example.org 1234
python manage.py up_snapshots example/snapshots/ user@example.org
```

### Run DeviceHub

Finally, we can run the DeviceHub service by running:

```bash
python manage.py runserver
```

### Clean up

To clean up the deployment and start fresh, just delete Django's database:

```bash
rm db/*
```

## License

DeviceHub is released under the [GNU Affero General Public License v3.0](LICENSE).
