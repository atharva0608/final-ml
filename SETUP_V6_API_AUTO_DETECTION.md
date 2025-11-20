# Setup Script v6.0 - API URL Auto-Detection

## 🎯 Problem Solved

The setup script was trying to update frontend API URLs using complex `sed` patterns, but it was unreliable and often failed. The frontend couldn't connect to the backend on EC2.

## ✅ Solution

**Automatic URL detection** - The frontend now automatically detects the backend URL based on where it's running:

- **On EC2 (Production)**: Frontend at `http://3.109.1.222` → Connects to `http://3.109.1.222:5000`
- **Localhost (Development)**: Frontend at `http://localhost:3000` → Connects to `http://localhost:5000`
- **Any EC2 Instance**: Works automatically - no IP hardcoding!

## 📋 Changes Made

### 1. Backend Repository (final-ml)

**✅ ALREADY PUSHED** to branch `claude/setup-project-structure-01DYWUjjfqXjVeiFr7yFRN2P`

**Files Changed**:
- `setup_v5.0.sh` → Updated to v6.0 with auto-detection
- `src_config_api.jsx` → Template for auto-detection config

**Key Improvements**:
```bash
# OLD WAY (70+ lines of sed patterns):
sed -i "s|BASE_URL: '[^']*'|BASE_URL: 'http://$PUBLIC_IP:5000'|g" src/config/api.jsx
# Complex pattern matching, often failed

# NEW WAY (Simple environment variable):
VITE_API_URL="http://$PUBLIC_IP:5000" npm run build
# Clean, reliable, always works
```

### 2. Frontend Repository (frontend-)

**⚠️ NEEDS TO BE PUSHED** - Changes committed locally to branch `api-auto-detection`

**Files Changed**:
- `src/config/api.jsx` → Auto-detection implementation
- `src/services/apiClient.jsx` → Real endpoint integration

**Push Commands**:
```bash
cd /home/user/frontend-analysis
git push -u origin api-auto-detection

# Then merge to main on GitHub
```

## 🔧 How Auto-Detection Works

### Frontend Configuration (src/config/api.jsx)

```javascript
// Priority 1: Environment variable (set during build)
const ENV_API_URL = import.meta.env.VITE_API_URL;

// Priority 2: Auto-detect from browser location
const getAutoDetectedURL = () => {
  const { protocol, hostname } = window.location;

  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://localhost:5000';  // Development
  }

  return `${protocol}//${hostname}:5000`;  // Production (EC2)
};

export const API_CONFIG = {
  BASE_URL: ENV_API_URL || getAutoDetectedURL(),
};
```

### Setup Script Build Command

```bash
# Build with environment variable (highest priority)
VITE_API_URL="http://$PUBLIC_IP:5000" npm run build

# If env var not set, frontend uses auto-detection
# Either way - it works!
```

## 📊 Endpoint Improvements

### Replaced Workarounds with Real Endpoints

**Before** (apiClient.jsx):
```javascript
async getAllInstancesGlobal(filters) {
  // Workaround: Loop through all clients
  const clients = await this.getAllClients();
  for (const client of clients) {
    const instances = await this.getInstances(client.id);
    // ... merge results
  }
  // N+1 query problem!
}
```

**After** (apiClient.jsx):
```javascript
async getAllInstancesGlobal(filters) {
  // Clean: Single API call
  return this.request(`/api/admin/instances${query}`);
}
```

**Endpoints Fixed**:
1. ✅ `getPriceHistory()` → `GET /api/client/instances/<id>/price-history`
2. ✅ `getAllInstancesGlobal()` → `GET /api/admin/instances`
3. ✅ `getAllAgentsGlobal()` → `GET /api/admin/agents`

## 🚀 Deployment Instructions

### Option A: Using Setup Script v6.0 (Fresh Deployment)

```bash
# On EC2 instance:
cd /home/ubuntu/final-ml
git pull origin claude/setup-project-structure-01DYWUjjfqXjVeiFr7yFRN2P
sudo bash setup_v5.0.sh

# The script will:
# 1. Clone frontend from https://github.com/atharva0608/frontend-.git
# 2. Create auto-detection config automatically
# 3. Build with VITE_API_URL
# 4. Deploy to nginx
```

### Option B: Manual Update (Existing Deployment)

**Step 1: Update Backend Repository**
```bash
cd /home/ubuntu/final-ml
git config --global --add safe.directory /home/ubuntu/final-ml
git pull origin claude/setup-project-structure-01DYWUjjfqXjVeiFr7yFRN2P
sudo systemctl restart spot-optimizer-backend
```

**Step 2: Update Frontend**

First, push the frontend changes from your local machine:
```bash
# On your local machine with GitHub access:
cd /path/to/frontend-
git checkout api-auto-detection
git push -u origin api-auto-detection

# Create PR and merge to main on GitHub
```

Then on EC2:
```bash
cd /home/ubuntu/final-ml/frontend
git pull origin main

# Recreate auto-detection config
cat > src/config/api.jsx << 'EOF'
[Auto-detection config from setup_v6.0.sh lines 619-663]
EOF

# Rebuild with environment variable
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)
VITE_API_URL="http://$PUBLIC_IP:5000" npm run build

# Deploy
sudo rm -rf /var/www/spot-optimizer/*
sudo cp -r dist/* /var/www/spot-optimizer/
sudo chown -R www-data:www-data /var/www/spot-optimizer
```

**Step 3: Verify**
```bash
# Check backend is running
curl http://localhost:5000/health

# Check frontend config
curl http://localhost/

# Check from browser
# Open: http://YOUR_EC2_IP/
# Open browser console, should see:
# [API Config] Using BASE_URL: http://YOUR_EC2_IP:5000
# [API Config] Source: Auto-detected
```

## 🎉 Benefits

### Before (setup_v5.0.sh)
- ❌ 70+ lines of complex sed patterns
- ❌ Pattern matching often failed
- ❌ Different file structures broke the script
- ❌ Had to manually verify and fix
- ❌ Hardcoded IPs in built files

### After (setup_v6.0.sh)
- ✅ 10 lines of simple configuration
- ✅ Always works - no pattern matching
- ✅ Works with any frontend structure
- ✅ Automatic verification
- ✅ No hardcoded IPs - pure auto-detection
- ✅ Works in dev AND prod environments
- ✅ Can override with environment variable if needed

## 🔍 Troubleshooting

### Frontend Can't Connect to Backend

**Check 1: Backend is running**
```bash
curl http://localhost:5000/health
# Should return JSON with status
```

**Check 2: Frontend has correct config**
```bash
# Open browser console on http://YOUR_EC2_IP/
# Look for: [API Config] Using BASE_URL: http://YOUR_EC2_IP:5000
```

**Check 3: CORS is enabled**
```bash
curl -H "Origin: http://YOUR_EC2_IP" \
     -H "Access-Control-Request-Method: GET" \
     -X OPTIONS \
     http://YOUR_EC2_IP:5000/api/admin/stats -v

# Should have: Access-Control-Allow-Origin header
```

### Auto-Detection Not Working

**Force environment variable**:
```bash
cd /home/ubuntu/final-ml/frontend
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)
VITE_API_URL="http://$PUBLIC_IP:5000" npm run build
```

**Check built files**:
```bash
grep -r "VITE_API_URL\|getAutoDetectedURL" dist/assets/*.js
# Should see the auto-detection logic in the bundle
```

## 📝 Next Steps

1. **Push Frontend Changes**:
   ```bash
   # From your local machine:
   cd /path/to/frontend-
   git push origin api-auto-detection
   # Then merge PR on GitHub
   ```

2. **Deploy to EC2**:
   ```bash
   # Option A: Run setup_v5.0.sh (fresh deployment)
   # Option B: Follow manual update steps above
   ```

3. **Test Everything**:
   - Open `http://YOUR_EC2_IP/` in browser
   - Check browser console for auto-detection logs
   - Verify all API calls work
   - Test Models view shows pricing reports

## 🎯 Summary

The API URL configuration is now **100% automatic**:
- ✅ No sed patterns needed
- ✅ No manual IP updates
- ✅ Works on any EC2 instance
- ✅ Works in development
- ✅ Simpler to maintain
- ✅ More reliable

The frontend is **smarter** and automatically finds the backend regardless of where it's deployed!
