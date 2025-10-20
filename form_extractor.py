import asyncio

async def extract_form_fields(page):
    """Extract input/textarea/select fields with labels, FROM ALL FRAMES"""
    js_code = """
    () => {
        const fields = [];
        const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="image"]), textarea, select');
        inputs.forEach(inp => {
            const field_id = inp.id || '';
            const field_name = inp.name || '';
            const placeholder = inp.placeholder || '';
            const field_type = inp.type || inp.tagName.toLowerCase();
            const formcontrolname = inp.getAttribute('formcontrolname') || '';
            const aria_label = inp.getAttribute('aria-label') || '';
            let label_text = '';
            if (field_id) {
                const label = document.querySelector(`label[for="${field_id}"]`);
                if (label) label_text = label.innerText;
            }
            if (!label_text) {
                const parent = inp.closest('div, td, li, mat-form-field');
                if (parent) {
                    const label = parent.querySelector('label, mat-label');
                    if (label) label_text = label.innerText;
                }
            }
            if (!label_text) {
                label_text = aria_label || placeholder || '';
            }
            label_text = label_text.replace(/[*:]/g, '').trim();
            const rect = inp.getBoundingClientRect();
            const isVisible = rect.width > 0 && rect.height > 0;
            if (isVisible) {
                fields.push({
                    id: field_id,
                    name: field_name,
                    placeholder: placeholder,
                    type: field_type,
                    label: label_text,
                    formcontrolname: formcontrolname,
                    aria_label: aria_label
                });
            }
        });
        return fields;
    }
    """
    all_fields = []
    try:
        main_fields = await page.evaluate(js_code)
        for f in main_fields:
            f['frame'] = 'main'
        all_fields.extend(main_fields)
    except Exception as e:
        print(f"⚠️ Main page extraction failed: {e}")
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            frame_fields = await frame.evaluate(js_code)
            for f in frame_fields:
                f['frame'] = frame.url or frame.name or 'unnamed_frame'
            all_fields.extend(frame_fields)
        except Exception as e:
            print(f"⚠️ Frame {frame.url} extraction failed: {e}")
    return all_fields
