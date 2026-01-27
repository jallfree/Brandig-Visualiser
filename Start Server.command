#!/bin/bash

# Staycold Branding Visualiser - Start Script
# Double-click this file to start the server

# Get the directory where this script is located
cd "$(dirname "$0")"

echo "=================================================="
echo "  Staycold Branding Visualiser"
echo "=================================================="
echo ""
echo "Starting server..."
echo ""

# Check if Flask is installed
python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Flask not installed. Installing now..."
    pip3 install flask flask-cors
    echo ""
fi

# Open browser after a short delay
(sleep 2 && open "http://localhost:5050/") &

# Start the server
python3 server.py
