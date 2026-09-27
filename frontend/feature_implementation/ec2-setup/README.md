# EC2 Setup for Weaviate + Neo4j

One-command setup for Weaviate and Neo4j on Amazon Linux 2023.

## Prerequisites

1. **EC2 Instance**: t3a.xlarge (or larger)
   - 4 vCPU, 16GB RAM
   - Amazon Linux 2023 AMI

2. **EBS Volume**: 100GB attached
   - General Purpose SSD (gp3)
   - Can be attached during or after EC2 creation

3. **Security Group**: Open these ports
   | Port | Service | Access |
   |------|---------|--------|
   | 22 | SSH | Your IP |
   | 7474 | Neo4j Browser | Your IP / VPC |
   | 7687 | Neo4j Bolt | Your IP / VPC |
   | 8080 | Weaviate | Your IP / VPC |

## Quick Install

### Option 1: One-liner (Copy-paste)

SSH into your EC2 and run:

```bash
# Download and run setup
curl -sSL https://raw.githubusercontent.com/YOUR_REPO/ec2-setup/setup.sh | bash
```

### Option 2: Upload files manually

1. **Copy files to EC2:**
   ```bash
   scp -i your-key.pem -r ec2-setup/ ec2-user@YOUR_EC2_IP:~/
   ```

2. **SSH into EC2:**
   ```bash
   ssh -i your-key.pem ec2-user@YOUR_EC2_IP
   ```

3. **Run setup:**
   ```bash
   cd ~/ec2-setup
   chmod +x setup.sh
   ./setup.sh
   ```

4. **Log out and back in** (for docker group):
   ```bash
   exit
   ssh -i your-key.pem ec2-user@YOUR_EC2_IP
   ```

## What Gets Installed

- Docker
- Docker Compose
- Weaviate 1.24.1 (Vector Database)
- Neo4j 5.26 Community (Graph Database) with APOC plugin

## Default Credentials

| Service | Username | Password |
|---------|----------|----------|
| Neo4j | `neo4j` | `ocr@4567` |
| Weaviate | N/A | Anonymous access |

## Change Neo4j Password

Edit `/data/docker-compose.yml`:
```yaml
environment:
  - NEO4J_AUTH=neo4j/YOUR_NEW_PASSWORD
```

Then reset:
```bash
cd /data
docker-compose down
sudo rm -rf /data/neo4j/data/*
docker-compose up -d
```

## File Structure

```
ec2-setup/
├── README.md           # This file
├── docker-compose.yml  # Container configuration
└── setup.sh           # Automated setup script
```

## After Installation

### Service URLs
- **Weaviate**: `http://YOUR_EC2_IP:8080`
- **Neo4j Browser**: `http://YOUR_EC2_IP:7474`
- **Neo4j Bolt**: `bolt://YOUR_EC2_IP:7687`

### Management Commands

```bash
cd /data

# View status
docker ps

# View logs
docker-compose logs -f

# Restart
docker-compose restart

# Stop
docker-compose down

# Start
docker-compose up -d
```

### Health Checks

```bash
# Weaviate
curl http://localhost:8080/v1/meta

# Neo4j
curl http://localhost:7474
```

## Troubleshooting

### Docker permission denied
```bash
# Log out and back in, or run:
newgrp docker
```

### EBS volume not detected
```bash
# List all disks
lsblk

# Manually mount (replace nvme1n1 with your disk)
sudo mkfs -t xfs /dev/nvme1n1
sudo mount /dev/nvme1n1 /data
```

### Neo4j keeps restarting
```bash
# Check logs
docker-compose logs neo4j

# Common fix - permissions
sudo chown -R 1000:1000 /data/neo4j
```

### Reset everything
```bash
cd /data
docker-compose down
sudo rm -rf /data/neo4j/data/*
sudo rm -rf /data/weaviate/*
docker-compose up -d
```

## Production Recommendations

1. **Security**: Restrict Security Group to VPC CIDR only
2. **SSL**: Put behind ALB with HTTPS
3. **Backup**: Enable EBS snapshots
4. **Monitoring**: Add CloudWatch agent
5. **Auth**: Enable Weaviate authentication

## Environment Variables for Backend

Add to your `.env`:
```bash
WEAVIATE_URL=http://YOUR_EC2_IP:8080
NEO4J_URI=bolt://YOUR_EC2_IP:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=REDACTED
```
