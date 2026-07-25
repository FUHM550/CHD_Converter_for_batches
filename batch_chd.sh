#!/usr/bin/env bash

# Multi-threaded batch script to convert CUE/ISO/GDI files to CHD using chdman & GNU Parallel

echo "Starting batch CHD conversion..."

# Find CUE, ISO, and GDI files, excluding track files like "(Track 2).cue"
find . -type f \( -iname "*.cue" -o -iname "*.iso" -o -iname "*.gdi" \) ! -iname "* (Track *)*" | \
parallel --progress --jobs 100% '
    file="{}"
    dir=$(dirname "$file")
    filename=$(basename "$file")
    basename="${filename%.*}"
    chd_out="$dir/$basename.chd"

    if [ -f "$chd_out" ]; then
        echo "Skipping (CHD already exists): $chd_out"
    else
        echo "Converting: $file"
        # Determine whether to use createcd or createdvd based on extension
        ext="${filename##*.}"
        ext_lc=$(echo "$ext" | tr "[:upper:]" "[:lower:]")

        if [ "$ext_lc" = "iso" ]; then
            chdman createdvd -i "$file" -o "$chd_out" --force
        else
            chdman createcd -i "$file" -o "$chd_out" --force
        fi
    fi
'

echo "Batch conversion complete!"
