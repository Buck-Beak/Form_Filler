import asyncio
from visual_feedback import VisualFeedback

KEY_MAP = {
    "date_of_birth": "dob",
    "dob": "dob",
    "phone": "mobile",
    "mobile": "mobile",
    "pan": "panAdhaarUserId",
    "aadhaar_number": "panAdhaarUserId",
    "aadhaar": "panAdhaarUserId",
}

async def autofill_form(page, classified_fields, user_data):
    filled_count = 0
    
    # Initialize visual feedback
    visual = VisualFeedback(page)
    await visual.inject_visual_styles()
    
    for mapping in classified_fields:
        field_id = mapping.get("id")
        field_name = mapping.get("name")
        category = mapping.get("category")
        field_frame = mapping.get("frame", "main")
        data_key = KEY_MAP.get(category, category)
        value = user_data.get(data_key)
        if not value:
            print(f"↪ Skip: no user value for category='{category}' (mapped key='{data_key}')")
            continue
        candidates = []
        if field_id:
            candidates.append(f"#{field_id}")
        if field_name:
            candidates.append(f"[name='{field_name}']")
        if mapping.get("formcontrolname"):
            candidates.append(f"[formcontrolname='{mapping['formcontrolname']}']")
        if mapping.get("placeholder"):
            candidates.append(f"[placeholder='{mapping['placeholder']}']")
        if mapping.get("aria_label"):
            candidates.append(f"[aria-label='{mapping['aria_label']}']")
        if not candidates:
            print(f"↪ Skip: no selector candidates for category='{category}'")
            continue
        target_frame = page.main_frame
        if field_frame != "main":
            for frame in page.frames:
                if frame.url == field_frame or frame.name == field_frame:
                    target_frame = frame
                    break
        filled_this = False
        for selector in candidates:
            try:
                element = target_frame.locator(selector).first
                await asyncio.sleep(0.2)
                if not await element.count():
                    continue
                if not await element.is_visible():
                    continue
                
                # Show visual feedback
                try:
                    await visual.show_filling_field(category, str(value))
                    await visual.highlight_element(selector, "clicking")
                except:
                    pass  # Don't fail filling if visual feedback fails
                
                await element.click()
                await asyncio.sleep(0.1)
                try:
                    await element.clear()
                except Exception:
                    await element.fill("")
                await asyncio.sleep(0.1)
                await element.type(str(value), delay=50)
                filled_count += 1
                filled_this = True
                print(f"✅ Filled '{category}' (mapped '{data_key}') via {selector} in frame {field_frame}")
                break
            except Exception as e:
                print(f"⚠️ Try selector failed for '{category}' via {selector}: {e}")
        if not filled_this:
            print(f"❌ Could not fill '{category}' (mapped '{data_key}') — no selector matched")
    
    print(f"\n🎉 Total fields filled: {filled_count}/{len(classified_fields)}")
    return filled_count
