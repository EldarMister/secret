#!/bin/bash

# Deploy script for Business Assistant GO
# Usage: ./deploy.sh [environment]

ENV=${1:-production}

echo "=========================================="
echo "Business Assistant GO - Deployment"
echo "Environment: $ENV"
echo "=========================================="

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3.12 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create logs directory
mkdir -p logs

# Check .env file
if [ ! -f ".env" ]; then
    echo "WARNING: .env file not found!"
    echo "Please copy .env.example to .env and configure it."
    exit 1
fi

# Run database initialization
echo "Initializing database..."
python -c "from src.db import get_db; get_db()"

# Start the application
echo "Starting application..."
if [ "$ENV" = "development" ]; then
    echo "Running in development mode..."
    python src/app.py
else
    echo "Running in production mode with Gunicorn..."
    gunicorn -w 4 -b 0.0.0.0:5000 --access-logfile logs/access.log --error-logfile logs/error.log src.app:app
fi
