/* qr_frame_picker.js — Custom QR frame picker for all design pages.
   Include this BEFORE the page's inline script block.
   Requires: #qrcode-img, #qr-preview-frame, #frame_id (hidden input),
             #custom-frames-grid, #custom-frames-empty in the DOM. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var qrImg       = document.getElementById('qrcode-img');
        var frameDiv    = document.getElementById('qr-preview-frame');
        var frameInput  = document.getElementById('frame_id');
        if (!qrImg || !frameDiv) return;

        var plainQrDataUrl = null;

        /* Capture the first plain QR data-URL written to #qrcode-img */
        var _obs = new MutationObserver(function () {
            var src = qrImg.getAttribute('src') || '';
            if (src.startsWith('data:') && !plainQrDataUrl) {
                plainQrDataUrl = src;
                _obs.disconnect();
            }
        });
        _obs.observe(qrImg, { attributes: true, attributeFilter: ['src'] });

        /* Composite QR onto frame image at the marked area */
        function compositeQR(qrDataUrl, frame) {
            return new Promise(function (resolve, reject) {
                var fi = new Image();
                fi.onload = function () {
                    var qi = new Image();
                    qi.onload = function () {
                        var cv = document.createElement('canvas');
                        cv.width  = fi.naturalWidth;
                        cv.height = fi.naturalHeight;
                        var ctx = cv.getContext('2d');
                        ctx.drawImage(fi, 0, 0);
                        ctx.drawImage(qi,
                            frame.qr_x * cv.width,
                            frame.qr_y * cv.height,
                            frame.qr_w * cv.width,
                            frame.qr_h * cv.height
                        );
                        resolve(cv.toDataURL('image/png'));
                    };
                    qi.onerror = reject;
                    qi.src = qrDataUrl;
                };
                fi.onerror = reject;
                fi.src = frame.image_url;
            });
        }

        function applyCustomFrame(frame) {
            var src = plainQrDataUrl || qrImg.getAttribute('src') || '';
            if (!src.startsWith('data:')) return;
            compositeQR(src, frame)
                .then(function (composited) {
                    qrImg.src = composited;
                    frameDiv.className         = 'qr-preview-frame frame-none';
                    frameDiv.style.backgroundImage = '';
                    qrImg.style.maxWidth  = '100%';
                    qrImg.style.maxHeight = '320px';
                    qrImg.style.width     = 'auto';
                    qrImg.style.height    = 'auto';
                    qrImg.style.display   = 'block';
                })
                .catch(function (err) { console.error('QFP error:', err); });
        }

        function selectFrame(el) {
            /* Deselect all preset + custom frame options */
            document.querySelectorAll('.frame-option, .frame-option-custom').forEach(function (s) {
                s.classList.remove('active');
            });
            el.classList.add('active');

            var customId = el.getAttribute('data-custom-frame-id');
            if (customId) {
                if (frameInput) frameInput.value = customId;
                applyCustomFrame({
                    image_url: el.getAttribute('data-frame-img'),
                    qr_x: parseFloat(el.getAttribute('data-frame-qx') || 0),
                    qr_y: parseFloat(el.getAttribute('data-frame-qy') || 0),
                    qr_w: parseFloat(el.getAttribute('data-frame-qw') || 0),
                    qr_h: parseFloat(el.getAttribute('data-frame-qh') || 0),
                });
            } else {
                if (frameInput) frameInput.value = '';
                frameDiv.className         = 'qr-preview-frame frame-' + (el.getAttribute('data-frame') || 'none');
                frameDiv.style.backgroundImage = '';
                if (plainQrDataUrl) {
                    qrImg.src = plainQrDataUrl;
                    qrImg.style.maxWidth = qrImg.style.maxHeight =
                    qrImg.style.width    = qrImg.style.height = '';
                }
            }
        }

        /* Expose selectFrame globally so dynamically-added frames (e.g. admin defaults) can use it */
        window.qfpSelectFrame = selectFrame;

        /* Attach click handlers to preset frame options (fires before inline handler) */
        document.querySelectorAll('.frame-option').forEach(function (item) {
            item.addEventListener('click', function () { selectFrame(this); });
        });

        /* Load admin default frames */
        fetch('/api/frames/default')
            .then(function (r) { return r.json(); })
            .then(function (frames) {
                var section = document.getElementById('default-frames-section');
                var grid    = document.getElementById('default-frames-grid');
                if (!grid || !frames || frames.length === 0) return;
                if (section) section.style.display = 'block';
                frames.forEach(function (f) {
                    var d = document.createElement('div');
                    d.className = 'grid-item frame-option-custom';
                    d.setAttribute('data-custom-frame-id', f.frame_id);
                    d.setAttribute('data-frame-img',       f.image_url);
                    d.setAttribute('data-frame-qx',        f.qr_x);
                    d.setAttribute('data-frame-qy',        f.qr_y);
                    d.setAttribute('data-frame-qw',        f.qr_w);
                    d.setAttribute('data-frame-qh',        f.qr_h);
                    d.title = f.name;
                    d.innerHTML = '<img class="custom-frame-thumb" src="' + f.image_url + '" alt="' + f.name + '"><span class="frame-label">' + f.name + '</span>';
                    d.addEventListener('click', function () { selectFrame(this); });
                    grid.appendChild(d);
                });
            })
            .catch(function () {});

        /* Load custom frames from API */
        fetch('/user/frames/api')
            .then(function (r) { return r.json(); })
            .then(function (frames) {
                var grid  = document.getElementById('custom-frames-grid');
                var empty = document.getElementById('custom-frames-empty');
                if (!grid) return;
                if (!frames || frames.length === 0) {
                    if (empty) empty.textContent = 'No custom frames yet.';
                    return;
                }
                if (empty) empty.style.display = 'none';
                grid.style.display = '';
                frames.forEach(function (f) {
                    var d = document.createElement('div');
                    d.className = 'grid-item frame-option-custom';
                    d.setAttribute('data-custom-frame-id', f.frame_id);
                    d.setAttribute('data-frame-img',       f.image_url);
                    d.setAttribute('data-frame-qx',        f.qr_x);
                    d.setAttribute('data-frame-qy',        f.qr_y);
                    d.setAttribute('data-frame-qw',        f.qr_w);
                    d.setAttribute('data-frame-qh',        f.qr_h);
                    d.title = f.name;
                    d.innerHTML = '<img src="' + f.image_url + '" alt="" '
                        + 'style="width:100%;max-width:40px;height:auto;aspect-ratio:1/1;object-fit:cover;border-radius:4px;display:block;flex-shrink:0;">'
                        + '<span class="frame-label" style="margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%;display:block;">' + f.name + '</span>';
                    d.addEventListener('click', function () { selectFrame(this); });
                    grid.appendChild(d);
                });
            })
            .catch(function () {
                var empty = document.getElementById('custom-frames-empty');
                if (empty) empty.textContent = 'Could not load frames.';
            });
    });
})();
