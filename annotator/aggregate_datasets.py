#!/usr/bin/env python3
import os
import csv
import shutil
import sys

def aggregate():
    # 1. Define paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    default_annotators_dir = os.path.join(script_dir, "all_annotators_dataset")
    user_annotators_dir = input(f"Enter annotator directory [{default_annotators_dir}]: ").strip()
    annotators_dir = user_annotators_dir if user_annotators_dir else default_annotators_dir

    default_output_csv_path = os.path.join(script_dir, "dataset.csv")
    user_output_csv_path = input(f"Enter output CSV path [{default_output_csv_path}]: ").strip()
    output_csv_path = user_output_csv_path if user_output_csv_path else default_output_csv_path

    default_output_images_dir = os.path.join(script_dir, "images")
    user_output_images_dir = input(f"Enter output images directory [{default_output_images_dir}]: ").strip()
    output_images_dir = user_output_images_dir if user_output_images_dir else default_output_images_dir

    print(f"\nRoot/Script Directory: {script_dir}")
    print(f"Annotators Directory: {annotators_dir}")
    print(f"Output CSV Path: {output_csv_path}")
    print(f"Output Images Directory: {output_images_dir}")

    if not os.path.exists(annotators_dir):
        print(f"Error: Annotators directory not found at: {annotators_dir}", file=sys.stderr)
        sys.exit(1)

    # Create root images directory if it doesn't exist
    os.makedirs(output_images_dir, exist_ok=True)

    # 2. Find annotator directories
    annotators = []
    for entry in os.listdir(annotators_dir):
        entry_path = os.path.join(annotators_dir, entry)
        if os.path.isdir(entry_path) and not entry.startswith('.'):
            annotators.append(entry)

    print(f"Found {len(annotators)} annotators: {', '.join(annotators)}")

    # 3. Read and aggregate CSV data and copy images
    all_rows = []
    fieldnames = [
        "id", "heading", "text", "image_path", "label", 
        "multi_category", "source", "source_category", 
        "category", "annotator", "annotation_confidence", "timestamp"
    ]

    total_images_copied = 0

    for annotator in sorted(annotators):
        annotator_dir = os.path.join(annotators_dir, annotator)
        csv_path = os.path.join(annotator_dir, "dataset.csv")
        images_dir = os.path.join(annotator_dir, "images")

        print(f"\nProcessing annotator: '{annotator}'")

        # Copy all images from annotator's images folder to root images folder
        if os.path.exists(images_dir) and os.path.isdir(images_dir):
            copied_count = 0
            for img_file in os.listdir(images_dir):
                if img_file.startswith('.'):
                    continue
                src_img_path = os.path.join(images_dir, img_file)
                dst_img_path = os.path.join(output_images_dir, img_file)
                if os.path.isfile(src_img_path):
                    shutil.copy2(src_img_path, dst_img_path)
                    copied_count += 1
                    total_images_copied += 1
            print(f"  Copied {copied_count} images from: {images_dir}")
        else:
            print(f"  Warning: Images directory not found at {images_dir}")

        # Read CSV rows
        if os.path.exists(csv_path) and os.path.isfile(csv_path):
            with open(csv_path, mode='r', encoding='utf-8', errors='replace') as f:
                reader = csv.DictReader(f)
                
                # Check headers
                reader_fieldnames = reader.fieldnames if reader.fieldnames else []
                # Check if there are any missing columns in reader compared to our list
                for fn in fieldnames:
                    if fn not in reader_fieldnames:
                        print(f"  Warning: Column '{fn}' not found in {csv_path}. It will be added as empty.")

                count = 0
                for row in reader:
                    # Clean up keys and ensure all required fields are present
                    clean_row = {}
                    for field in fieldnames:
                        val = row.get(field)
                        clean_row[field] = val.strip() if val is not None else ""
                    
                    all_rows.append(clean_row)
                    count += 1
                print(f"  Read {count} rows from {csv_path}")
        else:
            print(f"  Warning: CSV not found at {csv_path}")

    # 4. Write aggregated CSV file
    print(f"\nWriting {len(all_rows)} aggregated rows to {output_csv_path}...")
    with open(output_csv_path, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row)

    print("\nAggregation complete!")
    print(f"Total rows aggregated: {len(all_rows)}")
    print(f"Total image files copied: {total_images_copied}")

if __name__ == "__main__":
    aggregate()
