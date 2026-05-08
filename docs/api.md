# Libby — API Reference

All endpoints return JSON. The envelope is:

- **Success**: `{"status": "ok", "data": <payload>}`
- **Error**: `{"status": "error", "message": "<description>", "code": <http_status>}`

Base URL: `http://127.0.0.1:5000`

---

## Health

### `GET /api/health`

Liveness check.

**Response**
```json
{"status": "ok"}
```

---

## Books

### `GET /api/books`

Return a paginated, filterable list of books in the library.

**Query parameters**

| Param    | Type   | Default  | Description                              |
|----------|--------|----------|------------------------------------------|
| `page`   | int    | 1        | Page number (1-based)                    |
| `limit`  | int    | 50       | Books per page (max 200)                 |
| `search` | string | —        | Full-text search on title and author     |
| `author` | string | —        | Exact author filter                      |
| `status` | string | —        | `unread` \| `reading` \| `read`          |
| `sort`   | string | `title`  | `title` \| `author` \| `date_added`      |

**Response `data`**
```json
{
  "books": [ <Book>, ... ],
  "total": 142,
  "page": 1,
  "pages": 3
}
```

**Book object**
```json
{
  "id": "urn:uuid:...",
  "title": "Dune",
  "author": "Frank Herbert",
  "publisher": "Chilton Books",
  "language": "en",
  "description": "...",
  "file_path": "/path/to/dune.epub",
  "cover_path": "/data/covers/abc123.jpg",
  "file_size": 1048576,
  "date_added": "2024-06-01T12:00:00",
  "read_status": "unread"
}
```

---

### `POST /api/scan`

Trigger a scan of the configured `LIBRARY_PATH`. Discovers new EPUBs, extracts metadata, and upserts into the database.

**Response `data`**
```json
{ "scanned": 87, "added": 5, "updated": 2 }
```

---

### `PATCH /api/books/:id/status`

Update the read status of a single book.

**Body**
```json
{ "read_status": "reading" }
```

**Response `data`**: Updated Book object.

---

### `POST /api/books/:id/edit`

Edit a book's metadata. Uses `multipart/form-data`. All fields are optional.

| Field    | Type   | Description                            |
|----------|--------|----------------------------------------|
| `title`  | string | New title                              |
| `author` | string | New author                             |
| `cover`  | file   | Replacement cover image (JPEG or PNG) |

**Response `data`**: Updated Book object.

---

## Kobo Device

### `GET /api/kobo/status`

Check whether a Kobo device is currently connected.

**Response `data`**
```json
{
  "connected": true,
  "device": {
    "name": "KOBOeReader",
    "mount_point": "E:\\",
    "free_space": 26843545600,
    "total_space": 32212254720,
    "is_kobo": true
  }
}
```

---

### `POST /api/kobo/send`

Copy an EPUB to the connected Kobo device.

**Body**
```json
{ "book_id": "urn:uuid:..." }
```

**Response `data`**
```json
{ "bytes_transferred": 1048576, "destination": "E:\\dune.epub" }
```
