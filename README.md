# Nexus Search Engine

A full-featured web search engine with crawling, indexing, professional UI, and a free public API.

## Features

- **Web Crawler**: Crawls websites starting from a seed URL, following links within the same domain
- **Indexer**: Builds an inverted index for fast full-text search
- **Professional UI**: Google-like interface with clean design
- **Free API**: RESTful API endpoint for programmatic access (no authentication required)
- **Ranking**: Results ranked by term frequency

## Quick Start

```bash
# Install dependencies
pip install flask requests beautifulsoup4

# Run the server
python app.py
```

The server will start on `http://127.0.0.1:5000`

## Usage

### Web Interface
1. Open http://127.0.0.1:5000 in your browser
2. Click "Crawl Wikipedia Demo" to start crawling
3. Wait for crawling to complete
4. Enter search terms in the search box

### API Endpoints

#### Search
```
GET /api/search?q=<query>&limit=<optional_limit>
```

Example:
```bash
curl "http://127.0.0.1:5000/api/search?q=python+programming&limit=10"
```

Response:
```json
{
  "query": "python programming",
  "total_results": 5,
  "results": [
    {
      "title": "Page Title",
      "url": "https://example.com/page",
      "snippet": "... text snippet containing your search terms ..."
    }
  ]
}
```

#### Start Crawler
```
POST /api/crawl
Content-Type: application/json

{"url": "https://example.com"}
```

Example:
```bash
curl -X POST http://127.0.0.1:5000/api/crawl \
  -H "Content-Type: application/json" \
  -d '{"url": "https://en.wikipedia.org/wiki/Main_Page"}'
```

#### Check Status
```
GET /api/status
```

Returns current crawl status including pages crawled and queue size.

## Architecture

- **Backend**: Python Flask
- **Database**: SQLite (auto-created as `search_engine.db`)
- **Crawler**: Multi-threaded with configurable depth limit
- **Index**: Inverted index stored in SQLite for efficient lookups

## Configuration

Edit `app.py` to customize:
- `max_pages`: Maximum pages to crawl per session (default: 30)
- Port number (default: 5000)

## License

MIT License - Free for educational and commercial use.
