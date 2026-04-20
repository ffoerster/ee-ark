# ee-ark

> A Python/Django application for minting, binding, and resolving [ARK identifiers](https://arks.org/). Used for the [Electric Echoes Flyer Archive](https://beta.electric-echoes.org/), but designed to be reusable for other projects.

Fork of [squidgetx/arklet](https://github.com/squidgetx/arklet), which is itself a fork of the [Internet Archive Arklet](https://github.com/internetarchive/arklet/).

Licensed under the [MIT License](LICENSE).

---

## Features

| Feature | ee-ark | internetarchive |
| --- | :---: | :---: |
| ARK resolution | ✓ | ✓ |
| ARK minting and editing | ✓ | ✓ |
| Bulk minting and editing | ✓ | |
| Suffix passthrough | ✓ | |
| Separate minter and resolver | ✓ | |
| API access key hashing | ✓ | |
| Shoulder rules | ✓ | |
| Extensive metadata | ✓ | |
| Tombstone support | ✓ | |
| `?info` and `?json` endpoints | ✓ | |

---

## Architecture

The service consists of four components:

- **Database** — PostgreSQL storing ARK identifiers and metadata
- **Resolver** — Django web app that redirects ARK URLs to their target resources. Unknown ARKs are forwarded to [n2t.net](https://n2t.net).
- **Minter** — Django web app with a REST API and admin UI for creating and managing ARKs. Can also act as a resolver.
- **CLI** — Command line tools in [`/ui`](ui/) for scripting against the API.

The repo is pre-configured with Docker for both local development and production.

---

## Setup

### Local Development

```bash
docker-compose up
```

Starts PostgreSQL, the minter (`127.0.0.1:8001`), and the resolver (`127.0.0.1:8000`). Environment config lives in `docker/env.local`. Port changes also require updating `docker-compose.yml`.

**Create the first superuser:**

```bash
make dev-cmd          # opens a shell in the minter container
./manage.py createsuperuser
```

Then open `http://127.0.0.1:8001/admin` to create a NAAN and an API key.

### Production

The repo is pre-configured for nginx + gunicorn with a managed Postgres instance (e.g. a DigitalOcean droplet + managed database).

1. Copy `env.prod.example` → `env.prod` and fill in your Postgres credentials and Django secret key.
2. Start all services:

```bash
make prod
# or: docker-compose -f docker-compose.nginx.yml --profile nginx up
```

By default the resolver runs on port 80 and the minter on port 8080. To change the minter port, update both `docker-compose.nginx.yml` and `nginx.conf`.

---

## API Reference

### Resolution (resolver + minter)

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/ark://{naan}/{id}` | Redirect to the target URL, or forward to n2t.net if unknown |
| `GET` | `/ark://{naan}/{id}?info` | Human-readable HTML metadata page |
| `GET` | `/ark://{naan}/{id}?json` | JSON metadata response |
| `GET` | `/ark://{naan}/{id}/{suffix}` | Redirect with suffix passthrough |

### Management (minter only)

All management endpoints require an `Authorization` header with a valid API key. Keys are provisioned in the admin UI and are scoped to NAANs.

Error responses use a consistent JSON shape:

```json
{
  "code": "validation_error",
  "message": "Mint payload validation failed",
  "details": {
    "shoulder": ["This field is required."]
  },
  "request_id": "8c47627b-355b-4b07-8b2e-5da23afec6ae"
}
```

Common error codes:

| Code | Typical status | Meaning |
| --- | --- | --- |
| `method_not_allowed` | `405` | HTTP method is not supported for this endpoint |
| `invalid_json` | `400` | Request body is not valid JSON |
| `validation_error` | `400` | Form-level validation failed |
| `forbidden` | `403` | Missing or invalid API key |
| `invalid_payload` | `400` | JSON shape is wrong (e.g. missing `data` or required fields) |
| `invalid_ark` | `400` | ARK value is malformed |
| `ark_not_found` | `404` | Requested ARK does not exist |
| `invalid_shoulder` | `400` | Shoulder does not exist |
| `batch_limit_exceeded` | `400` | More than 100 records in one batch request |
| `mint_collision_limit` | `500` | Minting failed repeatedly due to identifier collisions |

#### `POST /mint`

Mints a new ARK.

| Field | Required |
| --- | :---: |
| `naan` | ✓ |
| `shoulder` | ✓ |
| `url` | |
| `title` | |
| `type` | |
| `commitment` | |
| `identifier` | |
| `format` | |
| `relation` | |
| `source` | |
| `metadata` | |

Returns the minted ARK identifier as a JSON string. The shoulder must already exist (managed via the admin UI).

#### `PUT /update`

Updates an existing ARK. Requires `ark`; all other fields from `/mint` are optional.

Additional optional tombstone fields:

| Field | Description |
| --- | --- |
| `state` | `active` or `tombstoned` |
| `replaced_by` | ARK that supersedes this record |
| `tombstone_reason` | Human-readable reason for tombstoning |

Returns `200` on success.

#### `POST /bulk_mint`

Mints up to 100 ARKs at once.

```json
{
  "naan": "12345",
  "data": [
    { "shoulder": "s1", "url": "https://example.org/1" },
    { "shoulder": "s1", "url": "https://example.org/2" }
  ]
}
```

#### `POST /bulk_update`

Updates up to 100 ARKs at once.

```json
{
  "data": [
    { "ark": "ark:/12345/s1abc", "url": "https://example.org/new" }
  ]
}
```

#### `POST /bulk_query`

Queries up to 100 ARKs at once.

```json
{
  "data": [
    { "ark": "ark:/12345/s1abc" }
  ]
}
```

#### `GET /history?ark=ark:/...&limit=20`

Returns recent change events for an ARK (most recent first). `limit` is optional (default `20`, max `100`).

### Admin UI

Access `/admin` on the minter to manage API keys, shoulders, NAANs, and administrator accounts. Protected by username/password authentication.
