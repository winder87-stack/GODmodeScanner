#!/bin/bash
# GODMODESCANNER Directory Structure Diagnostic
# Run this on your HOST machine (not inside Docker)
# Usage: bash diagnose_structure.sh

echo "========================================"
echo "GODMODESCANNER DIRECTORY DIAGNOSTIC"
echo "========================================"
echo ""

BASE="/home/ink/godmodescanner"

# 1. Find all godmodescanner directories
echo "[1] NESTED DIRECTORY DETECTION"
echo "------------------------------"
find "$BASE" -type d -name "godmodescanner" 2>/dev/null
echo ""

# 2. Size at each level
echo "[2] DISK USAGE BY LEVEL"
echo "------------------------------"
echo -n "Level 1 ($BASE): "
du -sh "$BASE" 2>/dev/null | cut -f1
echo -n "Level 2 ($BASE/projects/godmodescanner): "
du -sh "$BASE/projects/godmodescanner" 2>/dev/null | cut -f1 || echo "N/A"
echo -n "Level 3 ($BASE/projects/godmodescanner/projects/godmodescanner): "
du -sh "$BASE/projects/godmodescanner/projects/godmodescanner" 2>/dev/null | cut -f1 || echo "N/A"
echo ""

# 3. Git repository locations
echo "[3] GIT REPOSITORY ROOTS"
echo "------------------------------"
find "$BASE" -name ".git" -type d 2>/dev/null
echo ""

# 4. Environment files
echo "[4] ENVIRONMENT FILES (.env)"
echo "------------------------------"
find "$BASE" -name ".env*" -type f 2>/dev/null | while read f; do
    echo "$f ($(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null) bytes)"
done
echo ""

# 5. Python file counts
echo "[5] PYTHON FILE COUNTS"
echo "------------------------------"
echo -n "Level 1 (excluding nested): "
find "$BASE" -maxdepth 5 -path "$BASE/projects" -prune -o -name "*.py" -type f -print 2>/dev/null | wc -l
echo -n "Level 2 (projects/godmodescanner): "
find "$BASE/projects/godmodescanner" -name "*.py" -type f 2>/dev/null | wc -l
echo ""

# 6. Recently modified files (last 7 days)
echo "[6] RECENTLY MODIFIED PYTHON FILES (last 7 days)"
echo "------------------------------"
find "$BASE" -name "*.py" -type f -mtime -7 2>/dev/null | head -20
echo ""

# 7. Key directories check
echo "[7] KEY DIRECTORY PRESENCE"
echo "------------------------------"
for dir in agents utils config scripts tests docs docker data; do
    echo -n "$dir: "
    if [ -d "$BASE/$dir" ]; then
        echo "EXISTS at Level 1"
    fi
    if [ -d "$BASE/projects/godmodescanner/$dir" ]; then
        echo "  -> ALSO EXISTS at Level 2 (DUPLICATE!)"
    fi
done
echo ""

# Summary
echo "========================================"
echo "SUMMARY & RECOMMENDATIONS"
echo "========================================"
GIT_ROOT=$(find "$BASE" -name ".git" -type d 2>/dev/null | head -1 | xargs dirname 2>/dev/null)
echo "Git Root: $GIT_ROOT"
echo ""
echo "If you see duplicates at Level 2, your active code is likely at:"
echo "  $BASE/projects/godmodescanner/"
echo ""
echo "To flatten (BACKUP FIRST!):"
echo "  1. cp -r $BASE $BASE.backup"
echo "  2. Review which level has newest files"
echo "  3. Remove the redundant level"
