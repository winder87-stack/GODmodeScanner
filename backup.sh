#!/bin/bash
# GODMODESCANNER Backup Script

BACKUP_DIR="$HOME/godmodescanner/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PROJECT_DIR="$HOME/godmodescanner/projects/godmodescanner"

mkdir -p "$BACKUP_DIR"

# Backup project memory and knowledge
tar -czf "$BACKUP_DIR/godmodescanner_${TIMESTAMP}.tar.gz" \
    -C "$PROJECT_DIR" .a0proj/memory .a0proj/knowledge config

# Keep only last 48 backups
cd "$BACKUP_DIR"
ls -t godmodescanner_*.tar.gz | tail -n +49 | xargs -r rm

echo "Backup complete: godmodescanner_${TIMESTAMP}.tar.gz"
