import sqlite3
import threading
import time
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from flask import Flask, render_template, request, jsonify
from queue import Queue
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
DB_NAME = "search_engine.db"

# --- Database Layer ---
def init_db():
    """Initialize the SQLite database with necessary tables."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Table for crawled URLs
    c.execute('''CREATE TABLE IF NOT EXISTS urls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE,
        title TEXT,
        content TEXT,
        crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Table for Inverted Index (Word -> URL ID)
    c.execute('''CREATE TABLE IF NOT EXISTS inverted_index (
        word TEXT,
        url_id INTEGER,
        frequency INTEGER,
        PRIMARY KEY (word, url_id)
    )''')
    
    # Table for Crawl Queue (To persist queue between restarts if needed, though we use memory for speed)
    c.execute('''CREATE TABLE IF NOT EXISTS crawl_queue (
        url TEXT UNIQUE
    )''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized.")

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# --- Crawler & Indexer Logic ---
class SearchEngineCrawler:
    def __init__(self, max_pages=50):
        self.queue = Queue()
        self.visited = set()
        self.max_pages = max_pages
        self.crawled_count = 0
        self.is_crawling = False
        
    def add_seed(self, url):
        if url not in self.visited:
            self.queue.put(url)
            
    def normalize_url(self, url):
        # Simple normalization: strip fragments, ensure http/https
        parsed = urlparse(url)
        if not parsed.scheme:
            return None
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def crawl(self):
        if self.is_crawling:
            return "Crawler already running."
        
        thread = threading.Thread(target=self._run_crawler)
        thread.daemon = True
        thread.start()
        return "Crawler started in background."

    def _run_crawler(self):
        self.is_crawling = True
        conn = get_db_connection()
        c = conn.cursor()
        
        while not self.queue.empty() and self.crawled_count < self.max_pages:
            try:
                url = self.queue.get(timeout=2)
            except:
                break
                
            if url in self.visited:
                continue
            
            self.visited.add(url)
            logger.info(f"Crawling: {url}")
            
            try:
                headers = {'User-Agent': 'MySearchBot/1.0 (Educational Project)'}
                response = requests.get(url, headers=headers, timeout=5)
                
                if response.status_code != 200:
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract Title
                title = soup.title.string if soup.title else url
                
                # Extract Text Content (remove scripts/styles)
                for script in soup(["script", "style", "nav", "footer"]):
                    script.decompose()
                text = soup.get_text(separator=' ', strip=True)
                
                # Save to DB
                try:
                    c.execute("INSERT OR IGNORE INTO urls (url, title, content) VALUES (?, ?, ?)", 
                              (url, title, text))
                    conn.commit()
                    
                    # Get the ID of the inserted or existing row
                    c.execute("SELECT id FROM urls WHERE url = ?", (url,))
                    row = c.fetchone()
                    if row:
                        url_id = row[0]
                        self._index_content(text, url_id, c)
                        conn.commit()
                        self.crawled_count += 1
                except sqlite3.IntegrityError:
                    pass # Already exists
                
                # Extract Links
                base_domain = urlparse(url).netloc
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    full_url = urljoin(url, href)
                    
                    # Only follow same domain links to stay safe and relevant
                    if urlparse(full_url).netloc == base_domain:
                        clean_url = self.normalize_url(full_url)
                        if clean_url and clean_url not in self.visited:
                            self.queue.put(clean_url)
                            
            except Exception as e:
                logger.error(f"Error crawling {url}: {e}")
                
        self.is_crawling = False
        conn.close()
        logger.info(f"Crawling finished. Total pages: {self.crawled_count}")

    def _index_content(self, text, url_id, cursor):
        """Tokenize text and update inverted index."""
        # Simple tokenization: lowercase, remove non-alphanumeric
        words = re.findall(r'\b[a-z]{3,}\b', text.lower())
        
        word_counts = {}
        for word in words:
            word_counts[word] = word_counts.get(word, 0) + 1
        
        for word, count in word_counts.items():
            # Upsert logic for SQLite
            cursor.execute('''
                INSERT INTO inverted_index (word, url_id, frequency)
                VALUES (?, ?, ?)
                ON CONFLICT(word, url_id) DO UPDATE SET frequency = frequency + ?
            ''', (word, url_id, count, count))

# Initialize components
init_db()
crawler = SearchEngineCrawler(max_pages=30) # Limit for demo purposes

# --- Routes & API ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/search', methods=['GET'])
def api_search():
    """
    Free Public API Endpoint
    Params: q (query), limit (optional, default 10)
    """
    query = request.args.get('q', '').lower()
    limit = request.args.get('limit', 10, type=int)
    
    if not query:
        return jsonify({"error": "No query provided", "results": []}), 400
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # Tokenize query
    search_terms = re.findall(r'\b[a-z]{3,}\b', query)
    
    if not search_terms:
        return jsonify({"results": []})

    # Build SQL query to find URLs containing most search terms
    # We sum the frequencies of matching words to rank results
    placeholders = ','.join('?' * len(search_terms))
    
    sql = f'''
        SELECT u.url, u.title, u.content, SUM(i.frequency) as score
        FROM inverted_index i
        JOIN urls u ON i.url_id = u.id
        WHERE i.word IN ({placeholders})
        GROUP BY u.id
        ORDER BY score DESC
        LIMIT ?
    '''
    
    params = search_terms + [limit]
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        # Snippet generation
        content = row['content']
        snippet = "... " + content + " ..."
        # Try to find a better snippet around the keyword
        for term in search_terms:
            if term in content:
                start = max(0, content.find(term) - 50)
                end = min(len(content), content.find(term) + 150)
                snippet = "..." + content[start:end] + "..."
                break
                
        results.append({
            "title": row['title'],
            "url": row['url'],
            "snippet": snippet
        })
    
    return jsonify({
        "query": query,
        "total_results": len(results),
        "results": results
    })

@app.route('/api/crawl', methods=['POST'])
def api_start_crawl():
    data = request.json
    seed_url = data.get('url') if data else None
    
    if not seed_url:
        return jsonify({"error": "Seed URL required"}), 400
        
    crawler.add_seed(seed_url)
    status = crawler.crawl()
    
    return jsonify({"status": status, "seed": seed_url})

@app.route('/api/status', methods=['GET'])
def api_status():
    return jsonify({
        "crawled_count": crawler.crawled_count,
        "is_crawling": crawler.is_crawling,
        "queue_size": crawler.queue.qsize()
    })

if __name__ == '__main__':
    print("Starting Search Engine...")
    print("UI available at: http://127.0.0.1:5000")
    print("API available at: http://127.0.0.1:5000/api/search?q=your_query")
    # Disable debug mode to avoid reloader issues in background
    app.run(debug=False, host='0.0.0.0', port=5000)
