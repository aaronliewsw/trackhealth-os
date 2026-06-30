# TrackHealth OS API Contract

This is the frozen data seam both tracks build against: the backend owns typed
values, points, readings, factors, freshness, and connection state; React owns
all presentation. Slice 1 defines shapes only. FastAPI routes are added later.

## GET /api/state

Query params: none.

Response:

```json
{
  "date": "2026-06-30",
  "metrics": {
    "<metric-key>": {
      "value": "<typed Metric value object>",
      "label": "Steps",
      "unit": "steps",
      "has_readings": true
    }
  },
  "freshness": {
    "last_success_at": "2026-06-30T06:45:00+08:00",
    "next_scheduled_at": "2026-06-30T18:45:00+08:00"
  },
  "connection": {
    "state": "connected"
  }
}
```

`connection.state` is one of `connected`, `disconnected`, or `needs_mfa`.

## GET /api/metrics/{metric}/series

Query params:

- `range`: one of the frontend-supported range keys, for example `1d`, `7d`,
  `4w`, or `1y`.

Response:

```json
{
  "metric": "steps",
  "range": "1y",
  "points": [
    {
      "at": "2026-06-01",
      "value": 249350.0
    }
  ]
}
```

The backend resolves `range` to Store `Bucket` and aggregation through the
Metric registry. Points are returned ascending by date.

## GET /api/metrics/{metric}/readings

Query params:

- `on`: ISO date, `YYYY-MM-DD`.

Response:

```json
{
  "metric": "hrv",
  "on": "2026-06-30",
  "readings": [
    {
      "at": "2026-06-30T00:05:00+08:00",
      "value": 46.0,
      "detail": {
        "window": "overnight"
      }
    }
  ],
  "factors": {
    "baseline_low": 42,
    "baseline_high": 68,
    "status": "balanced"
  }
}
```

`factors` is structured data for Metric detail views and can be `null`.

## GET /api/metrics

Query params: none.

Response:

```json
{
  "metrics": [
    {
      "key": "steps",
      "label": "Steps",
      "unit": "steps",
      "has_readings": true,
      "agg": "sum"
    }
  ]
}
```

`agg` is one of `last` or `sum`.

## GET /api/sync/status

Query params: none.

Response:

```json
{
  "state": "idle",
  "last_success_at": "2026-06-30T06:45:00+08:00",
  "error": null
}
```

## GET /api/connection

Query params: none.

Response:

```json
{
  "state": "connected"
}
```
