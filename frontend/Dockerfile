FROM node:20-slim

WORKDIR /app

# Copy package files first for cache optimization
COPY package*.json ./

# Clean install
RUN npm ci

# Copy source code
COPY . .

# Expose port
EXPOSE 3000

# Run development server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
