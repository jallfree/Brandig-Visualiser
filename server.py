#!/usr/bin/env python3
"""
Staycold Branding Visualiser Server
Handles file serving, product management, and image uploads
"""

from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS
import json
import os
import shutil
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_DIR = os.path.join(BASE_DIR, 'products')
PRODUCTS_FILE = os.path.join(BASE_DIR, 'products.json')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_products():
    try:
        with open(PRODUCTS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"products": []}

def save_products(data):
    with open(PRODUCTS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def generate_id(name):
    """Generate a URL-safe ID from product name"""
    return name.lower().replace(' ', '-').replace('/', '-')

# Serve static HTML files
@app.route('/')
def index():
    return send_file(os.path.join(BASE_DIR, 'index.html'))

@app.route('/customizer')
def customizer():
    return send_file(os.path.join(BASE_DIR, 'customizer.html'))

@app.route('/settings')
def settings():
    return send_file(os.path.join(BASE_DIR, 'settings.html'))

# Serve static files (CSS, JS, etc.)
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'static'), filename)

# Serve product images
@app.route('/products/<product_id>/<filename>')
def serve_product_image(product_id, filename):
    product_dir = os.path.join(PRODUCTS_DIR, product_id)
    return send_from_directory(product_dir, filename)

# API: Get product config (positioning data)
@app.route('/api/products/<product_id>/config', methods=['GET'])
def get_product_config(product_id):
    config_path = os.path.join(PRODUCTS_DIR, product_id, 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({}), 200

# API: Get all products
@app.route('/api/products', methods=['GET'])
def get_products():
    data = load_products()
    return jsonify(data['products'])

# API: Get single product
@app.route('/api/products/<product_id>', methods=['GET'])
def get_product(product_id):
    data = load_products()
    for product in data['products']:
        if product['id'] == product_id:
            return jsonify(product)
    return jsonify({"error": "Product not found"}), 404

# API: Create new product
@app.route('/api/products', methods=['POST'])
def create_product():
    data = load_products()

    product_data = request.json
    product_id = generate_id(product_data['name'])

    # Check if ID already exists
    for p in data['products']:
        if p['id'] == product_id:
            return jsonify({"error": "Product with this name already exists"}), 400

    # Create product folder
    product_dir = os.path.join(PRODUCTS_DIR, product_id)
    os.makedirs(product_dir, exist_ok=True)

    new_product = {
        "id": product_id,
        "name": product_data['name'],
        "category": product_data['category'],
        "areas": product_data.get('areas', []),
        "hasOverlay": False,
        "images": {}
    }

    data['products'].append(new_product)
    save_products(data)

    return jsonify(new_product), 201

# API: Update product
@app.route('/api/products/<product_id>', methods=['PUT'])
def update_product(product_id):
    data = load_products()

    for i, product in enumerate(data['products']):
        if product['id'] == product_id:
            update_data = request.json
            product['name'] = update_data.get('name', product['name'])
            product['category'] = update_data.get('category', product['category'])
            product['areas'] = update_data.get('areas', product['areas'])
            data['products'][i] = product
            save_products(data)
            return jsonify(product)

    return jsonify({"error": "Product not found"}), 404

# API: Delete product
@app.route('/api/products/<product_id>', methods=['DELETE'])
def delete_product(product_id):
    data = load_products()

    for i, product in enumerate(data['products']):
        if product['id'] == product_id:
            # Remove product folder
            product_dir = os.path.join(PRODUCTS_DIR, product_id)
            if os.path.exists(product_dir):
                shutil.rmtree(product_dir)

            del data['products'][i]
            save_products(data)
            return jsonify({"success": True})

    return jsonify({"error": "Product not found"}), 404

# API: Upload image for product
@app.route('/api/products/<product_id>/upload', methods=['POST'])
def upload_image(product_id):
    data = load_products()

    # Find product
    product = None
    product_index = -1
    for i, p in enumerate(data['products']):
        if p['id'] == product_id:
            product = p
            product_index = i
            break

    if not product:
        return jsonify({"error": "Product not found"}), 404

    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    image_type = request.form.get('type', 'main')  # main, mask-front, mask-side, mask-canopy, mask-glass, overlay

    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if file and allowed_file(file.filename):
        # Determine filename based on type
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{image_type}.{ext}"

        # Save file
        product_dir = os.path.join(PRODUCTS_DIR, product_id)
        os.makedirs(product_dir, exist_ok=True)
        filepath = os.path.join(product_dir, filename)
        file.save(filepath)

        # Update product record
        if 'images' not in product:
            product['images'] = {}
        product['images'][image_type] = filename

        if image_type == 'overlay':
            product['hasOverlay'] = True

        data['products'][product_index] = product
        save_products(data)

        return jsonify({
            "success": True,
            "filename": filename,
            "type": image_type
        })

    return jsonify({"error": "Invalid file type"}), 400

# API: Delete image from product
@app.route('/api/products/<product_id>/images/<image_type>', methods=['DELETE'])
def delete_image(product_id, image_type):
    data = load_products()

    for i, product in enumerate(data['products']):
        if product['id'] == product_id:
            if 'images' in product and image_type in product['images']:
                # Delete file
                filename = product['images'][image_type]
                filepath = os.path.join(PRODUCTS_DIR, product_id, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)

                # Update record
                del product['images'][image_type]
                if image_type == 'overlay':
                    product['hasOverlay'] = False

                data['products'][i] = product
                save_products(data)

            return jsonify({"success": True})

    return jsonify({"error": "Product not found"}), 404

if __name__ == '__main__':
    # Ensure products directory exists
    os.makedirs(PRODUCTS_DIR, exist_ok=True)

    print("=" * 50)
    print("Staycold Branding Visualiser Server")
    print("=" * 50)
    print(f"Home page:    http://localhost:5051/")
    print(f"Settings:     http://localhost:5051/settings")
    print("=" * 50)

    app.run(host='localhost', port=5051, debug=True)
