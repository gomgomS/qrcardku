def fix_js_selectors():
    edit_qr_path = r"c:\Users\msi-pc\Documents\Project\ANTIGRAVITY_EDITOR\QR_PROJECTS\templates\user\edit_qr_content.html"

    with open(edit_qr_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # The issue:
    # replacement.replace('name="pdf_btn_text"', 'name="pdf_btn_text" value="{{ qrcard.get(\'pdf_btn_text\', \'\') }}"')
    # This also replaced the JavaScript document.querySelector('input[name="pdf_btn_text"]')

    # Fix: Revert the JavaScript selectors
    content = content.replace("querySelector('input[name=\"pdf_btn_text\" value=\"{{ qrcard.get('pdf_btn_text', '') }}\"]')", "querySelector('input[name=\"pdf_btn_text\"]')")
    content = content.replace("querySelector('input[name=\"pdf_company\" value=\"{{ qrcard.get('pdf_company', '') }}\"]')", "querySelector('input[name=\"pdf_company\"]')")
    content = content.replace("querySelector('input[name=\"pdf_title\" value=\"{{ qrcard.get('pdf_title', '') }}\"]')", "querySelector('input[name=\"pdf_title\"]')")
    content = content.replace("querySelector('input[name=\"pdf_desc\" value=\"{{ qrcard.get('pdf_desc', '') }}\"]')", "querySelector('input[name=\"pdf_desc\"]')")
    content = content.replace("querySelector('input[name=\"pdf_website\" value=\"{{ qrcard.get('pdf_website', '') }}\"]')", "querySelector('input[name=\"pdf_website\"]')")

    with open(edit_qr_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print("Fixed JS Selectors.")

fix_js_selectors()
