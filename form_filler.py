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
    "full_name": "name",
    "name": "name",
    "gender": "gender",
    "occupation": "occupation",
    "terms_agreement": "terms_agreement"
}

async def autofill_form(page, classified_fields, user_data):
    filled_count = 0
    
    # Initialize visual feedback
    visual = VisualFeedback(page)
    await visual.inject_visual_styles()
    
    # Extract "extracted_fields" if nested (as seen in main.py logic)
    actual_user_data = user_data.get("extracted_fields", user_data)
    
    for mapping in classified_fields:
        category = mapping.get("category")
        if category == "other":
            continue
            
        field_id = mapping.get("id")
        field_name = mapping.get("name")
        field_type = mapping.get("type", "text").lower()
        field_frame = mapping.get("frame", "main")
        
        data_key = KEY_MAP.get(category, category)
        value = actual_user_data.get(data_key)
        
        if value is None:
            print(f"↪ Skip: no user value for '{category}' (data_key='{data_key}')")
            continue

        target_frame = page.main_frame
        if field_frame != "main":
            for frame in page.frames:
                if frame.url == field_frame or frame.name == field_frame:
                    target_frame = frame
                    break

        try:
            # ── 1. RADIO BUTTONS ──────────────────────────────────────────────
            if field_type == "radio":
                # Find the radio with the matching value
                selector = f"input[type='radio'][name='{field_name}'][value='{str(value).lower()}']"
                element = target_frame.locator(selector)
                if await element.count() > 0:
                    await visual.show_filling_field(category, str(value))
                    await element.click()
                    filled_count += 1
                    print(f"[LOGIN] Typed '{category}': {value}")
                continue

            # ── 2. SELECT DROPDOWNS ────────────────────────────────────────────
            if field_type == "select" or field_type == "select-one":
                selector = f"select[name='{field_name}']" if field_name else f"#{field_id}"
                element = target_frame.locator(selector)
                if await element.count() > 0:
                    await visual.show_filling_field(category, str(value))
                    await element.select_option(value=str(value).lower())
                    filled_count += 1
                    print(f"[LOGIN] Selected Opt '{category}': {value}")
                continue

            # ── 3. CHECKBOXES ──────────────────────────────────────────────────
            if field_type == "checkbox":
                selector = f"input[type='checkbox'][name='{field_name}']" if field_name else f"#{field_id}"
                element = target_frame.locator(selector)
                if await element.count() > 0:
                    if value is True or str(value).lower() in ["true", "yes", "1", "on"]:
                        await visual.show_filling_field(category, "CHECKED")
                        await element.check()
                        filled_count += 1
                        print(f"[LOGIN] Checked '{category}'")
                continue

            # ── 4. TEXT / GENERAL INPUTS ───────────────────────────────────────
            # Re-use your candidate logic for text fields
            candidates = []
            if field_id: candidates.append(f"#{field_id}")
            if field_name: candidates.append(f"[name='{field_name}']")
            
            for selector in candidates:
                element = target_frame.locator(selector).first
                if await element.count() > 0 and await element.is_visible():
                    await visual.show_filling_field(category, str(value))
                    await element.fill(str(value))
                    filled_count += 1
                    print(f"[LOGIN] Typed '{category}': {value}")
                    break

        except Exception as e:
            print(f"[LOGIN] Error filling '{category}': {e}")

    # ── 🚀 AUTO-SUBMIT ────────────────────────────────────────────────────────
    auto_submit_enabled = actual_user_data.get("auto_submit", False)
    
    if not auto_submit_enabled:
        print("\n✋ Auto-Submit is DISABLED. Please verify the form and click Submit manually.")
        await visual.add_thought("✋ Auto-Submit is disabled. Please review and submit manually.")
        print(f"\nTotal fields filled: {filled_count}/{len(classified_fields)}")
        return filled_count

    print("\nAttempting Auto-Submit...")
    await asyncio.sleep(1)
    try:
        # Look for submit buttons
        submit_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "input[type='button'][value*='Submit' i]",
            "input[type='button'][value*='Register' i]",
            "input[type='button'][value*='Apply' i]",
            "button:has-text('Submit')",
            "button:has-text('Register')",
            "button:has-text('Apply')",
            "button:has-text('Submit and Continue')",
            "button:has-text('Next')",
            ".btn:has-text('Submit')",
            ".btn:has-text('Register')"
        ]
        
        for sel in submit_selectors:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible():
                print(f"Clicking submit button: {sel}")
                await visual.add_thought("🚀 Form filled! Clicking Submit...")
                await btn.click()
                break
    except Exception as e:
        print(f"Submit failed: {e}")

    print(f"\n🎉 Total fields filled: {filled_count}/{len(classified_fields)}")
    return filled_count
