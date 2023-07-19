# Containerized web-services workshop

In this workshop, we will focus on how to containerize an application and deploy the application as a web service in the de.NBI cloud infrastructure. We will cover basics in the usage of container technology, configure an reverse proxy together and use "Let's encrypt" to secure your website. We will show you key mechanisms and practices how you can deploy your own webservices in our cloud infrastructure.

# Preparation

## Docker and docker compose

* add docker repository

```console
sudo apt-get update
sudo apt-get install ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

* install docker and docker compose

```console
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu
```

* setup mtu and internal network in docker

By default docker uses a larger mtu size then OpenStack. The internal network 172.17.0.0/16 can interfere with other networks in use. To change the mtu size and default network (this can be any private network not already in use) create the file ```/etc/docker/daemon.json``` with permissions 644.

```console
echo '{
   "bip":"192.168.140.1/24",
   "mtu":1440
}' | sudo tee /etc/docker/daemon.json
```

To change the permissions:
```console
sudo chmod 644 /etc/docker/daemon.json
```

Then reload the daemon and restart docker:
```console
sudo systemctl daemon-reload
sudo systemctl restart docker
```

* Create directory structure

For the sake of clarity we will use separate folders for the app and the reverse proxy. Create a main folder in you home directory an two sub folders in the main folder:

```console
mkdir -p ~/compose/{web-app,proxy}
```

# Deploying FastAPI with docker

* prepare FastAPI
 
To deploy FastAPI with docker we firstly must create all needed files for FastAPI in the directory ```~/compose/web-app/```. This includes the python files and a text file with the required apps from pip for FastAPI.

First create another directory ```~/compose/web-app/app```:

```console
mkdir ~/compose/web-app/app
```

Write an empty python file called ```~/compose/web-app/app/__init__.py```.

```console
touch ~/compose/web-app/app/__init__.py
```

Than create another file ```~/compose/web-app/app/main.py``` with the following content:

```python
from typing import Union

from fastapi import FastAPI

import os

hostname = os.environ['HOST_NAME']

app = FastAPI(root_path="/p/"+hostname+"/80")


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}
```


This will import the fastapi python module and use it to create a new object called ```app```. In this environment we need to use the host name of the vm to reach the API with the browser. Therefor the root directory is set to a value build with the hostname from the vm. To use the environmental variable it needs to be exported:

```console
export HOSTNAME
```

When the root directory is called the key value pair ```"Hello": "World``` should be given back. The items can be called with the ```item_id```. 

Now create a file with the dependencies for the app you want to use. In this case we need three apps from pip. Create the file ```~/compose/web-app/requirements.txt```:

```text
fastapi>=0.68.0,<0.69.0
pydantic>=1.8.0,<2.0.0
uvicorn>=0.15.0,<0.16.0
```
This file will be used later to install all necessary program for the app. The numbers after the names define which version will be installed.

* Deploy the app with docker

To deploy FastAPI with docker we need a ```Dockerfile``` in the folder ```~/compose/web-app/Dockerfile```. 

```Dockerfile
FROM python:3.9
WORKDIR /code
ENV HOST_NAME $HOSTNAME
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
COPY ./app /code/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
```

This will use the python image in version 3.9 to create a container in which the directory ```code``` is created. The ```code``` directory is defined as default or *working directory*, all actions are done there.
The file with the required programs is copied to the folder and used to install all inserted programs with ```pip install```.
Now the folder ```app``` with the files ```__init__.py``` and ```main.py``` is copied to the *working directory*.
The last line calls the command ```uvicorn app.main:app --host 0.0.0.0 --port 80``` in the container.

Next we need to create an image from the ```Dockerfile```. Note the dot at the end of this command, indicating the location of the ```Dockerfile```
```console
sudo docker build -t myimage .
```

When the image build is done we can start a container using this image.
```console
sudo docker run -d --name mycontainer -p 80:80 myimage
```

The content can be checked with a web browser by using the external IP of the machine an d port 80.
To terminate all containers use the following command:

```console
sudo docker stop $(sudo docker ps -aq)
sudo docker rm $(sudo docker ps -aq)
```

# Deploying reverse proxy with docker

* preparation of reverse proxy

As reverse proxy we are using nginx. To use nginx we need to create a Dockerfile for the container and a config file for the reverse proxy.

Create the file ```~/compose/proxy/conf``` with the following content:
```conf
server {
  listen 80;
  server_name compose-reverse-proxy-1;
  location / {
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-NginX-Proxy true;
    proxy_pass http://compose-web-app-1:8080;
    proxy_ssl_session_reuse off;
    proxy_set_header Host $http_host;
    proxy_cache_bypass $http_upgrade;
    proxy_redirect off;
  }
}
```
 
This file will create a simple reverse-proxy that redirects all incoming traffic to the container called compose-web-app-1 at port 8080 and use some security measures for the connection.

* deploy the reverse proxy with docker

Now create a Dockerfile in  the folder and add the following content:
```Dockerfile
FROM nginx:1.13-alpine
COPY conf /etc/nginx/conf.d/default.conf
```

This will load the image nginx in version 1.13-alpine for the reverse proxy and copy the previously created ```conf``` file to the container.

This can be run as a single container by creating an image from the Dockerfile and creating a container from that image as done before with the FastAPI Dockerfile
```console
docker build -t myproxyimage .
docker run -d --name myproxycontainer -p 80:80 myproxyimage
```
As there is no service answering on port 8080 only the default page can be seen here.

---

# Deploy FastAPI and reverse proxy with docker compose

* Preparation of FastAPI 

We need to change the existing ```Dockerfile``` for FastAPI so we can use a reverse proxy.

Add the tag ```--proxy-headers``` to the issued command in the last line and change the port to ```8080```. Remove the ```ENV``` tag and the variables as we will use the ```docker-compose.yml``` for this. The new file should look like this:
```Dockerfile
FROM python:3.9
WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
COPY ./app /code/app
CMD ["uvicorn", "app.main:app", "--proxy-headers", "--host", "0.0.0.0", "--port", "8080"]
```

* prepare docker compose

We can use the previously created folders and both ```Dockerfiles``` for the docker compose deployment. 

To use docker compose, create a ```docker-compose.yml``` file in the directory ```~/compose/docker-compose.yml``` and enter the following:

```yml
version: "3.8"
services:
  web-app:
    build: ./web-app
    environment:
      HOST_NAME: $HOSTNAME
    networks:
      - app-net
  proxy:
    build: ./proxy
    ports:
      - 80:80
      - 443:443
    networks:
      - app-net

networks:
  app-net:
    ipam:
      driver: default
      config:
        - subnet: 10.0.32.0/24
          ip_range: 10.0.32.0/28

```

The version is just for reference it is not used to determine the docker version in use. In the section ```services:``` the containers to run are specified. 
In the ```build:``` tag of each service the folder for the Dockerfile is specified. As the ```docker-compose.yml``` file is located in the directory ```~/compose``` the folders to the Dockerfile is given in accordance to the directory of the ```docker-compose.yml``` file, indicated by the ```.``` at the beginning. 

In the section ```environment``` the variable for the vm host name is passed to the container. In the section ```networks:``` a network is created. We call it ```app-net:``` with the parameter ```ipam:``` we create a subnet for the containers with an usable ip range of 10.0.32.0/28. Select the default driver and an appropriate subnet (Default docker and docker compose networks are in the range of the OpenStack training public2 range and therefore can not be used.)

This will create two containers from the two folders which we just created. For each container the corresponding ```Dockerfile``` will be used. Note, that only the container for the reverse proxy does have any attached ports. This way the reverse proxy is reachable from the outside, but FastAPI is not.

To use the environmental variable export it:

```console
export HOSTNAME
```

Then start the containers with the following command:
```
docker compose up
```

Use your browser again to reach the IP of the vm and you should see the FastAPI page.
