import os
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

# Monetag Service Worker Route (404 error rokne ke liye)
@app.route('/sw.js')
def service_worker():
    return "/* Service Worker Active */", 200, {'Content-Type': 'application/javascript'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
