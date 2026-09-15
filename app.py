import os
import sqlite3
import requests
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DB_NAME = 'movies_search.db'

# --- TELEGRAM BOT TOKEN ---
TELEGRAM_BOT_TOKEN = "8969193756:AAEDDa2IJqiVqL75b8JfhFcH4UHILUz0YvY"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Basic table create karo
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
    
    # 2. AUTO-FIX: Missing columns add karo
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

# --- MONETAG SERVICE WORKER ROUTE ---
@app.route('/sw.js')
def service_worker():
    return send_from_directory(app.root_path, 'sw.js')

# --- HOME PAGE ---
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

# --- WATCH PAGE ---
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

# --- GET LINK / TIMER PAGE ---
@app.route('/get-link/<int:movie_id>')
def get_link(movie_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return "Movie not found", 404
        
    movie = dict(row)
    return render_template('get_link.html', movie=movie)

# --- UPLOAD PAGE (Backup ke liye) ---
@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    return render_template('upload.html')

# --- TELEGRAM WEBHOOK PIPELINE (Video & File Support) ---
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    
    if update and 'message' in update:
        msg = update['message']
        chat_id = msg['chat']['id']
        
        # 1. Check karo ki kya user ne Start command di hai ya movie file bheji hai
        if 'text' in msg and msg['text'].startswith('/start'):
            text_val = msg['text']
            if 'movie_' in text_val:
                try:
                    movie_id = text_val.split('movie_')[1]
                    conn = sqlite3.connect(DB_NAME)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
                    row = cursor.fetchone()
                    conn.close()
                    
                    if row and row['video_url']:
                        # Bot user ko wahi asli Telegram file/video bhej dega
                        file_id = row['video_url']
                        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo", json={
                            "chat_id": chat_id,
                            "video": file_id,
                            "caption": f"🎬 Enjoy your movie: *{row['title']}*\n\nPowered by RK FILMS",
                            "parse_mode": "Markdown"
                        })
                    else:
                        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                            "chat_id": chat_id,
                            "text": "❌ Movie file not found or expired."
                        })
                except Exception as e:
                    pass
            return "OK", 200

        # 2. Movie Upload via Telegram Video/Document + Caption
        caption = msg.get('caption', '')
        file_id = None
        
        if 'video' in msg:
            file_id = msg['video']['file_id']
        elif 'document' in msg:
            file_id = msg['document']['file_id']
            
        if file_id and "|" in caption:
            parts = [p.strip() for p in caption.split('|')]
            
            if len(parts) == 7: # Title, Desc, Year, Rating, Category, Genre, Poster
                title, desc, year, rating, category, genre, poster = parts
                try:
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO movies (title, description, year, rating, category, genre, poster, video_url)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (title, desc, year, rating, category, genre, poster, file_id))
                    conn.commit()
                    conn.close()
                    
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                                  json={"chat_id": chat_id, "text": f"✅ Success! '{title}' movie file ke sath RK FILMS par save ho gayi."})
                except Exception as e:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                                  json={"chat_id": chat_id, "text": f"❌ Error: {str(e)}"})
            else:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                              json={"chat_id": chat_id, "text": "❌ Format galat hai. Caption mein 7 parts hone chahiye '|' ke sath.\nFormat: Title | Desc | Year | Rating | Category | Genre | Poster_URL"})
                
    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
```[cite: 1]

### Ab Movie Kaise Add Karni hai? (Telegram par):
1. Apne Telegram bot ko koi bhi **Movie Video file** ya **Document** bhejiye (ya channel se forward kariye).
2. Uste waqt **Caption** mein yeh format daal dijiye:
   `Avatar | Sci-fi adventure movie | 2022 | 7.8 | Movie | Sci-Fi | https://image_url_here.jpg`
3. Bot turant save kar lega[cite: 1] aur jab user website par timer cross karke aayega, toh bot **wahi original video file user ko bhej dega!**
