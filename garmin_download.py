import io
import os
import zipfile
from pathlib import Path
from garminconnect import Garmin

# ==================== CONFIGURATION ====================
USERNAME = "name@email.com"
PASSWORD = "password"

DOWNLOAD_FOLDER = r"C:\some\directory"
NUMBER_OF_ACTIVITIES = 100
# =======================================================


def main():
    out_dir = Path(DOWNLOAD_FOLDER)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Logging into Garmin Connect...")
    try:
        client = Garmin(USERNAME, PASSWORD)
        client.login()
        print("Login successful!")

        print(
            f"Fetching metadata for the last {NUMBER_OF_ACTIVITIES} activities..."
        )
        activities = client.get_activities(0, NUMBER_OF_ACTIVITIES)

        print(f"Starting fast binary downloads into: {DOWNLOAD_FOLDER}")
        for idx, activity in enumerate(activities, 1):
            activity_id = activity["activityId"]

            # Pull the actual custom name from your dashboard (e.g., "Los_Angeles_Cycling")
            display_name = activity.get(
                "activityName", f"Activity_{activity_id}"
            )
            clean_display_name = "".join(
                c for c in display_name if c.isalnum() or c in (" ", "_", "-")
            ).strip()
            clean_display_name = clean_display_name.replace(" ", "_")

            filename = f"{clean_display_name}_{activity_id}.fit"
            file_path = out_dir / filename

            print(
                f"[{idx}/{len(activities)}] Processing True Binary: {filename}"
            )

            # CORRECT ARGUMENT: dl_fmt requests the raw zip stream explicitly
            zip_payload = client.download_activity(
                activity_id, dl_fmt=client.ActivityDownloadFormat.ORIGINAL
            )

            try:
                # Instantly extract the real .fit payload from Garmin's memory stream
                with zipfile.ZipFile(io.BytesIO(zip_payload)) as z:
                    for zip_info in z.infolist():
                        if zip_info.filename.lower().endswith(".fit"):
                            fit_data = z.read(zip_info.filename)

                            # Save the uncompressed data using your custom activity name
                            with open(file_path, "wb") as f:
                                f.write(fit_data)
                            break
            except zipfile.BadZipFile:
                # Safe fallback if your version pulls raw bytes instead of a zip file
                with open(file_path, "wb") as f:
                    f.write(zip_payload)

        print(
            f"\nSuccess! All true binary files are now downloaded to: {DOWNLOAD_FOLDER}"
        )
        print(
            "You can now run your working training load script (bulk_edit.py) over this folder!"
        )

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
