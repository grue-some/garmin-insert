import os
import struct
from pathlib import Path
from fitparse import FitFile

# ==================== CONFIGURATION ====================
# Your exact Windows 11 PC directory paths
INPUT_FOLDER = r"C:\some\directory\with\FitFiles-to-fix"
OUTPUT_FOLDER = r"C:\some\directory\for\FitFiles-fixed"

# Garmin Edge 1050 official profile IDs
TARGET_MANUFACTURER = 1       # 1 = Garmin
TARGET_PRODUCT = 4440         # 4440 = Edge 1050s
# =======================================================

# Garmin FIT CRC-16 Look-up Table
CRC_TABLE = [
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400
]

def calculate_crc(data: bytes) -> int:
    """Computes the standard Garmin FIT 16-bit CRC checksum over binary data."""
    crc = 0
    for byte in data:
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ CRC_TABLE[byte & 0xF]
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ CRC_TABLE[(byte >> 4) & 0xF]
    return crc

def rebuild_fit_with_edge1050(input_path, output_path):
    """Precisely patches the top-level file_id block and updates the CRC footprint."""
    with open(input_path, 'rb') as f:
        raw_bytes = bytearray(f.read())

    header_size = raw_bytes[0]
    data_size, = struct.unpack('<I', raw_bytes[4:8])
    crc_end_point = header_size + data_size

    # Use fitparse to read the original Wahoo identifiers out of this specific file
    fit_file = FitFile(str(input_path))
    
    for message in fit_file.get_messages('file_id'):
        mfg_field = message.get('manufacturer')
        prod_field = message.get('product')
        
        if mfg_field is not None and prod_field is not None:
            orig_mfg = mfg_field.raw_value
            orig_prod = prod_field.raw_value
            
            # Look for the sequential manufacturer + product byte sequence
            search_bytes = struct.pack('<H', int(orig_mfg)) + struct.pack('<H', int(orig_prod))
            
            # CRITICAL: We strictly limit the search to the first 150 bytes following the header
            # This protects the training load data from accidental corruption deeper in the file
            target_offset = raw_bytes.find(search_bytes, header_size, header_size + 150)
            
            if target_offset != -1:
                raw_bytes[target_offset:target_offset+2] = struct.pack('<H', TARGET_MANUFACTURER)
                raw_bytes[target_offset+2:target_offset+4] = struct.pack('<H', TARGET_PRODUCT)
                break
            else:
                # Fallback separate matching within the safe 150-byte zone
                old_mfg_b = struct.pack('<H', int(orig_mfg))
                old_prod_b = struct.pack('<H', int(orig_prod))
                
                m_off = raw_bytes.find(old_mfg_b, header_size, header_size + 150)
                p_off = raw_bytes.find(old_prod_b, header_size, header_size + 150)
                
                if m_off != -1: raw_bytes[m_off:m_off+2] = struct.pack('<H', TARGET_MANUFACTURER)
                if p_off != -1: raw_bytes[p_off:p_off+2] = struct.pack('<H', TARGET_PRODUCT)
                break

    # Recalculate and seal the file footer using the clean CRC loop
    bytes_to_crc = raw_bytes[:crc_end_point]
    new_crc = calculate_crc(bytes_to_crc)
    struct.pack_into('<H', raw_bytes, crc_end_point, new_crc)

    with open(output_path, 'wb') as out_f:
        out_f.write(raw_bytes[:crc_end_point + 2])

def main():
    in_dir = Path(INPUT_FOLDER)
    out_dir = Path(OUTPUT_FOLDER)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    if not in_dir.exists():
        print(f"Error: The input directory does not exist: {INPUT_FOLDER}")
        return

    fit_files = list(in_dir.glob("*.fit"))
    if not fit_files:
        print(f"No .fit files found in your input folder: {INPUT_FOLDER}")
        return
        
    print(f"Found {len(fit_files)} files. Running training-load compliant conversion...")
    
    success_count = 0
    for file_path in fit_files:
        output_file_path = out_dir / file_path.name
        try:
            rebuild_fit_with_edge1050(file_path, output_file_path)
            success_count += 1
            size_kb = output_file_path.stat().st_size / 1024
            print(f"[{success_count}/{len(fit_files)}] Processed: {file_path.name} ({size_kb:.1f} KB)")
        except Exception as e:
            print(f"Error processing {file_path.name}: {e}")

    print(f"\nSuccess! Rebuilt {success_count} files.")
    print(f"Your full-sized training load compliant files are waiting in: {OUTPUT_FOLDER}")

if __name__ == "__main__":
    main()
