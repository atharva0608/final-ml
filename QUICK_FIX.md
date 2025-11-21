# Quick Fix for Backend Not Running

## Issue
Backend is not running and frontend can't connect (ERR_CONNECTION_REFUSED on port 5000)

## Diagnosis
The setup script completed but backend service was not started or failed to start.

## Quick Fix Steps

### Step 1: Check what happened during setup

```bash
# On your Ubuntu server:
tail -100 /var/log/cloud-init-output.log  # If using cloud-init
# OR
journalctl -xe | grep spot-optimizer
```

### Step 2: Start backend manually (FASTEST FIX)

```bash
cd ~/final-ml

# Create quick startup script
cat > start_backend.sh << 'EOF'
#!/bin/bash
cd ~/final-ml/backend

# Create virtual environment if doesn't exist
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate and install requirements
source venv/bin/activate
pip install -q -r requirements.txt

# Create .env file
cat > .env << 'ENVEOF'
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=spotuser
DB_PASSWORD=spotpassword
DB_NAME=spot_optimizer
PORT=5000
FLASK_ENV=production
ENVEOF

# Start backend
echo "Starting backend on port 5000..."
python backend.py
EOF

chmod +x start_backend.sh

# Run it in background
nohup ./start_backend.sh > backend.log 2>&1 &

# Check if it started
sleep 3
curl http://localhost:5000/health
```

### Step 3: If MySQL permission errors are blocking

The MySQL errors you see are warnings but MySQL is still running. However, if backend can't connect to MySQL:

```bash
# Test MySQL connection
docker exec spot-mysql mysql -u spotuser -pspotpassword -e "SELECT 1;"

# If fails, recreate database user
docker exec spot-mysql mysql -u root -pspotpassword -e "
DROP USER IF EXISTS 'spotuser'@'%';
CREATE USER 'spotuser'@'%' IDENTIFIED BY 'spotpassword';
GRANT ALL PRIVILEGES ON spot_optimizer.* TO 'spotuser'@'%';
FLUSH PRIVILEGES;
"
```

### Step 4: Proper fix - Re-run setup

If quick start works, then properly deploy:

```bash
cd ~/final-ml/scripts

# Clean up any partial installation
sudo systemctl stop spot-optimizer-backend 2>/dev/null || true
sudo rm -rf /home/ubuntu/spot-optimizer

# Re-run setup
sudo ./setup.sh
```

### Step 5: Verify everything works

```bash
# Check backend
curl http://localhost:5000/health
# Should return: {"status":"healthy"}

# Check MySQL
docker exec spot-mysql mysql -u spotuser -pspotpassword spot_optimizer -e "SHOW TABLES;"
# Should list all tables

# Check frontend
curl http://localhost/
# Should return HTML

# Check backend service (after proper setup)
sudo systemctl status spot-optimizer-backend
```

## Root Cause Analysis

The setup script likely encountered one of these issues:

1. **File path mismatch**: Setup script looks for `backend.py` instead of `backend/backend.py`
   - We fixed this in setup.sh but you might have old version

2. **Permission issues**: systemd service can't start because of file permissions

3. **Python dependencies**: Missing packages or wrong Python version

4. **Database not ready**: Backend tried to start before MySQL was fully ready

## Check Current Setup Status

```bash
# On Ubuntu server, check what was actually deployed:
ls -la ~/spot-optimizer/
ls -la ~/final-ml/backend/

# Check if backend files exist in repo
ls -la ~/final-ml/backend/backend.py
ls -la ~/final-ml/backend/requirements.txt

# Check current setup.sh version
grep "backend/backend.py" ~/final-ml/scripts/setup.sh
# Should find the new path, if not, you have old version
```

## Pull Latest Code

If you cloned before the latest fixes:

```bash
cd ~/final-ml
git fetch origin
git checkout claude/restructure-project-files-01LApGgohR1kUwktsXZWprsr
git pull origin claude/restructure-project-files-01LApGgohR1kUwktsXZWprsr

# Now re-run setup
cd scripts
sudo ./setup.sh
```

## Quick Python Backend Test

Test if backend code works at all:

```bash
cd ~/final-ml/backend

# Test import
python3 -c "import sys; print('Python:', sys.version)"

# Test Flask
python3 -c "import flask; print('Flask:', flask.__version__)"

# Test MySQL connector
python3 -c "import mysql.connector; print('MySQL Connector:', mysql.connector.__version__)"

# If any fail, install:
pip3 install Flask==3.0.0 flask-cors==4.0.0 mysql-connector-python==8.2.0
```

## Expected State After Fix

```
Services:
✓ MySQL container running on port 3306
✓ Backend running on port 5000
✓ Nginx running on port 80
✓ Frontend built and served by Nginx

Connections:
Frontend (http://your-ip/) → Nginx → Backend (localhost:5000) → MySQL (localhost:3306)
```

## Still Not Working?

If backend still won't start, check logs:

```bash
# Backend logs (if using systemd)
sudo journalctl -u spot-optimizer-backend -n 100

# Or check manual start log
tail -f ~/final-ml/backend.log

# Check what's using port 5000
sudo netstat -tlnp | grep 5000
# or
sudo lsof -i :5000
```

## Emergency: Run Backend in Foreground (Debug Mode)

```bash
cd ~/final-ml/backend
source venv/bin/activate 2>/dev/null || python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

export DB_HOST=127.0.0.1
export DB_USER=spotuser
export DB_PASSWORD=spotpassword
export DB_NAME=spot_optimizer
export PORT=5000

# Run in foreground to see errors
python backend.py
```

This will show you exactly what's failing.
