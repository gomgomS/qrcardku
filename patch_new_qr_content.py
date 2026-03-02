import re

file_path = r'c:\Users\msi-pc\Documents\Project\ANTIGRAVITY_EDITOR\QR_PROJECTS\templates\user\new_qr_content.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Patch basic input fields
inputs_to_patch = ['pdf_company', 'pdf_title', 'pdf_desc', 'pdf_website', 'pdf_btn_text']

for field in inputs_to_patch:
    # Remove existing value="..." if any
    content = re.sub(rf'(name=\"{field}\"[^>]*?)value=\"[^\"]*\"', r'\1', content)
    # Add the new value template
    content = re.sub(rf'(name=\"{field}\" [^>]*?)>', rf'\1 value="{{{{ qrcard.get(\'{field}\', \'\') if qrcard else \'\' }}}}">', content)

# 2. Patch color hex inputs
color_fields = {'pdf_primary_color': '#2F6BFD', 'pdf_secondary_color': '#0E379A', 'pdf_title_color': '#000000', 'pdf_text_color': '#000000'}
for field, default_val in color_fields.items():
    # Remove existing value="..."
    content = re.sub(rf'(name=\"{field}\"[^>]*?)value=\"[^\"]*\"', r'\1', content)
    content = re.sub(rf'(name=\"{field}\" [^>]*?)>', rf'\1 value="{{{{ qrcard.get(\'{field}\', \'{default_val}\') if qrcard else \'{default_val}\' }}}}">', content)

# 3. Patch Welcome Time Slider
slider_pattern = r'(name=\"welcome_time\"[^>]*?)value=\"[^\"]*\"'
content = re.sub(slider_pattern, r'\1', content) # Ensure removed if there
# Wait, the field in HTML was `name="pdf_welcome_time"` before? Let's check. 
# Oh wait, my implementation earlier had `name="pdf_welcome_time"`. Wait, let me check the HTML again.
# Ah, the HTML has `name="pdf_welcome_time"` but in `server.py` it's extracting `welcome_time`.
# I should just patch both. Let's find name="pdf_welcome_time"
content = re.sub(r'name=\"pdf_welcome_time\"', r'name="welcome_time"', content)
# Now patch value
slider_pattern = r'(name=\"welcome_time\"[^>]*?)value=\"[^\"]*\"'
content = re.sub(slider_pattern, r'\1', content) 
slider_replace = r'\1 value="{{ qrcard.get(\'welcome_time\', \'2.5\') if qrcard else \'2.5\' }}"'
content = re.sub(r'(name=\"welcome_time\" [^>]*?)>', slider_replace + '>', content)


# 4. Inject Initialization JS
js_injection = '''
<script>
document.addEventListener("DOMContentLoaded", () => {
    // PDF Initialization Block for Edit/Draft Mode
    const qrcard_pdf_template = "{{ qrcard.get('pdf_template', 'default') if qrcard else 'default' }}";
    const qrcard_pdf_primary_color = "{{ qrcard.get('pdf_primary_color', '#2F6BFD') if qrcard else '#2F6BFD' }}";
    const qrcard_pdf_secondary_color = "{{ qrcard.get('pdf_secondary_color', '#0E379A') if qrcard else '#0E379A' }}";
    const qrcard_pdf_title_font = "{{ qrcard.get('pdf_title_font', 'Lato') if qrcard else 'Lato' }}";
    const qrcard_pdf_text_font = "{{ qrcard.get('pdf_text_font', 'Lato') if qrcard else 'Lato' }}";
    
    // Set Template Active
    const templates = document.querySelectorAll('.template-preview');
    templates.forEach(t => {
        if (t.dataset.template === qrcard_pdf_template) {
            t.classList.add('active');
        } else {
            t.classList.remove('active');
        }
    });

    // Pickers sync to hex
    const priPicker = document.getElementById('pdf_primary_picker');
    const secPicker = document.getElementById('pdf_secondary_picker');
    const priHex = document.getElementById('pdf_primary_hex');
    const secHex = document.getElementById('pdf_secondary_hex');
    
    if (priPicker && priHex) {
        priPicker.value = qrcard_pdf_primary_color;
        priHex.value = qrcard_pdf_primary_color.toUpperCase();
    }
    if (secPicker && secHex) {
        secPicker.value = qrcard_pdf_secondary_color;
        secHex.value = qrcard_pdf_secondary_color.toUpperCase();
    }

    // Dropdowns
    const titleSelect = document.querySelector('select[name="pdf_title_font"]');
    const textSelect = document.querySelector('select[name="pdf_text_font"]');
    if (titleSelect) titleSelect.value = qrcard_pdf_title_font;
    if (textSelect) textSelect.value = qrcard_pdf_text_font;

    // Time Slider Label
    const timeSlider = document.getElementById('welcome-time-slider');
    const timeDisplay = document.getElementById('welcome-time-display');
    if (timeSlider && timeDisplay) {
        timeDisplay.textContent = timeSlider.value + " seconds";
    }
    
    // Trigger any mockup updates globally
    if(window.updateAllMockups) {
        window.updateAllMockups();
    }
});
</script>
'''

if 'PDF Initialization Block for Edit' not in content:
    # Replace only the LAST occurrence of {% endblock %}
    parts = content.rsplit('{% endblock %}', 1)
    if len(parts) == 2:
        content = parts[0] + js_injection + '\n{% endblock %}'

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Variables injected!")
