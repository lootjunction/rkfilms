import os
import sqlite3
import requests
from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DB_NAME = 'movies_search.db'

# --- TELEGRAM BOT TOKEN YAHAN DALEIN ---
TELEGRAM_BOT_TOKEN = "8969193756:AAEDDa2IJqiVqL75b8JfhFcH4UHILUz0YvY"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Basic table create karo (agar bilkul nahi hai toh)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            year TEXT,
            poster TEXT,
            video_url TEXT
        )
    ''')
    
    # 2. AUTO-FIX: Agar purani database hai toh missing columns add karo
    cursor.execute("PRAGMA table_info(movies)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'rating' not in columns:
        cursor.execute("ALTER TABLE movies ADD COLUMN rating TEXT DEFAULT '0.0'")
    if 'category' not in columns:
        cursor.execute("ALTER TABLE movies ADD COLUMN category TEXT DEFAULT 'Movie'")
    if 'genre' not in columns:
        cursor.execute("ALTER TABLE movies ADD COLUMN genre TEXT DEFAULT 'Unknown'")
        
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    search_query = request.args.get('search', '').lower()
    selected_category = request.args.get('category', 'All')
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM movies WHERE 1=1"
    params = []
    
    if search_query:
        query += " AND LOWER(title) LIKE ?"
        params.append('%' + search_query + '%')
        
    if selected_category and selected_category != 'All':
        query += " AND category = ?"
        params.append(selected_category)
        
    cursor.execute(query, params)
    raw_movies = cursor.fetchall()
    conn.close()

    movies = []
    for row in raw_movies:
        movies.append(dict(row))

    trending = movies
    latest = sorted(movies, key=lambda x: x.get('year') if x.get('year') else '0', reverse=True)
    
    def safe_rating(movie):
        try:
            return float(movie.get('rating') or 0)
        except:
            return 0.0

    top_rated = sorted(movies, key=safe_rating, reverse=True)
    
    return render_template('index.html', trending=trending, latest=latest, top_rated=top_rated, search=search_query, current_category=selected_category)

@app.route('/watch/<int:movie_id>')
def watch(movie_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return "Movie not found", 404
        
    movie = dict(row)
    return render_template('watch.html', movie=movie)

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    return render_template('upload.html')

# --- TELEGRAM WEBHOOK ---
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    
    if update and 'message' in update and 'text' in update['message']:
        chat_id = update['message']['chat']['id']
        text = update['message']['text']
        
        # Bot ko is exact sequence mein script bhejni hai: 
        # Title | Description | Year | Rating | Category | Genre | Poster_URL | Video_URL
        if "|" in text:
            parts = [p.strip() for p in text.split('|')]
            
            if len(parts) == 8:
                try:
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO movies (title, description, year, rating, category, genre, poster, video_url)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', tuple(parts))
                    conn.commit()
                    conn.close()
                    
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                                  json={"chat_id": chat_id, "text": f"✅ Success! '{parts[0]}' RK FILMS par upload ho gayi."})
                except Exception as e:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                                  json={"chat_id": chat_id, "text": f"❌ Error: {str(e)}"})
            else:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                              json={"chat_id": chat_id, "text": "❌ Format galat hai. 8 parts hone chahiye '|' ke sath."})
    
    return "OK", 200

if __name__ == '__main__':
    app.run(host='localhost', port=5000, debug=True)