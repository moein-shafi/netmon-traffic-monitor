# NetMon API Documentation

Complete API reference for NetMon Traffic Monitor.

## Base URL

All API endpoints are prefixed with `/api` unless otherwise noted.

## Authentication

Most endpoints require authentication using JWT Bearer tokens.

### Login

**POST** `/api/auth/login`

Request body:
```json
{
  "username": "admin",
  "password": "admin"
}
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "username": "admin",
    "role": "admin"
  }
}
```

### Using the Token

Include the token in the Authorization header:
```
Authorization: Bearer <token>
```

## Public Endpoints

### Health Check

**GET** `/api/health`

Returns system health status.

Response:
```json
{
  "status": "ok",
  "timestamp": "2024-01-01T00:00:00Z",
  "version": "2.0.0"
}
```

### Get Windows

**GET** `/api/windows`

Get all traffic windows.

Query parameters:
- `limit` (optional): Maximum number of windows to return (1-100)

Response:
```json
[
  {
    "id": "window-20240101120000",
    "metrics": {
      "start_time": "2024-01-01T12:00:00Z",
      "end_time": "2024-01-01T12:05:00Z",
      "total_flows": 1234,
      "total_packets": 5678,
      "benign_flows": 1000,
      "attack_flows": 200,
      "unknown_flows": 34,
      "attacks_per_label": {
        "DDoS": 150,
        "PortScan": 50
      },
      "total_payload_bytes": 12345678,
      "feature_stats": {
        "duration": {
          "mean": 5.2,
          "min": 0.1,
          "max": 120.5
        }
      }
    },
    "llm_summary": "- Window analysis summary..."
  }
]
```

### Get Latest Window

**GET** `/api/windows/latest`

Get the most recent traffic window.

Response: Same format as single window object from `/api/windows`.

### Get Public Configuration

**GET** `/api/config/public`

Get public configuration settings.

Response:
```json
{
  "dashboard": {
    "refresh_interval_seconds": 60,
    "max_windows_display": 12,
    "timezone": "UTC",
    "theme": "dark"
  },
  "display": {
    "show_attack_details": true,
    "show_llm_summaries": true
  },
  "alerts": {
    "enable_public_alerts": true,
    "alert_threshold_attack_percent": 10.0
  }
}
```

### Update Public Configuration

**PUT** `/api/config/public` (Requires authentication)

Update public configuration.

Request body:
```json
{
  "updates": {
    "dashboard": {
      "refresh_interval_seconds": 30
    },
    "alerts": {
      "alert_threshold_attack_percent": 15.0
    }
  }
}
```

### Get Alerts

**GET** `/api/alerts`

Get system alerts.

Query parameters:
- `acknowledged` (optional): Filter by acknowledged status (true/false)
- `resolved` (optional): Filter by resolved status (true/false)
- `severity` (optional): Filter by severity (high/medium/low)
- `limit` (optional): Maximum number of alerts (1-1000, default: 100)

Response:
```json
[
  {
    "id": 1,
    "window_id": "window-20240101120000",
    "alert_type": "critical",
    "severity": "high",
    "title": "Critical: High Attack Rate Detected",
    "message": "Window shows 50% attack flows...",
    "metadata": {},
    "acknowledged": false,
    "resolved": false,
    "created_at": "2024-01-01T12:05:00Z",
    "acknowledged_at": null,
    "resolved_at": null
  }
]
```

### Get Analytics Summary

**GET** `/api/analytics/summary`

Get aggregated analytics across windows.

Query parameters:
- `start_time` (optional): Start time (ISO 8601)
- `end_time` (optional): End time (ISO 8601)

Response:
```json
{
  "total_windows": 12,
  "total_flows": 15000,
  "total_packets": 75000,
  "total_attack_flows": 1500,
  "total_benign_flows": 13000,
  "attack_percentage": 10.0,
  "average_flows_per_window": 1250.0,
  "time_range": {
    "start": "2024-01-01T12:00:00Z",
    "end": "2024-01-01T13:00:00Z"
  }
}
```

## Admin Endpoints

All admin endpoints require admin role.

### Get Admin Configuration

**GET** `/api/admin/config`

Get admin-only configuration.

Response:
```json
{
  "capture": {
    "pcap_dir": "/var/pcaps",
    "csv_dir": "/var/netmon/flows",
    "window_duration_minutes": 5,
    "max_windows_keep": 12
  },
  "ml": {
    "model_path": "/opt/netmon/model/netmon_rf.joblib",
    "threshold": 0.90,
    "enabled": true
  },
  "llm": {
    "ollama_url": "http://127.0.0.1:11434/api/generate",
    "ollama_model": "smollm2:135m",
    "enabled": true
  }
}
```

### Update Admin Configuration

**PUT** `/api/admin/config`

Update admin configuration.

Request body:
```json
{
  "updates": {
    "ml": {
      "threshold": 0.85
    },
    "llm": {
      "enabled": false
    }
  }
}
```

### List Users

**GET** `/api/admin/users`

Get all users.

Response:
```json
[
  {
    "username": "admin",
    "role": "admin",
    "created_at": "2024-01-01T00:00:00Z",
    "active": true
  }
]
```

### Create User

**POST** `/api/admin/users`

Create a new user.

Request body:
```json
{
  "username": "newuser",
  "password": "securepassword",
  "role": "user"
}
```

### Update User Password

**PUT** `/api/admin/users/{username}/password`

Update a user's password.

Request body:
```json
{
  "new_password": "newsecurepassword"
}
```

### Update Own Password

**PUT** `/api/admin/password` (Requires authentication)

Update your own password.

Request body:
```json
{
  "current_password": "oldpassword",
  "new_password": "newpassword"
}
```

### Acknowledge Alert

**POST** `/api/admin/alerts/{alert_id}/acknowledge`

Acknowledge an alert.

Response:
```json
{
  "status": "acknowledged"
}
```

### Resolve Alert

**POST** `/api/admin/alerts/{alert_id}/resolve`

Resolve an alert.

Response:
```json
{
  "status": "resolved"
}
```

### Get Audit Logs

**GET** `/api/admin/audit-logs`

Get audit logs.

Query parameters:
- `username` (optional): Filter by username
- `action` (optional): Filter by action
- `limit` (optional): Maximum number of logs (1-1000, default: 100)

Response:
```json
[
  {
    "id": 1,
    "username": "admin",
    "action": "login",
    "resource": null,
    "details": {},
    "ip_address": "127.0.0.1",
    "user_agent": "Mozilla/5.0...",
    "created_at": "2024-01-01T12:00:00Z"
  }
]
```

### Export CSV

**GET** `/api/admin/export/csv`

Export windows data as CSV.

Query parameters:
- `start_time` (optional): Start time (ISO 8601)
- `end_time` (optional): End time (ISO 8601)

Returns: CSV file download

### Export JSON

**GET** `/api/admin/export/json`

Export windows data as JSON.

Query parameters:
- `start_time` (optional): Start time (ISO 8601)
- `end_time` (optional): End time (ISO 8601)

Returns: JSON file download

## Error Responses

All endpoints may return error responses in the following format:

```json
{
  "detail": "Error message"
}
```

Common HTTP status codes:
- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found
- `500`: Internal Server Error

## Rate Limiting

Currently, there is no rate limiting implemented. Consider implementing rate limiting for production deployments.

## WebSocket Support

WebSocket support for real-time updates is planned for future releases.

