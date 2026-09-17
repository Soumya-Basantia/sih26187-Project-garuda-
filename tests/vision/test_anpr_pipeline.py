import cv2
import json
from ai_engine.anpr.plate_recognizer import PlateRecognizer, PlateStatus

def test_anpr():
    recognizer = PlateRecognizer()
    print("ANPR Engine loaded. EasyOCR available:", recognizer._available)

    # Seed the watchlist/registered vehicles
    demo_db_vehicles = [
        {
            "vehicle_id": "veh-demo-01",
            "plate_number": "DL01AB1234",
            "vehicle_type": "SUV",
            "owner_name": "Capt. Vikram Singh",
            "watchlist_flag": False,
            "notes": "Border Patrol Commander — High Priority Clearance",
        },
        {
            "vehicle_id": "veh-demo-02",
            "plate_number": "JK02XY9999",
            "vehicle_type": "Heavy Truck",
            "owner_name": "Unknown / Suspicious",
            "watchlist_flag": True,
            "notes": "🚨 BOLO Alert: Suspected infiltration logistics vehicle",
        }
    ]

    recognizer.load_watchlist(demo_db_vehicles)
    print(f"Loaded {len(demo_db_vehicles)} demo vehicles into the engine.")
    print("-" * 60)

    test_cases = [
        ("demo_plates/plate_cleared_DL01AB1234.jpg", "Cleared Authorized Vehicle (DL 01 AB 1234)"),
        ("demo_plates/plate_watchlist_JK02XY9999.jpg", "Threat Watchlist Vehicle (JK 02 XY 9999)"),
        ("demo_plates/plate_fuzzy_DL0IAB1234.jpg", "Fuzzy OCR Confusion (DL 0I AB I234 with 'I' instead of '1')"),
    ]

    for img_path, label in test_cases:
        print(f"\n[TEST CASE]: {label}")
        img = cv2.imread(img_path)
        if img is None:
            print(f"Error: Could not read {img_path}")
            continue

        result = recognizer.recognize(img)
        print(f"  Scanned Plate Text : {result.plate_text}")
        print(f"  Detection Status   : {result.status.value}")
        print(f"  Confidence Score   : {round(result.confidence * 100, 1)}%")
        print(f"  Fuzzy Match Used   : {result.is_fuzzy}")
        
        if result.watchlist_match:
            match = result.watchlist_match
            print(f"  Matched Owner      : {match.get('owner_name')}")
            print(f"  Watchlist Flag     : {match.get('watchlist_flag')}")
            try:
                print(f"  Notes              : {match.get('notes')}")
            except Exception:
                print(f"  Notes              : {match.get('notes').encode('ascii', 'replace').decode('ascii')}")

    print("\n" + "=" * 60)
    print("ANPR TEST EXECUTION COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    test_anpr()
