#!/bin/bash
#
# Weaviate + Neo4j Setup Script for Amazon Linux 2023
#
# Usage:
#   1. Copy this folder to EC2
#   2. Run: chmod +x setup.sh && ./setup.sh
#
# Requirements:
#   - Amazon Linux 2023 EC2 instance (t3a.xlarge recommended)
#   - 100GB EBS volume attached (will be auto-detected)
#   - Root or sudo access
#

set -e  # Exit on error

echo "========================================"
echo "  Weaviate + Neo4j Setup Script"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    print_warning "Running without root. Will use sudo for privileged commands."
    SUDO="sudo"
else
    SUDO=""
fi

# Step 1: Update system
echo ""
echo "Step 1: Updating system packages..."
$SUDO yum update -y
print_status "System updated"

# Step 2: Install Docker
echo ""
echo "Step 2: Installing Docker..."
if command -v docker &> /dev/null; then
    print_status "Docker already installed"
else
    $SUDO yum install -y docker
    $SUDO systemctl start docker
    $SUDO systemctl enable docker
    $SUDO usermod -aG docker $USER
    print_status "Docker installed"
fi

# Step 3: Install Docker Compose
echo ""
echo "Step 3: Installing Docker Compose..."
if command -v docker-compose &> /dev/null; then
    print_status "Docker Compose already installed"
else
    $SUDO curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    $SUDO chmod +x /usr/local/bin/docker-compose
    print_status "Docker Compose installed"
fi

# Step 4: Detect and mount EBS volume
echo ""
echo "Step 4: Setting up EBS volume..."

# Check if /data already exists and is mounted
if mountpoint -q /data 2>/dev/null; then
    print_status "/data is already mounted"
else
    # Find unmounted disk (excluding root)
    ROOT_DISK=$(lsblk -no PKNAME $(findmnt -n -o SOURCE /))
    EBS_DISK=$(lsblk -dpno NAME,SIZE | grep -v "$ROOT_DISK" | grep -v "loop" | head -1 | awk '{print $1}')

    if [ -z "$EBS_DISK" ]; then
        print_error "No additional EBS volume found! Please attach a 100GB EBS volume."
        exit 1
    fi

    print_status "Found EBS volume: $EBS_DISK"

    # Check if already formatted
    if ! blkid $EBS_DISK &> /dev/null; then
        echo "Formatting $EBS_DISK with XFS..."
        $SUDO mkfs -t xfs $EBS_DISK
    fi

    # Create mount point and mount
    $SUDO mkdir -p /data
    $SUDO mount $EBS_DISK /data

    # Add to fstab for persistence
    if ! grep -q "$EBS_DISK" /etc/fstab; then
        echo "$EBS_DISK /data xfs defaults,nofail 0 2" | $SUDO tee -a /etc/fstab
    fi

    print_status "EBS volume mounted at /data"
fi

# Step 5: Create directories
echo ""
echo "Step 5: Creating data directories..."
$SUDO mkdir -p /data/weaviate
$SUDO mkdir -p /data/neo4j/data
$SUDO mkdir -p /data/neo4j/logs
$SUDO mkdir -p /data/neo4j/plugins
$SUDO chown -R 1000:1000 /data
print_status "Directories created"

# Step 6: Copy docker-compose.yml
echo ""
echo "Step 6: Setting up docker-compose.yml..."
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ -f "$SCRIPT_DIR/docker-compose.yml" ]; then
    cp "$SCRIPT_DIR/docker-compose.yml" /data/docker-compose.yml
    print_status "docker-compose.yml copied to /data/"
else
    print_error "docker-compose.yml not found in script directory!"
    exit 1
fi

# Step 7: Start services
echo ""
echo "Step 7: Starting Weaviate and Neo4j..."
cd /data

# Need to use newgrp or re-login for docker group
if groups | grep -q docker; then
    docker-compose up -d
else
    $SUDO docker-compose up -d
fi

print_status "Services starting..."

# Step 8: Wait for services to be ready
echo ""
echo "Step 8: Waiting for services to be ready..."
sleep 15

# Check Weaviate
echo "Checking Weaviate..."
for i in {1..10}; do
    if curl -s http://localhost:8080/v1/meta > /dev/null 2>&1; then
        print_status "Weaviate is ready"
        break
    fi
    if [ $i -eq 10 ]; then
        print_warning "Weaviate may still be starting..."
    fi
    sleep 3
done

# Check Neo4j
echo "Checking Neo4j..."
for i in {1..10}; do
    if curl -s http://localhost:7474 > /dev/null 2>&1; then
        print_status "Neo4j is ready"
        break
    fi
    if [ $i -eq 10 ]; then
        print_warning "Neo4j may still be starting..."
    fi
    sleep 3
done

# Final status
echo ""
echo "========================================"
echo "  Setup Complete!"
echo "========================================"
echo ""

# Get EC2 public/private IP
PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4 2>/dev/null || hostname -I | awk '{print $1}')

echo "Service URLs:"
echo "  Weaviate:      http://$PRIVATE_IP:8080"
echo "  Neo4j Browser: http://$PRIVATE_IP:7474"
echo "  Neo4j Bolt:    bolt://$PRIVATE_IP:7687"
echo ""
echo "Neo4j Credentials:"
echo "  Username: neo4j"
echo "  Password: ocr@4567"
echo ""
echo "Useful commands:"
echo "  cd /data && docker-compose logs -f    # View logs"
echo "  cd /data && docker-compose restart    # Restart services"
echo "  cd /data && docker-compose down       # Stop services"
echo "  cd /data && docker-compose up -d      # Start services"
echo ""

# Reminder about docker group
if ! groups | grep -q docker; then
    print_warning "Please log out and log back in to use docker without sudo"
fi
