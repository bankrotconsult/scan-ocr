## Монтирование папки DFS-сервера (Windows) на Ubuntu-сервере

Сервис сохраняет готовые файлы в директорию `SCAN_FILES_DIR`. В продакшне эта директория должна
быть смонтирована из сетевой папки на Windows DFS-сервере через протокол SMB/CIFS.
Сервер Ubuntu и DFS-сервер должны находиться в одной корпоративной сети.

### 1. Установить клиент CIFS на Ubuntu

```bash
sudo apt update
sudo apt install cifs-utils
```

### 2. Создать точку монтирования

```bash
sudo mkdir -p /mnt/dfs/scan-files
```

Это будет локальный путь, который представится как сетевая папка DFS.
Именно его нужно будет указать в `SCAN_FILES_DIR` (или смонтировать поверх уже существующей директории).

### 3. Создать файл с доменными учётными данными

Хранить логин/пароль прямо в команде монтирования небезопасно — лучше в отдельном файле:

```bash
sudo nano /etc/smb-credentials
```

Содержимое файла:
```
username=ИМЯ_ПОЛЬЗОВАТЕЛЯ_ДОМЕНА
password=ПАРОЛЬ
domain=ИМЯ_ДОМЕНА
```

Закрыть доступ к файлу для остальных пользователей:
```bash
sudo chmod 600 /etc/smb-credentials
```

> `username` — доменная учётная запись, у которой есть права на запись в целевую папку DFS.
> Эта же учётная запись используется для удаления файлов и папок через проводник Windows.

### 4. Смонтировать сетевую папку вручную (проверка)

```bash
sudo mount -t cifs "//ИМЯ_DFS_СЕРВЕРА/ПУТЬ/К/ПАПКЕ" /mnt/dfs/scan-files \
  -o credentials=/etc/smb-credentials,uid=$(id -u),gid=$(id -g),file_mode=0664,dir_mode=0775,vers=3.0
```

Пример пути DFS: `//dfs.corp.local/shared/scan-output`

Параметры:
- `uid=$(id -u)` / `gid=$(id -g)` — файлы будут принадлежать текущему пользователю Ubuntu,
  что позволяет Docker-контейнеру (который тоже работает под этим uid) писать в папку без sudo.
- `file_mode=0664,dir_mode=0775` — права на создаваемые файлы и папки.
- `vers=3.0` — версия протокола SMB; если не работает, попробуй `vers=2.1` или `vers=2.0`.

Проверить, что папка доступна:
```bash
ls /mnt/dfs/scan-files
```

### 5. Настроить автомонтирование при загрузке (fstab)

Чтобы папка монтировалась автоматически после перезагрузки сервера, добавить строку в `/etc/fstab`:

```bash
sudo nano /etc/fstab
```

Добавить в конец файла:
```
//ИМЯ_DFS_СЕРВЕРА/ПУТЬ/К/ПАПКЕ  /mnt/dfs/scan-files  cifs  credentials=/etc/smb-credentials,uid=1000,gid=1000,file_mode=0664,dir_mode=0775,vers=3.0,_netdev  0  0
```

> `_netdev` — важный флаг: указывает системе ждать сети перед монтированием.
> `uid=1000,gid=1000` — заменить на фактический uid/gid пользователя сервера (`id ИМЯ_ПОЛЬЗОВАТЕЛЯ`).

Проверить, что fstab корректен (без перезагрузки):
```bash
sudo mount -a
```

### 6. Прописать путь монтирования в конфигурацию сервиса

В `docker-compose.yml` обновить путь тома и переменную:

```yaml
volumes:
  - /mnt/dfs/scan-files:/mnt/dfs/scan-files

environment:
  SCAN_FILES_DIR: /mnt/dfs/scan-files
```

### 7. Права на удаление папок из Windows

Чтобы можно было удалять созданные сервисом папки через проводник Windows или другой Windows-инструмент:

- Доменная учётная запись, указанная в `/etc/smb-credentials`, должна иметь права **«Изменение»** (Modify) или **«Полный доступ»** (Full Control) на целевую папку в настройках DFS на Windows-стороне.
- Это настраивается на самом DFS-сервере администратором через: `Свойства папки → Безопасность → Изменить`.
- Если файлы создаются другим пользователем (например, root из контейнера), Windows не позволит их удалить. Именно поэтому важно передавать правильный `uid` при монтировании (п. 4/5) и держать `user:` в docker-compose.

### 8. Диагностика проблем с подключением

```bash
# Проверить доступность сервера
ping ИМЯ_DFS_СЕРВЕРА

# Проверить доступность порта SMB
nc -zv ИМЯ_DFS_СЕРВЕРА 445

# Размонтировать при необходимости
sudo umount /mnt/dfs/scan-files

# Посмотреть смонтированные CIFS-ресурсы
mount | grep cifs
```

---

```bash
docker compose exec scan-app alembic revision --autogenerate
docker compose exec scan-app alembic upgrade head
```

### Connect Admin (dev)
```bash
docker compose exec scan-app python -m src.scripts.create_admin
```

### build command
```commandline
docker compose down -v && docker compose up --build
```