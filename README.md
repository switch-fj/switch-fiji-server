# Switch Fiji Server

The backend microservice powering the Switch Fiji IoT platform.

This system ingests telemetry data from field devices, maps them to registered clients and sites, and exposes structured data for engineering, finance, and client-facing applications.

---

## 🚀 Overview

Switch Fiji Server is a scalable, event-driven backend designed to manage:

* IoT device telemetry (real-time + historical)
* Client, site, and device relationships
* Engineering monitoring tools
* Fiance (Billing and invoicing systems)

---

## 🧠 Architecture

The system follows a **hybrid data architecture**:

### 1. Operational Data (PostgreSQL)

Managed via `SQLModel`

Stores:

* Users
* Clients
* Sites
* Devices
* Contracts
* Billing & invoices

---

### 2. Telemetry Data (AWS DynamoDB)

Stores:

* High-frequency device logs
* Time-series data (energy, inverter stats, etc.)

---

### 3. Async Processing

Handled via:

* Celery (task queue)
* Redis (broker + caching)

Used for:

* Background jobs
* Billing cycles
* Notifications

---

## 🔄 Data Flow

```
Device → Ingestion API → DynamoDB → Telemetry Service → API → Dashboard
```

---

## 📦 Tech Stack

* **FastAPI** – API framework
* **SQLModel + PostgreSQL** – relational data
* **DynamoDB (via aioboto3)** – telemetry storage
* **Celery + Redis** – background processing
* **Structlog** – structured logging
* **Pydantic** – validation & schemas

---

## 📁 Project Structure

```
├── app/
│   │
│   ├── main.py
│   │
│   ├── core/                   # Global system logic
│   │     ├── settings.py       # Environment & config
│   │     ├── security.py       # JWT, hashing
│   │     ├── auth.py           # Authentication logic
│   │     ├── permissions.py    # Role-based access
│   │     └── dependencies.py   # FastAPI dependencies
│   │
│   ├── database/
│   │     ├── postgres.py       # Postgres setup
│   │     ├── dynamodb.py       # DynamoDB client
│   │     └── migrations/       # Alembic migrations
│   │
│   ├── modules/                # Domain-driven modules
│   │     ├── users/
│   │     ├── clients/
│   │     ├── sites/
│   │     ├── devices/
│   │     ├── contracts/
│   │     ├── billing/
│   │     ├── invoices/
│   │     └── telemetry/
│   │
│   ├── services/               # Business logic layer
│   │     ├── telemetry_service.py
│   │     ├── billing_service.py
│   │     ├── invoice_service.py
│   │     └── device_service.py
│   │
│   ├── jobs/                   # Background workers (Celery)
│   │     ├── billing_jobs.py
│   │     └── telemetry_jobs.py
│   │
│   ├── api/                    # API routes (by role)
│   │     ├── admin/
│   │     ├── engineer/
│   │     └── client/
│   │
│   └── utils/
│         ├── pagination.py
│         └── datetime_utils.py
│
└── pyproject.toml
```

---

## 🧩 Architectural Principles

### 🔹 Module-Driven Design

Each domain module is self-contained:

```
modules/devices/
├── model.py
├── schema.py
└── repository.py
```
---

### 🔹 Service Layer (Business Logic)

* Centralizes all business rules
* Orchestrates database + external services
* Keeps API routes clean

---

### 🔹 Thin API Layer

Routes are responsible for:

* Request validation
* Calling services
* Returning responses

---

### 🔹 Background Jobs

Heavy or scheduled tasks are handled via Celery:

* Billing calculations
* Telemetry aggregation
* Notifications

---

## ⚙️ Setup

### 1. Install dependencies

```bash
uv sync
```

---

### 2. Activate environment

```bash
source .venv/bin/activate
```

---

### 3. Environment variables

Create a `.env` file:

```
DATABASE_URL=postgresql://user:password@localhost:5432/switch_fiji
REDIS_URL=redis://localhost:6379
AWS_REGION=your-region
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
DYNAMODB_TABLE=telemetry-table
```

---

### 4. Run database migrations

```bash
alembic upgrade head
```

---

### 5. Start the server

```bash
uvicorn app.main:app --reload
```

---

### 6. Start Celery worker

```bash
celery -A app.jobs worker --loglevel=info
```

---

### 7. Start Flower (optional)

```bash
celery -A app.jobs flower
```

---

## 📡 Core Concepts

### 🔹 Clients

Organizations that own one or more sites.

### 🔹 Sites

Physical locations where devices are deployed.

### 🔹 Devices

Gateway units (e.g., ESP32) that send telemetry data.

Each device is uniquely identified by:

```
gateway_id
```

---

## ⚠️ Important Design Rules

### ❌ No Auto-Creation from Telemetry

Clients, sites, and devices must be explicitly created.

Telemetry must match an existing device.

Unknown devices are logged as:

```
unregistered_device
```

---

## 📊 Telemetry

Telemetry data includes:

* Energy meters (kWh, power)
* Inverter data (MPPT, status, battery SOC)
* AC monitoring
* Irradiance readings

Stored in DynamoDB and accessed via the telemetry service.

---

## 🔌 Key Endpoints

### Ingestion

```
POST /ingest/telemetry
```

Writes raw device payload to DynamoDB.

---

### Engineer Dashboard

```
GET /engineer/sites/{site_id}/telemetry
```

Returns:

* Device logs
* Meter readings
* Inverter status

---

## 🧪 Development

### Linting

```bash
uv run ruff lint
```

### Formatting

```bash
uv run ruff format
```

---

## 🔐 Security (Planned)

* JWT authentication
* Role-based access control (Admin, Engineer, Client)
* API rate limiting

---

## 📈 Scaling Strategy

* Stateless FastAPI services
* Horizontal scaling via containers
* DynamoDB for high-throughput ingestion
* Redis caching for hot queries

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch
3. Commit changes
4. Open a PR

---

## 📄 License

Proprietary – Switch Fiji Project