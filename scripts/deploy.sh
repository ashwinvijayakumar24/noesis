#!/bin/bash
# ============================================
# Noesis Production Deployment Script
# ============================================
# Usage: ./deploy.sh [command]
# Commands: status, logs, update, backup, restart

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

COMPOSE_FILE="docker-compose.prod.yml"
PROJECT_DIR="$HOME/noesis"
INFRA_DIR="$PROJECT_DIR/infra"

# Check if running on EC2 instance
if [ ! -f "$INFRA_DIR/$COMPOSE_FILE" ]; then
    echo -e "${RED}Error: Must run on EC2 instance with Noesis deployed${NC}"
    exit 1
fi

cd "$INFRA_DIR"

# Function to show usage
usage() {
    echo "Noesis Production Deployment Helper"
    echo ""
    echo "Usage: ./deploy.sh [command]"
    echo ""
    echo "Commands:"
    echo "  status    - Show service status"
    echo "  logs      - Follow service logs"
    echo "  update    - Pull latest code and rebuild"
    echo "  backup    - Backup database"
    echo "  restart   - Restart all services"
    echo "  monitor   - Show resource usage"
    echo "  help      - Show this help"
    echo ""
}

# Function to show status
show_status() {
    echo -e "${GREEN}=== Service Status ===${NC}"
    docker compose -f "$COMPOSE_FILE" ps
    echo ""
    echo -e "${GREEN}=== Health Checks ===${NC}"
    for service in db redis grobid backend; do
        health=$(docker inspect --format='{{.State.Health.Status}}' noesis-${service}-prod 2>/dev/null || echo "no healthcheck")
        if [ "$health" = "healthy" ]; then
            echo -e "✅ $service: ${GREEN}healthy${NC}"
        elif [ "$health" = "no healthcheck" ]; then
            status=$(docker inspect --format='{{.State.Status}}' noesis-${service}-prod 2>/dev/null || echo "unknown")
            echo -e "⚠️  $service: ${YELLOW}$status (no healthcheck)${NC}"
        else
            echo -e "❌ $service: ${RED}$health${NC}"
        fi
    done
}

# Function to show logs
show_logs() {
    echo -e "${GREEN}=== Following logs (Ctrl+C to exit) ===${NC}"
    docker compose -f "$COMPOSE_FILE" logs -f --tail=50
}

# Function to update deployment
update_deployment() {
    echo -e "${YELLOW}=== Updating Noesis ===${NC}"

    # Pull latest code
    echo "Pulling latest code..."
    cd "$PROJECT_DIR"
    git pull origin main

    # Rebuild and restart
    echo "Rebuilding backend..."
    cd "$INFRA_DIR"
    docker compose -f "$COMPOSE_FILE" build backend

    echo "Restarting services..."
    docker compose -f "$COMPOSE_FILE" up -d

    echo -e "${GREEN}✅ Update complete!${NC}"

    # Show status
    sleep 5
    show_status
}

# Function to backup database
backup_database() {
    echo -e "${YELLOW}=== Backing up database ===${NC}"

    BACKUP_DIR="$HOME/backups"
    mkdir -p "$BACKUP_DIR"

    DATE=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/db_$DATE.sql"

    echo "Creating backup: $BACKUP_FILE"
    docker compose -f "$COMPOSE_FILE" exec -T db \
        pg_dump -U noesis_prod noesis_prod > "$BACKUP_FILE"

    echo "Compressing..."
    gzip "$BACKUP_FILE"

    # Keep only last 7 backups
    ls -t "$BACKUP_DIR"/db_*.sql.gz | tail -n +8 | xargs -r rm

    echo -e "${GREEN}✅ Backup complete: ${BACKUP_FILE}.gz${NC}"
    echo "Total backups: $(ls -1 "$BACKUP_DIR"/db_*.sql.gz | wc -l)"
}

# Function to restart services
restart_services() {
    echo -e "${YELLOW}=== Restarting services ===${NC}"
    docker compose -f "$COMPOSE_FILE" restart
    echo -e "${GREEN}✅ Services restarted${NC}"

    sleep 5
    show_status
}

# Function to monitor resources
monitor_resources() {
    echo -e "${GREEN}=== System Resources ===${NC}"
    free -h
    echo ""

    echo -e "${GREEN}=== Disk Usage ===${NC}"
    df -h | grep -E '(Filesystem|/dev/root|tmpfs)'
    echo ""

    echo -e "${GREEN}=== Docker Stats ===${NC}"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
    echo ""

    echo -e "${GREEN}=== Docker Volumes ===${NC}"
    docker volume ls --format "table {{.Name}}\t{{.Driver}}"
}

# Main script
case "$1" in
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    update)
        update_deployment
        ;;
    backup)
        backup_database
        ;;
    restart)
        restart_services
        ;;
    monitor)
        monitor_resources
        ;;
    help|"")
        usage
        ;;
    *)
        echo -e "${RED}Error: Unknown command '$1'${NC}"
        usage
        exit 1
        ;;
esac
