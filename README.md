# APUDIG MVP (Django)

Proyecto nuevo e independiente para la migración FastAPI -> Django monolito.

## 1) Crear entorno virtual propio

```bash
cd apudig_mvp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 2) Ejecutar en local (SQLite)

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Abrir: http://127.0.0.1:8000/login/

## 3) Ejecutar con Docker + PostgreSQL

1. Edita `.env` y activa valores PostgreSQL.
2. Levanta:

```bash
docker compose up --build
```

## 4) Flujo MVP implementado

- Login (`/login`)
- Selección empresa/sucursal (`/companies/select/`)
- Dashboard base (`/dashboard/`)

## 5) Próximo paso recomendado

- Migrar auth multiempresa real desde APUDIG (tabla usuarios, roles y acceso por store).
- Incorporar apps de fase 2 (`partners`, `inventory`).
