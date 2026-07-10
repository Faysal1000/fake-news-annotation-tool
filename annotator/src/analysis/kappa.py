"""
Cohen's and Fleiss' Kappa agreement metrics.

Computes inter-rater reliability scores from relabeling CSV files.
"""

import csv
from pathlib import Path
from itertools import combinations
from constants import CSV_COLUMNS

__all__ = ["compute_cohen_kappa", "compute_fleiss_kappa", "calculate_kappa", "interpret_kappa"]

def compute_cohen_kappa(ratings_a, ratings_b, categories):
    """
    Compute Cohen's Kappa for two annotators.
    ratings_a, ratings_b: lists of category labels (same length).
    categories: the set of all possible category labels.
    Returns kappa value (float).
    """
    n = len(ratings_a)
    if n == 0:
        return 0.0

    cats = sorted(categories)
    cat_index = {c: i for i, c in enumerate(cats)}
    k = len(cats)

    # Build confusion matrix
    matrix = [[0] * k for _ in range(k)]
    for a, b in zip(ratings_a, ratings_b):
        if a in cat_index and b in cat_index:
            matrix[cat_index[a]][cat_index[b]] += 1

    # Observed agreement
    p_o = sum(matrix[i][i] for i in range(k)) / n

    # Expected agreement by chance
    p_e = 0.0
    for i in range(k):
        row_sum = sum(matrix[i][j] for j in range(k))
        col_sum = sum(matrix[j][i] for j in range(k))
        p_e += (row_sum * col_sum)
    p_e /= (n * n)

    if p_e == 1.0:
        return 1.0
    return (p_o - p_e) / (1.0 - p_e)

def compute_fleiss_kappa(ratings_table, categories):
    """
    Compute Fleiss' Kappa for multiple annotators.
    ratings_table: list of dicts, each dict maps category -> count of raters who chose it.
    categories: list of all category labels.
    Returns kappa value (float).
    """
    n_subjects = len(ratings_table)
    if n_subjects == 0:
        return 0.0

    cats = sorted(categories)
    k = len(cats)

    # Number of raters per subject (should be the same for all)
    n_raters = sum(ratings_table[0].get(c, 0) for c in cats)
    if n_raters <= 1:
        return 0.0

    # Calculate P_i (agreement for each subject)
    P_i_list = []
    for subject in ratings_table:
        sum_sq = sum(subject.get(c, 0) ** 2 for c in cats)
        P_i = (sum_sq - n_raters) / (n_raters * (n_raters - 1))
        P_i_list.append(P_i)

    P_bar = sum(P_i_list) / n_subjects

    # Calculate p_j (proportion of all assignments to each category)
    total_assignments = n_subjects * n_raters
    p_j = {}
    for c in cats:
        p_j[c] = sum(subject.get(c, 0) for subject in ratings_table) / total_assignments

    P_e_bar = sum(pj ** 2 for pj in p_j.values())

    if P_e_bar == 1.0:
        return 1.0
    return (P_bar - P_e_bar) / (1.0 - P_e_bar)

def calculate_kappa(kappa_csv_path, mode="cohen"):
    """
    Calculate inter-rater agreement from the relabeling_for_kappa.csv file.
    Computes agreement for both 'label' and 'multi_category' columns.

    mode: 'cohen' for Cohen's Kappa (exactly 2 annotators) or
          'fleiss' for Fleiss' Kappa (2+ annotators).

    Returns a formatted results string, or raises an error if data is incomplete.
    """
    csv_path = Path(kappa_csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Kappa CSV not found: {kappa_csv_path}")

    # Read all rows and discover annotator columns
    rows = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for row in reader:
            rows.append(row)

    if not rows:
        raise ValueError("No records found in the kappa CSV.")

    # Find annotator names from column pattern: {name}_label
    annotator_names = []
    for h in headers:
        if h.endswith("_label") and h != "label":
            name = h[:-6]  # strip "_label"
            annotator_names.append(name)

    if not annotator_names:
        raise ValueError(
            "No annotator rating columns found.\n\n"
            "Annotators need to complete Re-label mode first.\n"
            "Expected columns like: AnnotatorName_label"
        )

    if mode == "cohen" and len(annotator_names) < 2:
        raise ValueError(
            f"Cohen's Kappa requires at least 2 annotators, "
            f"but found {len(annotator_names)}."
        )

    if mode == "fleiss" and len(annotator_names) < 2:
        raise ValueError(
            f"Fleiss' Kappa requires at least 2 annotators, "
            f"but found {len(annotator_names)}."
        )

    # Check for missing ratings and collect per-annotator missing info
    missing_info = []
    for name in annotator_names:
        label_col = f"{name}_label"
        multi_col = f"{name}_multi_category"
        missing_label_rows = []
        missing_multi_rows = []
        for i, row in enumerate(rows):
            label_val = (row.get(label_col) or "").strip()
            multi_val = (row.get(multi_col) or "").strip()
            if not label_val:
                missing_label_rows.append(i + 1)
            if not multi_val:
                missing_multi_rows.append(i + 1)
        
        if missing_label_rows:
            if len(missing_label_rows) <= 5:
                row_list = ", ".join(str(r) for r in missing_label_rows)
            else:
                row_list = ", ".join(str(r) for r in missing_label_rows[:5]) + f"... ({len(missing_label_rows)} total)"
            missing_info.append(f"  {name}: missing {len(missing_label_rows)} labels (rows: {row_list})")
            
        if missing_multi_rows:
            if len(missing_multi_rows) <= 5:
                row_list = ", ".join(str(r) for r in missing_multi_rows)
            else:
                row_list = ", ".join(str(r) for r in missing_multi_rows[:5]) + f"... ({len(missing_multi_rows)} total)"
            missing_info.append(f"  {name}: missing {len(missing_multi_rows)} multi-categories (rows: {row_list})")

    if missing_info:
        raise ValueError(
            "Some annotators have incomplete ratings.\n"
            "All records must be labeled before calculating Kappa.\n\n"
            + "\n".join(missing_info)
        )

    # Collect all unique categories for label and multi_category
    label_cats = set()
    multi_cats = set()
    for name in annotator_names:
        for row in rows:
            lv = (row.get(f"{name}_label") or "").strip()
            mv = (row.get(f"{name}_multi_category") or "").strip()
            if lv:
                label_cats.add(lv)
            if mv:
                multi_cats.add(mv)

    results = []
    results.append(f"Inter-Rater Reliability Results")
    results.append(f"Mode: {'Cohen (pairwise)' if mode == 'cohen' else 'Fleiss'}'s Kappa")
    results.append(f"Annotators ({len(annotator_names)}): {', '.join(annotator_names)}")
    results.append(f"Records: {len(rows)}")
    results.append("")

    if mode == "cohen":
        # Cohen's Kappa: pairwise for every pair of annotators
        pairs = list(combinations(annotator_names, 2))

        results.append(f"--- Label (Fake/Real) ---")
        label_kappas = []
        for a_name, b_name in pairs:
            a_labels = [(row.get(f"{a_name}_label") or "").strip() for row in rows]
            b_labels = [(row.get(f"{b_name}_label") or "").strip() for row in rows]
            k = compute_cohen_kappa(a_labels, b_labels, label_cats)
            label_kappas.append(k)
            results.append(f"  {a_name} vs {b_name}: {k:.4f} ({interpret_kappa(k)})")

        if len(pairs) > 1:
            avg_label = sum(label_kappas) / len(label_kappas)
            results.append(f"  Average: {avg_label:.4f} ({interpret_kappa(avg_label)})")

        results.append("")
        results.append(f"--- Multi-Category ---")
        multi_kappas = []
        for a_name, b_name in pairs:
            a_multi = [(row.get(f"{a_name}_multi_category") or "").strip() for row in rows]
            b_multi = [(row.get(f"{b_name}_multi_category") or "").strip() for row in rows]
            k = compute_cohen_kappa(a_multi, b_multi, multi_cats)
            multi_kappas.append(k)
            results.append(f"  {a_name} vs {b_name}: {k:.4f} ({interpret_kappa(k)})")

        if len(pairs) > 1:
            avg_multi = sum(multi_kappas) / len(multi_kappas)
            results.append(f"  Average: {avg_multi:.4f} ({interpret_kappa(avg_multi)})")

    else:
        # Fleiss' Kappa: 2+ annotators
        # Build ratings table for labels
        label_table = []
        for row in rows:
            counts = {c: 0 for c in label_cats}
            for name in annotator_names:
                val = (row.get(f"{name}_label") or "").strip()
                if val in counts:
                    counts[val] += 1
            label_table.append(counts)
        k_label = compute_fleiss_kappa(label_table, label_cats)

        # Build ratings table for multi-category
        multi_table = []
        for row in rows:
            counts = {c: 0 for c in multi_cats}
            for name in annotator_names:
                val = (row.get(f"{name}_multi_category") or "").strip()
                if val in counts:
                    counts[val] += 1
            multi_table.append(counts)
        k_multi = compute_fleiss_kappa(multi_table, multi_cats)

        results.append(f"--- Label (Fake/Real) ---")
        results.append(f"  Fleiss' Kappa: {k_label:.4f}")
        results.append(f"  Interpretation: {interpret_kappa(k_label)}")
        results.append("")
        results.append(f"--- Multi-Category ---")
        results.append(f"  Fleiss' Kappa: {k_multi:.4f}")
        results.append(f"  Interpretation: {interpret_kappa(k_multi)}")

    return "\n".join(results)

def interpret_kappa(k):
    """Return a human-readable interpretation of a kappa score (Landis & Koch scale)."""
    if k < 0:
        return "Poor (less than chance)"
    elif k < 0.21:
        return "Slight agreement"
    elif k < 0.41:
        return "Fair agreement"
    elif k < 0.61:
        return "Moderate agreement"
    elif k < 0.81:
        return "Substantial agreement"
    else:
        return "Almost perfect agreement"
