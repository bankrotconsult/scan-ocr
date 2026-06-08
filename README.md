```bash
docker compose exec app alembic revision --autogenerate
docker compose exec app alembic upgrade head
```

### Connect Admin (dev)
```bash
docker compose -f docker-compose-dev.yml exec app python -m src.scripts.create_admin
```