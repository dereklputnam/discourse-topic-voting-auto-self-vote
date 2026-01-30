#!/usr/bin/env python3
"""
Backfill Self-Votes via Discourse API

This script casts votes for topic authors who haven't voted on their own topics.
It uses the Discourse API to impersonate users and cast votes on their behalf.

Requirements:
- Python 3.7+
- requests library (pip install requests)
- An admin API key with impersonation permissions

Usage:
1. Update the configuration section below
2. Prepare a CSV file with topic_id and username columns
3. Run: python backfill_votes_api.py

CSV Format:
    topic_id,username
    12345,john_doe
    12346,jane_smith
"""

import csv
import time
import requests
from datetime import datetime

#==============================================================================
# CONFIGURATION
#==============================================================================

# Discourse instance URL (no trailing slash)
DISCOURSE_URL = 'https://comstg.netwrix.com/community'

# Admin API key (must have impersonation permissions)
API_KEY = 'YOUR_API_KEY_HERE'

# Admin username that owns the API key
API_USERNAME = 'system'

# Path to CSV file with topic_id and username columns
CSV_FILE = 'topics_to_vote.csv'

# Dry run mode - set to False to actually cast votes
DRY_RUN = True

# Delay between API calls (seconds) to avoid rate limiting
DELAY_BETWEEN_REQUESTS = 0.5

#==============================================================================
# SCRIPT
#==============================================================================

def cast_vote(topic_id: int, username: str) -> dict:
    """
    Cast a vote on a topic as a specific user.

    Args:
        topic_id: The ID of the topic to vote on
        username: The username to impersonate when voting

    Returns:
        dict with 'success' boolean and 'message' string
    """
    url = f"{DISCOURSE_URL}/voting/vote"

    headers = {
        'Api-Key': API_KEY,
        'Api-Username': username,  # Impersonate the user
        'Content-Type': 'application/json'
    }

    data = {
        'topic_id': topic_id
    }

    try:
        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 200:
            return {'success': True, 'message': 'Vote cast successfully'}
        elif response.status_code == 422:
            # Usually means already voted or voting not enabled
            return {'success': False, 'message': 'Already voted or voting not enabled'}
        elif response.status_code == 403:
            return {'success': False, 'message': 'Permission denied - check API key permissions'}
        elif response.status_code == 404:
            return {'success': False, 'message': 'Topic not found or voting not enabled on category'}
        else:
            return {'success': False, 'message': f'HTTP {response.status_code}: {response.text[:200]}'}

    except requests.RequestException as e:
        return {'success': False, 'message': f'Request error: {str(e)}'}


def main():
    print("\n" + "=" * 60)
    print("Backfill Self-Votes via API")
    print("=" * 60)
    print(f"Mode: {'DRY RUN (no changes)' if DRY_RUN else 'LIVE (votes will be cast)'}")
    print(f"Target: {DISCOURSE_URL}")
    print(f"CSV File: {CSV_FILE}")
    print("=" * 60 + "\n")

    # Read CSV file
    try:
        with open(CSV_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        print(f"ERROR: CSV file not found: {CSV_FILE}")
        print("\nCreate a CSV file with the following format:")
        print("topic_id,username")
        print("12345,john_doe")
        print("12346,jane_smith")
        return
    except Exception as e:
        print(f"ERROR: Failed to read CSV file: {e}")
        return

    if not rows:
        print("ERROR: CSV file is empty")
        return

    # Validate CSV columns
    required_columns = {'topic_id', 'username'}
    if not required_columns.issubset(rows[0].keys()):
        print(f"ERROR: CSV must have columns: {required_columns}")
        print(f"Found columns: {set(rows[0].keys())}")
        return

    print(f"Found {len(rows)} topics to process\n")

    # Process each row
    success_count = 0
    skip_count = 0
    error_count = 0

    for i, row in enumerate(rows, 1):
        topic_id = row['topic_id'].strip()
        username = row['username'].strip()

        print(f"[{i}/{len(rows)}] Topic #{topic_id} by @{username}", end=" ")

        if DRY_RUN:
            print("-> would vote")
            success_count += 1
        else:
            result = cast_vote(int(topic_id), username)

            if result['success']:
                print("-> voted!")
                success_count += 1
            elif 'Already voted' in result['message']:
                print("-> already voted (skipped)")
                skip_count += 1
            else:
                print(f"-> ERROR: {result['message']}")
                error_count += 1

            # Rate limiting
            if i < len(rows):
                time.sleep(DELAY_BETWEEN_REQUESTS)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total topics: {len(rows)}")
    print(f"Votes {'to cast' if DRY_RUN else 'cast'}: {success_count}")
    print(f"Already voted (skipped): {skip_count}")
    print(f"Errors: {error_count}")

    if DRY_RUN:
        print("\n** DRY RUN COMPLETE **")
        print("To cast votes, set DRY_RUN = False and run again.")

    print("")


if __name__ == '__main__':
    main()
