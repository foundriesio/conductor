Test scheduler and coordinator. Works together with jobserv and LAVA

## Setup rabbitmq for the worker
```
sudo rabbitmqctl add_vhost conductor
sudo rabbitmqctl add_user "conductor" "secret"
sudo rabbitmqctl set_permissions -p "conductor" "conductor" ".*" ".*" ".*"
```

## Start worker
```
python -m celery -A conductor worker -B
```
