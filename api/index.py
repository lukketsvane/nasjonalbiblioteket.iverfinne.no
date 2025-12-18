#!/usr/bin/env python3
"""
Vercel serverless entry point for the NBNO web application.
This wraps the Flask app for deployment on Vercel.
"""
import sys
import os
import re

import requests
from flask import Flask, render_template, request, jsonify, Response, send_from_directory

# Add the root directory to the path so we can import nbno module
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# Create Flask app with correct template and static paths
app = Flask(
    __name__,
    template_folder=os.path.join(ROOT_DIR, 'web', 'templates'),
    static_folder=os.path.join(ROOT_DIR, 'web', 'static'),
    static_url_path='/static'
)

# Import the Book class for citation functionality
from nbno import Book


@app.route('/', methods=['GET'])
def index():
    """Main page - simplified for Vercel (no download functionality)."""
    return render_template('index.html', books=[], ocrlangs=[])


@app.route('/citation', methods=['GET', 'POST'])
def citation():
    """Generate citations from nb.no URLs or media IDs."""
    if request.method == 'GET':
        return render_template('citation.html')
    
    # POST: process the URL/ID and return citation formats
    url_or_id = request.json.get('url', '').strip()
    if not url_or_id:
        return jsonify({'error': 'Mangler URL eller ID'}), 400
    
    # Extract media ID from URL if needed
    media_id = url_or_id
    if 'nb.no/items/' in url_or_id:
        # Extract ID from URL like https://www.nb.no/items/37d98942e04aa67503580d489b760ef5
        match = re.search(r'/items/([a-f0-9]+)', url_or_id)
        if match:
            media_id = match.group(1)
    elif url_or_id.startswith('URN:NBN:'):
        # Handle URN format
        media_id = url_or_id
    
    try:
        # Fetch metadata using the Book class
        book = Book(media_id)
        
        # Extract metadata fields
        metadata_dict = {}
        for item in book.raw_metadata:
            label = item.get('label', '')
            value = item.get('value', '')
            metadata_dict[label] = value
        
        # Build citation data
        title = metadata_dict.get('Tittel') or metadata_dict.get('Alternativ tittel') or book.title
        author = metadata_dict.get('Forfatter', '')
        year = metadata_dict.get('Publisert', '')
        publisher = metadata_dict.get('Forlag', '')
        place = metadata_dict.get('Utgivelsessted', '')
        isbn = metadata_dict.get('ISBN', '')
        
        # Extract year from "Publisert" field (might contain full date or year)
        year_match = re.search(r'\d{4}', year)
        if year_match:
            year = year_match.group(0)
        
        # Generate URN from the book's digimedie
        urn = f"URN:NBN:no-nb_{book.media_type}_{book.media_id}"
        urn_url = f"https://urn.nb.no/{urn}"
        
        # Generate different citation formats
        citations = {
            'bokmal': generate_citation_bokmal(author, year, title, isbn, place, publisher, urn_url),
            'nynorsk': generate_citation_nynorsk(author, year, title, isbn, place, publisher, urn_url),
            'lokalhistorie': generate_citation_lokalhistorie(author, title, publisher, place, year, urn),
            'metadata': metadata_dict,
            'urn': urn,
            'urn_url': urn_url
        }
        
        return jsonify(citations)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def generate_citation_bokmal(author, year, title, isbn, place, publisher, urn_url):
    """Generate Wikipedia Bokmål citation format."""
    parts = ["{{ Kilde bok"]
    if author:
        parts.append(f" | forfatter = {author}")
    if year:
        parts.append(f" | utgivelsesår = {year}")
    if title:
        parts.append(f" | tittel = {title}")
    if isbn:
        parts.append(f" | isbn = {isbn}")
    if place:
        parts.append(f" | utgivelsessted = {place}")
    if publisher:
        parts.append(f" | forlag = {publisher}")
    if urn_url:
        parts.append(f" | url = {urn_url}")
    parts.append(" | side = }}")
    return "\n".join(parts)


def generate_citation_nynorsk(author, year, title, isbn, place, publisher, urn_url):
    """Generate Wikipedia Nynorsk citation format."""
    parts = ["{{ Kjelde bok"]
    if author:
        parts.append(f" | forfattar = {author}")
    if year:
        parts.append(f" | utgjeve år = {year}")
    if title:
        parts.append(f" | tittel = {title}")
    if isbn:
        parts.append(f" | isbn = {isbn}")
    if place:
        parts.append(f" | stad = {place}")
    if publisher:
        parts.append(f" | forlag = {publisher}")
    if urn_url:
        parts.append(f" | url = {urn_url}")
    parts.append(" | side = }}")
    return "\n".join(parts)


def generate_citation_lokalhistorie(author, title, publisher, place, year, urn):
    """Generate Local History Wiki citation format."""
    parts = []
    if author:
        parts.append(f"{author}.")
    if title:
        parts.append(f"''{title}''.")
    if publisher:
        parts.append(f"Utg. {publisher}.")
    if place:
        parts.append(f"{place}.")
    if year:
        parts.append(f"{year}.")
    if urn:
        # Extract just the NBN part
        nbn = urn.replace('URN:NBN:no-nb_', 'NBN:no-nb_')
        parts.append(f"{{{{{nbn}}}}}.")
    return " ".join(parts)


@app.route('/preview', methods=['GET'])
def preview():
    """Return metadata/thumbnails for a given media ID (used in queue preview)."""
    media_id = request.args.get('id', '').strip()
    if not media_id:
        return jsonify({'error': 'Missing id parameter'}), 400
    try:
        book = Book(media_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    thumb = None
    preview_page = None
    # try a C1 cover thumbnail first
    if 'C1' in book.page_url:
        c1_url = f"{book.page_url['C1']}/full/!200,200/0/native.jpg"
        try:
            resp = requests.head(c1_url, timeout=5)
            if resp.status_code == 200:
                thumb = c1_url
                preview_page = 'C1'
        except Exception:
            pass
    # fallback to first numeric page thumbnail
    if not thumb and book.page_names:
        preview_page = book.page_names[0]
        thumb = f"{book.page_url[preview_page]}/full/!200,200/0/native.jpg"
    data = {
        'title': book.title,
        'type': book.media_type,
        'pages': book.num_pages,
        'preview_page': preview_page,
        'thumbnail': thumb,
        'access': book.tilgang,
        'metadata': book.raw_metadata,
    }
    return jsonify(data)


@app.route('/logs/<path:subpath>', methods=['GET'])
def serve_logs(subpath):
    """Serve log files - returns empty for Vercel deployment."""
    # In Vercel serverless, we don't have persistent logs
    return ('', 200, {'Content-Type': 'text/plain'})


@app.route('/favicon.ico', methods=['GET'])
def favicon_ico():
    """Serve favicon.ico - uses PNG image with ICO-compatible mimetype."""
    return send_from_directory(
        os.path.join(ROOT_DIR, 'web', 'static', 'img'),
        'logo.png',
        mimetype='image/x-icon'
    )


@app.route('/favicon.png', methods=['GET'])
def favicon_png():
    """Serve favicon.png from static directory."""
    return send_from_directory(
        os.path.join(ROOT_DIR, 'web', 'static', 'img'),
        'logo.png',
        mimetype='image/png'
    )


# For Vercel serverless functions
handler = app
