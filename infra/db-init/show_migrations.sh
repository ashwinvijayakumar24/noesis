#!/bin/bash

echo "=========================================="
echo "SUPABASE DATABASE MIGRATION SQL"
echo "=========================================="
echo ""
echo "Go to: https://app.supabase.com/project/ufnaadgdrraqnatvgarq/sql"
echo "Then copy and paste the SQL below:"
echo ""
echo "=========================================="
echo ""

for file in *.sql; do
    if [ -f "$file" ]; then
        echo ""
        echo "-- =========================================="
        echo "-- FILE: $file"
        echo "-- =========================================="
        echo ""
        cat "$file"
        echo ""
    fi
done

echo ""
echo "=========================================="
echo "After running this SQL, Step 3.4 will be complete!"
echo "=========================================="
