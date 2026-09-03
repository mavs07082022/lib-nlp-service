# python/app.py - Complete NLP Service for Render Production

import json
import os
import time
import hashlib
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS

print("=" * 70)
print("📚 Library NLP Search Service Starting...")
print("=" * 70)

# ============================================
# CHECK DEPENDENCIES
# ============================================
try:
    from sentence_transformers import SentenceTransformer, util
    SEMANTIC_AVAILABLE = True
    print("✅ sentence-transformers loaded successfully")
except ImportError as e:
    SEMANTIC_AVAILABLE = False
    print("❌ sentence-transformers NOT installed!")
    print(f"   Error: {e}")

try:
    import torch
    print(f"✅ PyTorch loaded (CUDA available: {torch.cuda.is_available()})")
except:
    print("⚠️ PyTorch not available (CPU mode only)")

try:
    import numpy as np
    print("✅ NumPy loaded")
except:
    print("⚠️ NumPy not available")

print("=" * 70)

app = Flask(__name__)
CORS(app)

# ============================================
# GLOBAL CACHE
# ============================================
model = None
book_cache = {
    'embeddings': None,
    'books': None,
    'book_texts': None,
    'timestamp': 0,
    'hash': None
}

# ============================================
# SUPABASE CONFIGURATION
# ============================================
SUPABASE_URL = 'https://olzkpwzebcnmbqhbcyyz.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9semtwd3plYmNubWJxaGJjeXl6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQwMjYxNzcsImV4cCI6MjA5OTYwMjE3N30.GNk7gwaWfi3O-dncbixlkB7M8q6R-UJUe2VMsB5cBTQ'

def supabase_request(endpoint, method='GET', data=None):
    """Make a request to Supabase"""
    import requests
    url = f'{SUPABASE_URL}/rest/v1/{endpoint}'
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }
    
    try:
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=15)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=15)
        elif method == 'PATCH':
            response = requests.patch(url, headers=headers, json=data, timeout=15)
        else:
            response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code >= 400:
            print(f"⚠️ Supabase error: {response.status_code} - {response.text[:200]}")
            return []
        
        return response.json()
    except Exception as e:
        print(f"⚠️ Error in supabase_request: {e}")
        return []

# ============================================
# LOAD BOOKS FUNCTIONS
# ============================================
def load_books_from_supabase():
    """Fetch books from Supabase"""
    try:
        books = supabase_request('books?select=*,categories(name)')
        if books:
            print(f"✅ Loaded {len(books)} books from Supabase")
        return books
    except Exception as e:
        print(f"⚠️ Error loading from Supabase: {e}")
        return []

def load_books_from_json():
    """Fallback: Load from local JSON file"""
    paths = [
        os.path.join(os.path.dirname(__file__), 'books_data.json'),
        'books_data.json'
    ]
    
    for path in paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    books = json.load(f)
                    print(f"✅ Loaded {len(books)} books from {path}")
                    return books
            except Exception as e:
                print(f"⚠️ Error loading {path}: {e}")
    
    print("⚠️ No books found, using sample data")
    return [
        {'id': '1', 'title': 'Atomic Habits', 'author': 'James Clear', 
         'description': 'An easy and proven way to build good habits and break bad ones.',
         'category': 'Self-Help'},
        {'id': '2', 'title': 'Deep Work', 'author': 'Cal Newport',
         'description': 'Rules for focused success in a distracted world.',
         'category': 'Self-Help'},
        {'id': '3', 'title': 'Thinking, Fast and Slow', 'author': 'Daniel Kahneman',
         'description': 'A groundbreaking exploration of how we think and make decisions.',
         'category': 'Psychology'}
    ]

def load_books():
    """Load books from Supabase first, fallback to JSON"""
    books = load_books_from_supabase()
    if not books:
        books = load_books_from_json()
    
    for book in books:
        if 'description' not in book or book['description'] is None:
            book['description'] = ''
        if 'category' not in book and 'categories' in book:
            book['category'] = book['categories'].get('name', '') if book['categories'] else ''
        if 'keywords' not in book or book['keywords'] is None:
            book['keywords'] = ''
        if 'author' not in book or book['author'] is None:
            book['author'] = 'Unknown'
        if 'title' not in book or book['title'] is None:
            book['title'] = 'Untitled'
        if 'cover_image' not in book:
            book['cover_image'] = None
    
    return books

def get_book_text(book):
    """Create rich text for embedding"""
    parts = [
        book.get('title', ''),
        book.get('author', ''),
        book.get('description', ''),
        book.get('category', ''),
        book.get('keywords', ''),
        book.get('isbn', ''),
        book.get('publisher', '')
    ]
    return ' '.join(filter(None, parts)).lower()

def get_books_hash(books):
    """Create a hash of all books to detect changes"""
    book_strings = []
    for book in books:
        key = f"{book.get('id', '')}|{book.get('title', '')}|{book.get('author', '')}|{book.get('description', '')}"
        book_strings.append(key)
    combined = '|'.join(sorted(book_strings))
    return hashlib.md5(combined.encode()).hexdigest()

# ============================================
# MODEL LOADING
# ============================================
def load_model():
    """Load the sentence transformer model"""
    global model, SEMANTIC_AVAILABLE
    
    if not SEMANTIC_AVAILABLE:
        return None
    
    if model is not None:
        return model
    
    try:
        print("🔄 Loading Sentence Transformer model...")
        print("   Model: all-MiniLM-L6-v2 (80MB)")
        print("   This may take a moment on first run...")
        
        model = SentenceTransformer('all-MiniLM-L6-v2')
        
        test_text = "This is a test"
        test_embedding = model.encode(test_text)
        print(f"✅ Model loaded! Embedding dimensions: {len(test_embedding)}")
        
        return model
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        SEMANTIC_AVAILABLE = False
        return None

# ============================================
# CACHE MANAGEMENT
# ============================================
def get_cached_embeddings(books):
    """Compute and cache book embeddings"""
    global book_cache
    
    if not books:
        return None, None
    
    if not SEMANTIC_AVAILABLE:
        return None, None
    
    current_hash = get_books_hash(books)
    
    if (book_cache['embeddings'] is not None and 
        book_cache['hash'] == current_hash):
        print("✅ Using cached embeddings")
        return book_cache['embeddings'], book_cache['book_texts']
    
    print("🔄 Computing new embeddings...")
    
    try:
        model = load_model()
        if model is None:
            return None, None
        
        book_texts = [get_book_text(book) for book in books]
        embeddings = model.encode(book_texts, convert_to_tensor=True, show_progress_bar=False)
        
        book_cache['embeddings'] = embeddings
        book_cache['books'] = books
        book_cache['book_texts'] = book_texts
        book_cache['timestamp'] = time.time()
        book_cache['hash'] = current_hash
        
        print(f"✅ Embeddings computed: {len(embeddings)} vectors")
        return embeddings, book_texts
        
    except Exception as e:
        print(f"❌ Failed to compute embeddings: {e}")
        return None, None

# ============================================
# SEARCH ENDPOINT
# ============================================
@app.route('/search', methods=['POST', 'GET'])
def semantic_search():
    """Main search endpoint with full image support"""
    start_time = time.time()
    
    if request.method == 'POST':
        data = request.json or {}
        query = data.get('query', '').strip()
        search_type = data.get('type', 'semantic')
        limit = data.get('limit', 50)
        min_relevance = data.get('min_relevance', 15)
    else:
        query = request.args.get('q', '').strip()
        search_type = request.args.get('type', 'semantic')
        limit = int(request.args.get('limit', 50))
        min_relevance = int(request.args.get('min_relevance', 15))
    
    if not query:
        return jsonify({'error': 'Query is required', 'results': [], 'count': 0}), 400
    
    print(f"🔍 Search: '{query}' (type: {search_type}, min_relevance: {min_relevance}%)")
    
    books = load_books()
    if not books:
        return jsonify({'error': 'No books available', 'results': [], 'count': 0}), 404
    
    # Semantic Search
    if search_type in ['semantic', 'nlp', 'yewno']:
        try:
            model = load_model()
            
            if model is not None and SEMANTIC_AVAILABLE:
                embeddings, book_texts = get_cached_embeddings(books)
                
                if embeddings is not None:
                    query_embedding = model.encode(query, convert_to_tensor=True)
                    scores = util.cos_sim(query_embedding, embeddings)[0]
                    
                    all_results = []
                    for idx, score in enumerate(scores):
                        relevance = float(score) * 100
                        if relevance >= min_relevance:
                            book = books[idx].copy()
                            book['relevance'] = round(relevance, 2)
                            book['semantic_score'] = round(relevance, 2)
                            book['search_type'] = 'semantic'
                            all_results.append(book)
                    
                    all_results.sort(key=lambda x: x['relevance'], reverse=True)
                    results = all_results[:limit]
                    
                    elapsed = (time.time() - start_time) * 1000
                    print(f"✅ Found {len(results)} semantic results in {elapsed:.0f}ms")
                    
                    return jsonify({
                        'query': query,
                        'type': 'semantic_nlp',
                        'count': len(results),
                        'results': results,
                        'time_ms': round(elapsed, 2),
                        'model': 'all-MiniLM-L6-v2',
                        'min_relevance': min_relevance
                    })
                    
        except Exception as e:
            print(f"❌ Semantic search error: {e}")
            import traceback
            traceback.print_exc()
    
    # Basic Search (Fallback)
    print("🔄 Falling back to basic search...")
    query_lower = query.lower()
    query_words = [w for w in query_lower.split() if len(w) > 2]
    results = []
    
    for book in books:
        text = get_book_text(book)
        score = 0
        
        title = book.get('title', '').lower()
        if query_lower in title:
            score += 50
        elif any(word in title for word in query_words):
            score += 20
        
        author = book.get('author', '').lower()
        if query_lower in author:
            score += 30
        elif any(word in author for word in query_words):
            score += 15
        
        desc = book.get('description', '').lower()
        if query_lower in desc:
            score += 20
        elif any(word in desc for word in query_words):
            score += 10
        
        category = book.get('category', '').lower()
        if query_lower in category:
            score += 15
        elif any(word in category for word in query_words):
            score += 8
        
        keywords = book.get('keywords', '').lower()
        if query_lower in keywords:
            score += 15
        
        if score > 0:
            book_copy = book.copy()
            book_copy['relevance'] = score
            book_copy['search_type'] = 'basic'
            results.append(book_copy)
    
    results.sort(key=lambda x: x['relevance'], reverse=True)
    elapsed = (time.time() - start_time) * 1000
    
    print(f"✅ Found {len(results)} basic results in {elapsed:.0f}ms")
    
    return jsonify({
        'query': query,
        'type': 'basic',
        'count': len(results),
        'results': results[:limit],
        'time_ms': round(elapsed, 2)
    })

# ============================================
# PREDICT ENDPOINT - Zero-Query Predictor
# ============================================
@app.route('/predict', methods=['POST'])
def predict_intent():
    """Predict search intent before user finishes typing"""
    data = request.json or {}
    partial_query = data.get('partial_query', '')
    grade_level = data.get('grade_level', 'Grade 10')
    subjects = data.get('subjects', [])
    history = data.get('search_history', [])
    
    if not partial_query or len(partial_query) < 2:
        return jsonify({
            'predictions': [],
            'message': 'Query too short for prediction'
        })
    
    try:
        model = load_model()
        if model is None:
            return jsonify({'predictions': [], 'message': 'NLP model not available'})
        
        books = load_books()
        embeddings, _ = get_cached_embeddings(books)
        
        if embeddings is None:
            return jsonify({'predictions': [], 'message': 'No books available'})
        
        # Create context with grade level and subjects
        context_text = f"{grade_level} {' '.join(subjects[:5])} {' '.join(history[:10])}"
        query_with_context = f"{partial_query} {context_text}"
        query_embedding = model.encode(query_with_context, convert_to_tensor=True)
        
        # Compute similarities
        scores = util.cos_sim(query_embedding, embeddings)[0]
        
        # Get predictions
        predictions = []
        for idx, score in enumerate(scores):
            relevance = float(score) * 100
            if relevance > 10:
                book = books[idx].copy()
                book['relevance'] = round(relevance, 2)
                book['prediction_score'] = round(relevance, 2)
                book['is_prediction'] = True
                predictions.append(book)
        
        predictions.sort(key=lambda x: x['relevance'], reverse=True)
        
        return jsonify({
            'query': partial_query,
            'predictions': predictions[:5],
            'count': len(predictions[:5]),
            'grade_level': grade_level,
            'message': f'Showing predictions for {partial_query}...'
        })
        
    except Exception as e:
        print(f"❌ Prediction error: {e}")
        return jsonify({'predictions': [], 'message': f'Prediction error: {str(e)}'})

# ============================================
# ANALYZE SESSION - Frustration Detection
# ============================================
@app.route('/analyze_session', methods=['POST'])
def analyze_session():
    """Analyze user session for research frustration patterns"""
    data = request.json or {}
    queries = data.get('queries', [])
    clicks = data.get('clicks', [])
    abandoned = data.get('abandoned', [])
    
    if len(queries) < 2:
        return jsonify({
            'frustration_detected': False,
            'message': 'Not enough search data to analyze'
        })
    
    try:
        model = load_model()
        if model is None:
            return jsonify({
                'frustration_detected': False,
                'message': 'NLP model not available'
            })
        
        query_embeddings = model.encode(queries, convert_to_tensor=True)
        similarities = []
        
        for i in range(len(query_embeddings) - 1):
            sim = util.cos_sim(query_embeddings[i], query_embeddings[i+1])[0][0].item()
            similarities.append(sim)
        
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0
        low_similarity_count = sum(1 for s in similarities if s < 0.3)
        high_abandonment = sum(1 for a in abandoned if a) / len(abandoned) if abandoned else 0
        low_clicks = sum(1 for c in clicks if c < 1) / len(clicks) if clicks else 0
        
        frustration_score = 0
        reasons = []
        
        if low_similarity_count > len(similarities) * 0.5:
            frustration_score += 40
            reasons.append("Frequent topic switching")
        
        if high_abandonment > 0.5:
            frustration_score += 30
            reasons.append("High search abandonment")
        
        if low_clicks > 0.6:
            frustration_score += 30
            reasons.append("Low click-through rate")
        
        if avg_similarity < 0.2:
            frustration_score += 20
            reasons.append("Very low query similarity")
        
        frustration_detected = frustration_score > 50
        
        suggestions = []
        if frustration_detected:
            suggestions = [
                "📚 It looks like you're having trouble finding what you need. Would you like to schedule a consultation with the librarian?",
                "🔍 Try using simpler keywords or check our beginner's guide to library resources.",
                "📖 Browse our curated collections by subject to discover related materials."
            ]
        
        return jsonify({
            'frustration_detected': frustration_detected,
            'frustration_score': frustration_score,
            'avg_similarity': round(avg_similarity, 3),
            'reasons': reasons,
            'message': 'Frustration pattern detected' if frustration_detected else 'Normal search pattern',
            'suggestions': suggestions if frustration_detected else None
        })
        
    except Exception as e:
        print(f"❌ Session analysis error: {e}")
        return jsonify({
            'frustration_detected': False,
            'message': f'Analysis error: {str(e)}'
        })

# ============================================
# CLASSIFY BOOK - Automated Classification
# ============================================
@app.route('/classify', methods=['POST'])
def classify_book():
    """Automatically classify books based on curriculum competencies"""
    data = request.json or {}
    title = data.get('title', '')
    description = data.get('description', '')
    author = data.get('author', '')
    book_id = data.get('book_id')
    
    if not title or not description:
        return jsonify({
            'success': True,
            'suggestions': [
                {
                    'category_id': None,
                    'category_name': 'General',
                    'subject': 'General',
                    'grade_level': 'All Grades',
                    'score': 30,
                    'tags': ['Book', 'General']
                }
            ],
            'tags': ['Book', 'General'],
            'message': 'Please provide title and description for better classification'
        })
    
    try:
        # Simple keyword-based classification
        text = (title + ' ' + description + ' ' + author).lower()
        
        # Subject detection
        categories = {
            'History': ['history', 'historical', 'revolution', 'colonial', 'philippine', 'spanish', 'american', 'war', 'ancient', 'medieval'],
            'Science': ['biology', 'chemistry', 'physics', 'science', 'cells', 'genetics', 'ecology', 'evolution', 'energy', 'force'],
            'Mathematics': ['algebra', 'calculus', 'geometry', 'trigonometry', 'math', 'statistics', 'probability', 'numbers'],
            'English': ['literature', 'poetry', 'essay', 'grammar', 'writing', 'reading', 'novel', 'english'],
            'Filipino': ['panitikan', 'wika', 'filipino', 'tula', 'akda', 'kwento'],
            'Araling Panlipunan': ['araling panlipunan', 'ap', 'kabihasnan', 'lipunan', 'kultura', 'politika', 'ekonomiya'],
            'Technology': ['programming', 'coding', 'software', 'hardware', 'computer', 'database'],
            'Psychology': ['psychology', 'mental', 'behavior', 'mind', 'thinking', 'cognitive'],
            'Business': ['business', 'management', 'marketing', 'finance', 'accounting'],
            'Self-Help': ['self-help', 'improvement', 'growth', 'personal', 'motivation', 'inspiration']
        }
        
        # Grade detection
        grades = {
            'Grade 7': ['grade 7', '7th grade', 'grade seven'],
            'Grade 8': ['grade 8', '8th grade', 'grade eight'],
            'Grade 9': ['grade 9', '9th grade', 'grade nine'],
            'Grade 10': ['grade 10', '10th grade', 'grade ten'],
            'Grade 11': ['grade 11', '11th grade', 'grade eleven'],
            'Grade 12': ['grade 12', '12th grade', 'grade twelve', 'senior high']
        }
        
        best_category = 'General'
        best_score = 0
        
        for cat, keywords in categories.items():
            score = 0
            for keyword in keywords:
                if keyword in text:
                    score += 10
            if score > best_score:
                best_score = score
                best_category = cat
        
        # Find grade
        found_grade = 'All Grades'
        for grade, keywords in grades.items():
            for keyword in keywords:
                if keyword in text:
                    found_grade = grade
                    break
        
        # Generate tags
        tags = []
        words = text.split()
        common_words = ['the', 'a', 'an', 'and', 'or', 'but', 'for', 'on', 'at', 'to', 'in', 'with', 'without', 'by', 'of', 'from']
        
        for word in words:
            word = word.strip()
            if len(word) > 3 and word not in common_words:
                tags.append(word.capitalize())
        
        tags = list(dict.fromkeys(tags))[:7]  # Remove duplicates, limit to 7
        tags.append(best_category)
        if found_grade != 'All Grades':
            tags.append(found_grade)
        
        return jsonify({
            'success': True,
            'suggestions': [
                {
                    'category_id': None,
                    'category_name': best_category,
                    'subject': best_category,
                    'grade_level': found_grade,
                    'score': min(best_score + 30, 95),
                    'tags': tags
                }
            ],
            'tags': tags,
            'message': 'Book classified successfully'
        })
        
    except Exception as e:
        print(f"❌ Classification error: {e}")
        return jsonify({
            'success': True,
            'suggestions': [
                {
                    'category_id': None,
                    'category_name': 'General',
                    'subject': 'General',
                    'grade_level': 'All Grades',
                    'score': 40,
                    'tags': ['Book', 'General']
                }
            ],
            'tags': ['Book', 'General'],
            'message': 'Classification with fallback'
        })

# ============================================
# HEALTH CHECK
# ============================================
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    books = load_books()
    return jsonify({
        'status': 'running',
        'semantic_available': SEMANTIC_AVAILABLE,
        'model_loaded': model is not None,
        'books_count': len(books),
        'timestamp': time.time()
    })

# ============================================
# REINDEX
# ============================================
@app.route('/reindex', methods=['POST'])
def reindex_books():
    """Force reindex of books"""
    global book_cache
    book_cache = {
        'embeddings': None,
        'books': None,
        'book_texts': None,
        'timestamp': 0,
        'hash': None
    }
    print("🗑️ Cache cleared")
    return jsonify({'success': True, 'message': 'Cache cleared'})

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    print("=" * 70)
    print("🚀 Starting NLP Search Service...")
    print("=" * 70)
    print(f"✅ Semantic Search: {'ENABLED' if SEMANTIC_AVAILABLE else 'DISABLED'}")
    
    if SEMANTIC_AVAILABLE:
        try:
            load_model()
        except Exception as e:
            print(f"⚠️ Model pre-load failed: {e}")
    
    books = load_books()
    print(f"📊 Books available: {len(books)}")
    
    images_count = sum(1 for b in books if b.get('cover_image'))
    print(f"🖼️ Books with images: {images_count}")
    
    print("=" * 70)
    print("🌐 Server running on Render")
    print("📡 POST /search  - Search books")
    print("📡 POST /predict  - Predict search intent")
    print("📡 POST /analyze_session - Analyze user session")
    print("📡 POST /classify - Classify books")
    print("📡 GET  /health  - Health check")
    print("📡 POST /reindex - Clear cache")
    print("=" * 70)
    
    # For Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)