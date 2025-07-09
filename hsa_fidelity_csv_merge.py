#!/usr/bin/env python3

"""
hsa_fidelity_csv_merge.py

A script to merge Monarch Money HSA transaction CSVs with Fidelity HSA bank transaction CSVs.
It updates the Monarch Money CSV with missing or enhanced information from the Fidelity bank CSV,
enabling improved import and reconciliation back into Monarch Money.

This script is specifically customized for HSA account transactions exported from Fidelity.

Usage:
    python3 hsa_fidelity_csv_merge.py --monarch_csv monarch.csv --fidelity_csv fidelity.csv --output_csv output.csv

Maintainer:
    Charles Shi <schrht@gmail.com>

This script was created with Cursor using the GPT-4 model.

"""

import csv
import sys
import logging
import re
from datetime import datetime
import argparse

# Configure logger
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s', stream=sys.stdout)
logger = logging.getLogger(__name__)

def parse_fidelity_date(date_str):
    # Fidelity format: MM/DD/YYYY
    try:
        return datetime.strptime(date_str.strip(), '%m/%d/%Y').date()
    except Exception as e:
        logger.error(f"Could not parse Fidelity date: {date_str} ({e})")
        return None

def parse_monarch_date(date_str):
    # Monarch format: YYYY-MM-DD
    try:
        return datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
    except Exception as e:
        logger.error(f"Could not parse Monarch date: {date_str} ({e})")
        return None

def extract_symbol_from_original_statement(original_statement):
    # Extract symbol from patterns like:
    # 'DVFri Oct 04 12:00:00 UTC 202434.17FXAIX' -> 'FXAIX'
    # 'Iawed Oct 02 12:00:00 Utc 2024153.85fdrxx' -> 'FDRXX'
    if not original_statement:
        return ''
    
    # Look for any sequence of letters at the end
    match = re.search(r'[A-Za-z]{2,}$', original_statement.strip())
    if match:
        return match.group().upper()
    
    return ''

def parse_fidelity_row(row):
    logger.debug(f"parse_fidelity_row input row: {row}")
    # Skip rows that don't have the expected keys
    if 'Account' not in row or 'Run Date' not in row or 'Amount ($)' not in row:
        return None
    # Only consider HSA account rows
    if row['Account'] != 'Health Savings Account':
        return None
    # Normalize date and amount
    run_date = row['Run Date']
    amount = row['Amount ($)']
    symbol = row.get('Symbol', '').strip().upper()
    norm_date = parse_fidelity_date(run_date)
    result = {
        'date': run_date.strip(),
        'norm_date': norm_date,
        'amount': float(amount.strip()) if amount else 0.0,
        'symbol': symbol,
        'desc': row.get('Description', ''),
        'action': row.get('Action', ''),
        'type': row.get('Type', ''),
        'original': row
    }
    logger.debug(f"parse_fidelity_row result: {result}")
    return result

def parse_monarch_row(row):
    logger.debug(f"parse_monarch_row input row: {row}")
    # Monarch: Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags
    date = row['Date']
    amount = row['Amount']
    original_statement = row.get('Original Statement', '')
    symbol = extract_symbol_from_original_statement(original_statement)
    norm_date = parse_monarch_date(date)
    result = {
        'date': date.strip(),
        'norm_date': norm_date,
        'amount': float(amount.strip()) if amount else 0.0,
        'symbol': symbol,
        'merchant': row.get('Merchant'),
        'category': row.get('Category'),
        'original_statement': original_statement,
        'original': row
    }
    logger.debug(f"parse_monarch_row result: {result}")
    return result

def match_entries(monarch_rows, fidelity_rows):
    matches = []
    unmatched = []

    # Build a lookup for Fidelity by (normalized date, amount, symbol)
    fidelity_lookup = {}
    for f in fidelity_rows:
        key = (f['norm_date'], f['amount'], f['symbol'])
        logger.debug(f"Fidelity key: {key}")
        if key not in fidelity_lookup:
            fidelity_lookup[key] = []
        fidelity_lookup[key].append(f)

    logger.debug(f"Fidelity lookup: {fidelity_lookup}")

    # Try to match each Monarch row
    for m in monarch_rows:
        key = (m['norm_date'], m['amount'], m['symbol'])
        logger.debug(f"Monarch key: {key}")
        if key in fidelity_lookup and fidelity_lookup[key]:
            match = fidelity_lookup[key].pop(0)
            matches.append((m, match))
            logger.debug(
                f"Match found: Monarch entry (Date: {m['date']}, Amount: {m['amount']}, Symbol: {m['symbol']}) "
                f"<-> Fidelity entry (Date: {match['date']}, Amount: {match['amount']}, Symbol: {match['symbol']}, Description: {match['desc']})"
            )
        else:
            unmatched.append(m)
            logger.warning(f"No match found for Monarch entry (Date: {m['date']}, Amount: {m['amount']}, Symbol: {m['symbol']})")
    return matches, unmatched

def skip_blank_lines(f):
    # Skip blank lines at the start of the file
    while True:
        pos = f.tell()
        line = f.readline()
        if not line:
            break
        if line.strip():
            f.seek(pos)
            break
    return f

def main(): 
    parser = argparse.ArgumentParser(description="Merge Monarch and Fidelity CSVs for HSA reconciliation.")
    parser.add_argument("monarch_csv", help="Path to Monarch CSV file")
    parser.add_argument("fidelity_csv", help="Path to Fidelity CSV file")
    parser.add_argument("output_csv", help="Path to output CSV file")
    args = parser.parse_args()

    monarch_csv = args.monarch_csv
    fidelity_csv = args.fidelity_csv
    output_csv = args.output_csv

    # Read Fidelity (handle BOM automatically)
    with open(fidelity_csv, newline='', encoding='utf-8-sig') as f:
        f = skip_blank_lines(f)
        reader = csv.DictReader(f)
        fidelity_rows = [parse_fidelity_row(row) for row in reader]
        fidelity_rows = [r for r in fidelity_rows if r]

    # Read Monarch
    with open(monarch_csv, newline='') as f:
        f = skip_blank_lines(f)
        reader = csv.DictReader(f)
        monarch_rows = [parse_monarch_row(row) for row in reader]
        monarch_rows = [r for r in monarch_rows if r]

    # Match
    matches, unmatched = match_entries(monarch_rows, fidelity_rows)
    logger.info(f"Total Monarch entries: {len(monarch_rows)}")
    logger.info(f"Matched: {len(matches)}")
    logger.info(f"Unmatched: {len(unmatched)}")
    # TODO: Update Monarch file with Fidelity info and write output

if __name__ == "__main__":
    main()