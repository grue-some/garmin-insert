import os
import time
import datetime
from fitparse import FitFile
from garminconnect import Garmin

# ==================== CONFIGURATION ====================
GARMIN_EMAIL = "address@email.com"
GARMIN_PASSWORD = "password"
MODIFIED_FILES_DIR = "../some/directory/path"  # Folder containing new modified files

# Set DRY_RUN to True to test and find matches without deleting or uploading anything.
# Set to False only when you are ready to execute the changes.
DRY_RUN = True
# =========================================

def get_fit_start_time(file_path):
    """Extracts the exact creation/start timestamp from the FIT file in UTC."""
    try:
        fit_file = FitFile(file_path)
        for record in fit_file.get_messages('file_id'):
            for data in record:
                if data.name == 'time_created':
                    return data.value  # Returns a naive datetime object (UTC)
    except Exception as e:
        print(f"Error parsing FIT file {file_path}: {e}")
    return None

def main():
    if not os.path.exists(MODIFIED_FILES_DIR):
        print(f"Error: Directory '{MODIFIED_FILES_DIR}' does not exist.")
        return

    # Initialize and log in to Garmin Connect
    print("Logging into Garmin Connect...")
    try:
        client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
        client.login()
        print("Login successful.\n")
    except Exception as e:
        print(f"Authentication failed: {e}")
        return

    # List all FIT files in the target directory
    fit_files = [f for f in os.listdir(MODIFIED_FILES_DIR) if f.lower().endswith('.fit')]
    total_files = len(fit_files)
    print(f"Found {total_files} FIT files to process.")
    
    if DRY_RUN:
        print("⚠️ RUNNING IN DRY-RUN MODE. No changes will be made to your account. ⚠️\n")

    success_count = 0
    fail_count = 0

    for index, filename in enumerate(fit_files, 1):
        file_path = os.path.join(MODIFIED_FILES_DIR, filename)
        print(f"[{index}/{total_files}] Processing: {filename}")
        
        start_time = get_fit_start_time(file_path)
        if not start_time:
            print(f"  ❌ Skipped: Could not read timestamp from file.")
            fail_count += 1
            continue
        
        # FIX: Expand search boundaries to 36 hours before/after to guarantee catching 
        # activities that crossed the midnight UTC boundary (e.g., started after 5 PM local).
        start_window = (start_time - datetime.timedelta(hours=36)).date().isoformat()
        end_window = (start_time + datetime.timedelta(hours=36)).date().isoformat()
        
        try:
            activities = client.get_activities_by_date(start_window, end_window)
        except Exception as e:
            print(f"  ❌ Error fetching Garmin activities: {e}")
            fail_count += 1
            continue

        # Try to find a matching activity within a 2-minute window using UTC/GMT
        matching_activity = None
        for act in activities:
            # Clean up the Garmin GMT string (handles '2026-04-16T10:29:29.0' or '2026-04-16 10:29:29Z')
            gmt_str = act['startTimeGMT'].replace('T', ' ').replace('Z', '')
            if '.' in gmt_str:
                gmt_str = gmt_str.split('.')[0]
                
            try:
                act_time_utc = datetime.datetime.strptime(gmt_str, '%Y-%m-%d %H:%M:%S')
            except Exception as parse_err:
                print(f"  ⚠️ Could not parse Garmin time string '{gmt_str}': {parse_err}")
                continue
            
            time_diff = abs((act_time_utc - start_time.replace(tzinfo=None)).total_seconds())
            if time_diff < 120:  # 2-minute grace window
                matching_activity = act
                break

        if not matching_activity:
            print(f"  ❌ Skipped: No matching Garmin activity found close to timestamp {start_time} UTC")
            fail_count += 1
            continue

        activity_id = matching_activity['activityId']
        activity_name = matching_activity['activityName']
        print(f"  Found match: '{activity_name}' (ID: {activity_id})")

        if DRY_RUN:
            print(f"  [DRY RUN] Would delete ID {activity_id}, upload {filename}, and rename to '{activity_name}'.")
            success_count += 1
        else:
            try:
                # 1. Delete original activity
                print(f"  Deleting original activity {activity_id}...")
                client.delete_activity(activity_id)
                
                # 2. Upload the new modified FIT file
                print(f"  Uploading modified file...")
                client.upload_activity(file_path)
                
                # Extended buffer (8 seconds) to let Garmin process file ingestion completely
                print(f"  Waiting 8 seconds for Garmin server parsing...")
                time.sleep(8)
                
                # 3. Find the freshly uploaded activity to fetch its new ID
                print(f"  Fetching new activity ID...")
                fresh_activities = client.get_activities_by_date(start_window, end_window)
                
                new_activity_id = None
                for act in fresh_activities:
                    gmt_str = act['startTimeGMT'].replace('T', ' ').replace('Z', '')
                    if '.' in gmt_str:
                        gmt_str = gmt_str.split('.')[0]
                    act_time_utc = datetime.datetime.strptime(gmt_str, '%Y-%m-%d %H:%M:%S')
                    
                    time_diff = abs((act_time_utc - start_time.replace(tzinfo=None)).total_seconds())
                    if time_diff < 120:
                        new_activity_id = act['activityId']
                        break
                
                # 4. Direct HTTP API Renaming Method
                if new_activity_id:
                    print(f"  Renaming new activity {new_activity_id} to '{activity_name}'...")
                    url = f"/activity-service/activity/{new_activity_id}"
                    payload = {"activityId": int(new_activity_id), "activityName": str(activity_name)}
                    
                    # Direct client engine execution
                    client.client.put("connectapi", url, json=payload)
                    
                    print(f"  ✅ Successfully replaced and renamed!")
                    success_count += 1
                else:
                    print(f"  ⚠️ Uploaded successfully, but could not locate the new activity ID inside the lookup window.")
                    fail_count += 1
                    
            except Exception as e:
                print(f"  ❌ Critical error during replacement: {e}")
                fail_count += 1

        # Anti-ban cooldown delay between processing separate files (5 seconds)
        time.sleep(5)

    print("\n==================== SUMMARY ====================")
    print(f"Process complete. Total processed: {total_files}")
    print(f"Successful matches/replacements: {success_count}")
    print(f"Failed/Skipped: {fail_count}")
    if DRY_RUN:
        print("Reminder: This was a DRY RUN. Change DRY_RUN = False to execute for real.")
    print("=================================================")

if __name__ == "__main__":
    main()
