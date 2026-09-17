import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def make_license_plate(text: str, filename: str, is_commercial: bool = False):
    """
    Generates a realistic Indian license plate image.
    Standard private vehicle: White background with black text.
    Commercial/transport: Yellow background with black text.
    Includes the blue 'IND' strip with chakra symbol on the left.
    """
    w, h = 520, 110
    bg_color = (245, 200, 0) if is_commercial else (255, 255, 255)
    
    # Create base PIL image
    img = Image.new("RGB", (w, h), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Draw outer border
    draw.rectangle([2, 2, w - 3, h - 3], outline=(20, 20, 20), width=4)
    
    # Left blue IND strip (HSRP format)
    strip_w = 48
    draw.rectangle([6, 6, strip_w, h - 6], fill=(0, 51, 153))
    
    # IND text in strip
    try:
        font_ind = ImageFont.truetype("C:\\Windows\\Fonts\\arialbd.ttf", 14)
        font_chakra = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 18)
    except Exception:
        font_ind = ImageFont.load_default()
        font_chakra = font_ind
        
    draw.text((12, 18), "IND", fill=(255, 255, 255), font=font_ind)
    draw.text((15, 45), "❂", fill=(0, 180, 255), font=font_chakra)
    
    # Main plate text
    try:
        # High-legibility bold font
        font_plate = ImageFont.truetype("C:\\Windows\\Fonts\\impact.ttf", 64)
    except Exception:
        try:
            font_plate = ImageFont.truetype("C:\\Windows\\Fonts\\arialbd.ttf", 54)
        except Exception:
            font_plate = ImageFont.load_default()
            
    # Calculate position for center-aligned text
    bbox = draw.textbbox((0, 0), text, font=font_plate)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    text_x = strip_w + 15 + ((w - strip_w - 20) - text_w) // 2
    text_y = (h - text_h) // 2 - 5
    
    draw.text((text_x, text_y), text, fill=(10, 10, 10), font=font_plate)
    
    # Save image
    out_path = os.path.join("demo_plates", filename)
    img.save(out_path, quality=95)
    print(f"Generated plate image: {out_path}")
    return out_path

if __name__ == "__main__":
    make_license_plate("DL 01 AB 1234", "plate_cleared_DL01AB1234.jpg", is_commercial=False)
    make_license_plate("JK 02 XY 9999", "plate_watchlist_JK02XY9999.jpg", is_commercial=True)
    make_license_plate("DL 0I AB I234", "plate_fuzzy_DL0IAB1234.jpg", is_commercial=False)
    print("All demo plates generated successfully!")
