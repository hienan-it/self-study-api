# 🎓 Study Master API

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)

An AI-powered backend for the Study Master platform. Built with **FastAPI** for high performance and **OpenAI** integration for intelligent educational features.

---

## 🚀 Key Features

- **🔐 Robust Auth**: JWT-based authentication with role-based access control.
- **📚 Academic Management**: Modular structure for subjects, modules, and lessons.
- **🤖 AI Integration**: Intelligent study assistants and automated knowledge extraction.
- **📊 Session Tracking**: Detailed analytics for study progress and engagement.
- **🗃️ DB Migrations**: Managed with Alembic for reliable schema evolution.

## 🛠️ Tech Stack

- **Core**: FastAPI (Python 3.11+)
- **ORM**: SQLAlchemy 2.0 (Async)
- **Validation**: Pydantic v2
- **Database**: PostgreSQL
- **Migrations**: Alembic
- **AI Engine**: OpenAI API
- **Web Server**: Uvicorn

---

## 📥 Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL
- OpenAI API Key

### Installation

1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd self-study-api
   ```

2. **Setup Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate # Linux/macOS
   # venv\Scripts\activate  # Windows
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   Copy `.env.example` to `.env` and fill in your details:
   ```bash
   cp .env.example .env
   ```

5. **Run Database Migrations**
   ```bash
   alembic upgrade head
   ```

### Running the Server

**Development Mode (Auto-reload):**
```bash
uvicorn app.main:app --reload --port 8000
```

**Access Documentation:**
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## 🐳 Docker Deployment

Run the entire stack (API + DB) using Docker Compose:

```bash
docker-compose up -d
```

---

## 📂 Project Structure

```text
app/
├── api/            # Route handlers & endpoints
├── core/           # Security, auth, config, exceptions
├── db/             # Database session & models
├── models/         # Pydantic & SQLAlchemy models
├── services/       # Business logic layer
└── utils/          # Helper functions & setup scripts
alembic/            # Database migration versions
```

---

## 📄 License
This project is private. All rights reserved.
