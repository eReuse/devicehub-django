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

> **Note**
> This docker container was designed to be setup with user `1000`, which correspond to default linux user. Hence not root user, or any other specific linux user. Sorry. We would like to fix this better and soon.

For a quick start with pre-generated sample data, DeviceHub can be run directly with docker. To do so, from the root of the project run:

```bash
git clone https://farga.pangea.org/ereuse/devicehub-django
cd devicehub-django
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
su - devicehub
```

Clone the repository:

```bash
git clone https://farga.pangea.org/ereuse/devicehub-django
cd devicehub-django
cp .env.example .env
```

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

### Baremetal Prerequisites

- Python 3.11
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

> **Note**
> If you're running a newer system like Debian 13 with Python 3.13+, the system `python3-xapian` package may be incompatible with Python 3.11. In this case, skip this section and follow the ["Alternative: Compiling Xapian from Sources"](#xapian-for-newer-systems-like-debian-13-ubuntu-2410) guide below.

Now, install the xapian dependencies (xapian library and python bindings)

```bash
sudo apt-get install python3-xapian libxapian-dev
```

Allow the virtual environment to use system-installed packages:

```bash
export PYTHONPATH="${PYTHONPATH}:/usr/lib/python3/dist-packages"
```

#### Xapian for newer systems (like Debian 13, Ubuntu 24.10+)

If you're running a newer system (like Debian 13, Ubuntu 24.10+) with Python 3.13+ where the system `python3-xapian` package is incompatible with older Python versions, you'll need to compile Xapian from sources for Python 3.11.

**Prerequisites:**

```bash
# Install build dependencies
sudo apt-get update
sudo apt-get install python3-sphinx python3-dev swig build-essential
```

##### Step 1: Set up Python 3.11 using pyenv

If you don't have pyenv installed:

```bash
# Install pyenv
curl https://pyenv.run | bash
# Restart your shell or run:
exec "$SHELL"
```

Install and set Python 3.11.10:

```bash
# Install Python 3.11.10
pyenv install 3.11.10

# Set it as the local version for this project directory
cd /path/to/devicehub-django
pyenv local 3.11.10
```

##### Step 2: Create virtual environment with Python 3.11

```bash
# Remove any existing virtual environment
rm -rf env

# Create new virtual environment with Python 3.11
python -m venv env
source env/bin/activate

# Verify Python version
python --version  # Should show Python 3.11.10
```

##### Step 3: Download and compile Xapian from sources

Download the Xapian core and bindings from the official repository:

```bash
# Download Xapian core and bindings (version 1.4.29)
wget https://oligarchy.co.uk/xapian/1.4.29/xapian-core-1.4.29.tar.xz
wget https://oligarchy.co.uk/xapian/1.4.29/xapian-bindings-1.4.29.tar.xz

# Extract the archives
tar -xf xapian-core-1.4.29.tar.xz
tar -xf xapian-bindings-1.4.29.tar.xz
```

First, build and install Xapian core:

```bash
# Build Xapian core
cd xapian-core-1.4.29
./configure --prefix=/usr/local
make
sudo make install

# Update library cache
sudo ldconfig
cd ..
```

Then, build the Python bindings:

```bash
# Navigate to xapian-bindings directory
cd xapian-bindings-1.4.29

# Make sure virtual environment is activated
source ../env/bin/activate

# Configure for Python 3.11
./configure --with-python3 PYTHON3=$(which python) PYTHON3_INC=$(python -c "import sysconfig; print(sysconfig.get_path('include'))")

# Build the bindings
make

# Copy the built module to your virtual environment
cd ..
cp -r xapian-bindings-1.4.29/python3/xapian env/lib/python3.11/site-packages/
```

##### Step 4: Test Xapian installation

```bash
# Test that Xapian works correctly
python -c "import xapian; print('Xapian version:', xapian.version_string())"
```

You should see output like: `Xapian version: 1.4.29`

##### Step 5: Install Python dependencies

```bash
# Install requirements (with virtual environment activated)
pip install -r requirements.txt
```

**Note:** When using this approach, do NOT set the `PYTHONPATH` to system packages as it may cause conflicts. The compiled Xapian bindings are installed directly in your virtual environment.

##### Troubleshooting

**If you get "configure: error: Python3 bindings build dependencies not found":**

- Make sure you installed all build dependencies: `sudo apt-get install python3-sphinx python3-dev swig build-essential`
- Verify your Python 3.11 installation: `python --version`

**If you get import errors when testing Xapian:**

- Ensure you're in the virtual environment: `source env/bin/activate`, typically you should see `(env)` in your shell prompt.
- Make sure you didn't set `PYTHONPATH` to system packages
- Verify the xapian module was copied correctly: `ls env/lib/python3.11/site-packages/xapian/`

**If the build fails with missing headers:**

- Install additional development packages: `sudo apt-get install libxapian-dev build-essential`
- Make sure Xapian core was installed successfully before building bindings

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

Also, we can add some sample data into the database to play along:

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
