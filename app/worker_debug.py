from datetime import datetime, timezone

from worker import (
    process_pcaps_to_csv,
    process_csvs_to_windows,
	#    prune_old_files,
)

def main():
    print("=== STEP 1: PCAP -> CSV ===")
    process_pcaps_to_csv()

    print("=== STEP 2: CSV -> windows + LLM ===")
    process_csvs_to_windows()

#    print("=== STEP 3: prune old files ===")
#    now = datetime.now(timezone.utc)
#    prune_old_files(now)

    print("=== DONE ===")

if __name__ == "__main__":
    main()

