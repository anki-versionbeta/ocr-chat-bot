# Weaviate & Neo4j Configuration

> **EC2 Instance:** 10.242.190.53 (t3a.xlarge)
> **Created:** January 28, 2026
> **Status:** ✅ RUNNING

---

## Connection Details

### Weaviate (Vector Database)

| Property | Value |
|----------|-------|
| **URL** | `http://10.242.190.53:8080` |
| **REST API** | `http://10.242.190.53:8080/v1` |
| **Authentication** | None (anonymous access enabled) |
| **Version** | 1.24.1 |

**Key Endpoints:**
- `GET /v1/meta` - Instance info
- `GET /v1/schema` - View schema
- `POST /v1/objects` - Create objects
- `POST /v1/graphql` - GraphQL queries

---

### Neo4j (Graph Database)

| Property | Value |
|----------|-------|
| **Browser URL** | `http://10.242.190.53:7474` |
| **Bolt URL** | `bolt://10.242.190.53:7687` |
| **Username** | `neo4j` |
| **Password** | `ocr@4567` |
| **Version** | 5.26-community |
| **Plugins** | APOC |

**What is Bolt vs Browser?**
- **Browser (port 7474)**: Web UI for running Cypher queries manually, visualizing graphs
- **Bolt (port 7687)**: Binary protocol for programmatic access from Python/Node.js drivers

---

## Environment Variables

Add these to your `.env` file:

```bash
# Weaviate Configuration
WEAVIATE_URL=http://10.242.190.53:8080
WEAVIATE_API_KEY=  REDACTED

# Neo4j Configuration
NEO4J_URI=bolt://10.242.190.53:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=REDACTED
```

---

## Python Backend Integration

### Install Dependencies

```bash
pip install weaviate-client neo4j "neo4j-graphrag[anthropic]"
```

### Weaviate Client

```python
import weaviate

# Connect to Weaviate
client = weaviate.Client(
    url="http://10.242.190.53:8080"
)

# Check connection
print(client.is_ready())  # Should return True

# Get schema
schema = client.schema.get()
print(schema)
```

### Neo4j Client

```python
from neo4j import GraphDatabase

# Connect to Neo4j
driver = GraphDatabase.driver(
    "bolt://10.242.190.53:7687",
    auth=("neo4j", "ocr@4567")
)

# Test connection
with driver.session() as session:
    result = session.run("RETURN 1 AS test")
    print(result.single()["test"])  # Should return 1

driver.close()
```

### Neo4j with Claude (neo4j-graphrag)

```python
from neo4j import GraphDatabase
from neo4j_graphrag.llm import AnthropicLLM
from neo4j_graphrag.retrievers import Text2CypherRetriever
import os

# Connect to Neo4j
driver = GraphDatabase.driver(
    "bolt://10.242.190.53:7687",
    auth=("neo4j", "ocr@4567")
)

# Initialize Claude
llm = AnthropicLLM(
    model_name="claude-3-5-sonnet-20241022",
    model_params={"temperature": 0, "max_tokens": 4000},
    api_key=REDACTED
)

# Create Text2Cypher retriever
retriever = Text2CypherRetriever(
    driver=driver,
    llm=llm,
    neo4j_schema=None  # Auto-fetch schema
)

# Query in natural language
results = retriever.search("Find all documents")
for item in results.items:
    print(item)

driver.close()
```

---

## Frontend/Node.js Integration

### Install Dependencies

```bash
npm install weaviate-ts-client neo4j-driver
```

### Weaviate Client (TypeScript)

```typescript
import weaviate from 'weaviate-ts-client';

const client = weaviate.client({
  scheme: 'http',
  host: '10.242.190.53:8080',
});

// Check connection
const meta = await client.misc.metaGetter().do();
console.log(meta);
```

### Neo4j Client (TypeScript)

```typescript
import neo4j from 'neo4j-driver';

const driver = neo4j.driver(
  'bolt://10.242.190.53:7687',
  neo4j.auth.basic('neo4j', 'ocr@4567')
);

const session = driver.session();
const result = await session.run('RETURN 1 AS test');
console.log(result.records[0].get('test'));

await session.close();
await driver.close();
```

---

## EC2 Management Commands

SSH into EC2:
```bash
ssh -i "ec2-ip-login.pem" ec2-user@10.242.190.53
```

Docker commands (run on EC2):
```bash
cd /data

# View running containers
docker ps

# View logs
docker-compose logs -f
docker-compose logs -f neo4j
docker-compose logs -f weaviate

# Restart services
docker-compose restart

# Stop services
docker-compose down

# Start services
docker-compose up -d

# Check disk usage
df -h /data
```

---

## Data Storage

| Service | Host Path | Container Path |
|---------|-----------|----------------|
| Weaviate | `/data/weaviate` | `/var/lib/weaviate` |
| Neo4j Data | `/data/neo4j/data` | `/data` |
| Neo4j Logs | `/data/neo4j/logs` | `/logs` |
| Neo4j Plugins | `/data/neo4j/plugins` | `/plugins` |

All data persists on 100GB EBS volume mounted at `/data`.

---

## Security Notes

**Current Setup (Development):**
- Weaviate: Anonymous access enabled
- Neo4j: Password authentication only
- Ports open: 7474, 7687, 8080

**For Production:**
1. Configure AWS Security Groups to restrict access
2. Enable Weaviate authentication
3. Use SSL/TLS for connections
4. Consider VPC peering for internal access only

---

## Health Check URLs

```bash
# Weaviate ready check
curl http://10.242.190.53:8080/v1/.well-known/ready

# Weaviate meta info
curl http://10.242.190.53:8080/v1/meta

# Neo4j info
curl http://10.242.190.53:7474
```

---

## Troubleshooting

### Container not starting
```bash
docker-compose logs neo4j
docker-compose logs weaviate
```

### Permission errors
```bash
sudo chown -R 1000:1000 /data/neo4j
sudo chown -R 1000:1000 /data/weaviate
```

### Reset Neo4j password
```bash
cd /data
docker-compose down
sudo rm -rf /data/neo4j/data/*
# Edit docker-compose.yml with new password
docker-compose up -d
```

### Check disk space
```bash
df -h /data
du -sh /data/*
```

---

*Document Version: 1.0*
*Last Updated: January 28, 2026*
