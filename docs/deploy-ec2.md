# Deploying BatchGate on AWS EC2

One instance runs everything with docker compose: `db` (PostgreSQL), `redis`, `api`, `worker`
and `frontend` (Caddy). Only the frontend is reachable from outside, on ports 80 and 443. It
serves the web app and forwards `/api` to the API.

## 1. Launch the instance

In the EC2 console, **Launch instance**:

- **Region:** one where the Claude API is available. Mumbai (`ap-south-1`) is close to
  Bangalore.
- **AMI:** Ubuntu Server 24.04 LTS (x86_64).
- **Instance type:** `t3.medium` (2 vCPU, 4 GB). The frontend build needs the memory. A
  `t3.small` works if you add swap (step 2).
- **Key pair:** create or pick one, to SSH in.
- **Storage:** 20 GB gp3.
- **Security group:** allow inbound
  - SSH (22) from **My IP** only
  - HTTP (80) from anywhere
  - HTTPS (443) from anywhere

Then give it a fixed address: **Elastic IPs → Allocate**, then **Associate** it with the
instance. The IP then survives a stop and start.

## 2. Install Docker

```bash
ssh -i batchgate.pem ubuntu@<elastic-ip>

curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit        # log back in so the group applies
ssh -i batchgate.pem ubuntu@<elastic-ip>
docker compose version

# Only on a t3.small: 2 GB of swap for the build
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile \
  && sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 3. Get the code and configure it

```bash
git clone https://github.com/<you>/batchgate.git
cd batchgate
cp .env.example .env
nano .env
```

| Setting | What to put |
|---|---|
| `BATCHGATE_DB_NAME`, `BATCHGATE_DB_USER` | `batchgate`, unless you want other names |
| `BATCHGATE_DB_PASSWORD` | A new password. PostgreSQL is created with it on the first start. |
| `BATCHGATE_SECRET_KEY` | `openssl rand -hex 32` |
| `ANTHROPIC_API_KEY` | Your key. Without it, COA values are typed in by hand and the copilot is off. |
| `DOMAIN` | Empty for plain HTTP on the IP, or a domain (below) |
| `BATCHGATE_DEMO_MODE` | `true` shows the one-click demo logins. Fine for the demo. |

Write a literal `$` in a value as `$$`.

## 4. Start it

```bash
docker compose up -d --build
docker compose ps
```

The first build takes a few minutes. When all five services show as running (`db`, `redis`
and `api` as *healthy*), open `http://<elastic-ip>`.

On its first start the API applies the migrations and adds the demo data, because the
database is empty. Later starts only apply new migrations, so your data is kept.

## 5. Optional: HTTPS with a domain

Add a DNS **A record** for a name you own (for example `batchgate.example.com`) pointing at the
Elastic IP. Set `DOMAIN=batchgate.example.com` in `.env`, then run:

```bash
docker compose up -d frontend
```

Caddy gets a Let's Encrypt certificate on its own and redirects HTTP to HTTPS. Ports 80 and 443
must be open for this.

## Day to day

```bash
docker compose logs -f api worker        # what the API and the COA reader are doing
docker compose logs -f frontend          # requests, certificates

# Update to the latest code (migrations run on start, data is kept)
git pull && docker compose up -d --build

# Back up the database
docker compose exec db pg_dump -U batchgate batchgate | gzip > batchgate-$(date +%F).sql.gz

# Restore a backup into an empty database
gunzip -c batchgate-2026-11-03.sql.gz | docker compose exec -T db psql -U batchgate batchgate

# Fresh demo data (deletes everything in the database)
docker compose exec api python -m app.seed --reset

# A psql shell
docker compose exec db psql -U batchgate batchgate
```

Uploaded COAs are kept in the `uploads` volume, which the API and the worker share.
`docker compose down` keeps all volumes. `docker compose down -v` deletes the database and the
uploads too.

## When something is wrong

| You see | Check |
|---|---|
| The page doesn't load | `docker compose ps`. Port 80 and 443 open in the security group? |
| `api` keeps restarting | `docker compose logs api`. It names the problem, such as a database that is behind its migrations, with the command to fix it. |
| COAs stay on "Waiting for the COA reader" | `docker compose logs worker`. Is the worker running? |
| COAs go straight to typing values in | `ANTHROPIC_API_KEY` is empty or wrong. Fix `.env`, then `docker compose up -d api worker`. |
| Changed `BATCHGATE_DB_PASSWORD` and the API can't log in | PostgreSQL keeps the password it was created with. Change it in the database too: `docker compose exec db psql -U batchgate -c "ALTER USER batchgate PASSWORD '...'"` |

## Cost

A `t3.medium` in Mumbai is about $0.045 an hour (about $33 a month running all the time).
**Stop** the instance from the console between demos. The Elastic IP and the disk are kept,
and an Elastic IP attached to a stopped instance costs a little per hour. **Terminate** it
when you are done.
