#!/bin/bash

# Setup cron jobs for Business Assistant GO

echo "Setting up cron jobs..."

# Create cron entries
crontab -l > /tmp/current_crontab 2>/dev/null || echo "# New crontab" > /tmp/current_crontab

# Add cron jobs for timeout checking
# Check every minute

PROJECT_DIR="/opt/business-assistant-go"
PYTHON_PATH="$PROJECT_DIR/venv/bin/python"

cat >> /tmp/current_crontab << EOF

# Business Assistant GO - Cron Jobs
# Check cafe timeouts every minute
* * * * * cd $PROJECT_DIR && $PYTHON_PATH src/cron_jobs.py cafe >> logs/cron.log 2>&1

# Check pharmacy timeouts every minute
* * * * * cd $PROJECT_DIR && $PYTHON_PATH src/cron_jobs.py pharmacy >> logs/cron.log 2>&1

# Check taxi timeouts every minute
* * * * * cd $PROJECT_DIR && $PYTHON_PATH src/cron_jobs.py taxi >> logs/cron.log 2>&1
EOF

# Install new crontab
crontab /tmp/current_crontab
rm /tmp/current_crontab

echo "Cron jobs installed successfully!"
echo "Current cron jobs:"
crontab -l
