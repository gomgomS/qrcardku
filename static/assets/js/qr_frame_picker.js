/* qr_frame_picker.js — Custom QR frame picker for all design pages.
   Include this BEFORE the page's inline script block.
   Requires: #qrcode-img, #qr-preview-frame, #frame_id (hidden input),
             #custom-frames-grid, #custom-frames-empty in the DOM. */
(function () {
    function _escHtml(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
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

        /* CSS overlay approach — no canvas, no CORS issues.
           Frame image sits behind (z-index 1) as background decoration;
           QR is positioned on top (z-index 2) at the user-marked area. */
        function applyCustomFrame(frame) {
            var fi = new Image();
            fi.onload = function () {
                var ratio = fi.naturalHeight / fi.naturalWidth;
                var W = 200;
                var H = Math.round(W * ratio);

                /* Set up container */
                frameDiv.className        = 'qr-preview-frame frame-none';
                frameDiv.style.position   = 'relative';
                frameDiv.style.width      = W + 'px';
                frameDiv.style.height     = H + 'px';
                frameDiv.style.padding    = '0';
                frameDiv.style.overflow   = 'hidden';
                frameDiv.style.background = 'transparent';
                frameDiv.style.display    = 'block';

                /* Hide caption (frame image carries its own design) */
                var caption = document.getElementById('frame-caption');
                if (caption) caption.style.display = 'none';

                /* Remove any previous frame overlay */
                var old = frameDiv.querySelector('.frame-img-overlay');
                if (old) old.remove();

                /* Frame image as BACKGROUND layer (z-index 1) */
                var overlay = document.createElement('img');
                overlay.className = 'frame-img-overlay';
                overlay.src = frame.image_url;
                overlay.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:fill;pointer-events:none;z-index:1;';
                frameDiv.insertBefore(overlay, frameDiv.firstChild);

                /* QR inner ON TOP of frame image (z-index 2) at the marked area.
                   Must clear aspect-ratio:1 from stylesheet so height isn't forced square. */
                var qrInner = frameDiv.querySelector('.qr-inner');
                if (qrInner) {
                    qrInner.style.position    = 'absolute';
                    qrInner.style.left        = (frame.qr_x * 100) + '%';
                    qrInner.style.top         = (frame.qr_y * 100) + '%';
                    qrInner.style.width       = (frame.qr_w * 100) + '%';
                    qrInner.style.height      = (frame.qr_h * 100) + '%';
                    qrInner.style.maxWidth    = 'none';
                    qrInner.style.aspectRatio = 'auto';
                    qrInner.style.zIndex      = '2';
                    qrInner.style.display     = 'block';
                    qrInner.style.overflow    = 'hidden';
                }

                /* Restore plain QR and make it fill the marked area */
                if (plainQrDataUrl) qrImg.src = plainQrDataUrl;
                qrImg.style.width     = '100%';
                qrImg.style.height    = '100%';
                qrImg.style.maxWidth  = 'none';
                qrImg.style.maxHeight = 'none';
                qrImg.style.objectFit = 'contain';
                qrImg.style.display   = 'block';
            };
            fi.onerror = function () {
                console.warn('QFP: could not load frame image', frame.image_url);
            };
            fi.src = frame.image_url;
        }

        /* Reset preview back to a CSS-based preset frame */
        function resetToPreset(frameName) {
            /* Remove overlay */
            var old = frameDiv.querySelector('.frame-img-overlay');
            if (old) old.remove();

            /* Restore container */
            frameDiv.style.cssText = '';
            frameDiv.className = 'qr-preview-frame frame-' + (frameName || 'none');

            /* Restore qr-inner */
            var qrInner = frameDiv.querySelector('.qr-inner');
            if (qrInner) qrInner.style.cssText = '';

            /* Restore QR image */
            if (plainQrDataUrl) qrImg.src = plainQrDataUrl;
            qrImg.style.cssText = '';

            /* Show caption again */
            var caption = document.getElementById('frame-caption');
            if (caption) caption.style.display = '';
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
                    qr_w: parseFloat(el.getAttribute('data-frame-qw') || 1),
                    qr_h: parseFloat(el.getAttribute('data-frame-qh') || 1),
                });
            } else {
                if (frameInput) frameInput.value = '';
                resetToPreset(el.getAttribute('data-frame') || 'none');
            }
        }

        /* ── SVG Standard Frame support ──────────────────────────────────── */
        var _currentSvgFrame = null;

        function applySvgStandardFrame(frame) {
            var vRatio = frame.vH / frame.vW;
            var W = 200;
            var H = Math.round(W * vRatio);

            frameDiv.className      = 'qr-preview-frame frame-none';
            frameDiv.style.position = 'relative';
            frameDiv.style.width    = W + 'px';
            frameDiv.style.height   = H + 'px';
            frameDiv.style.padding  = '0';
            frameDiv.style.overflow = 'hidden';
            frameDiv.style.background = 'transparent';
            frameDiv.style.display  = 'block';

            var caption = document.getElementById('frame-caption');
            if (caption) caption.style.display = 'none';

            var old = frameDiv.querySelector('.frame-img-overlay');
            if (old) old.remove();

            /* Render SVG as an img via blob URL */
            var svgBlob = new Blob([frame.svg], { type: 'image/svg+xml' });
            var svgUrl  = URL.createObjectURL(svgBlob);
            var overlay = document.createElement('img');
            overlay.className = 'frame-img-overlay';
            overlay.src = svgUrl;
            overlay.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:fill;pointer-events:none;z-index:1;';
            overlay.onload = function () { URL.revokeObjectURL(svgUrl); };
            frameDiv.insertBefore(overlay, frameDiv.firstChild);

            var qrInner = frameDiv.querySelector('.qr-inner');
            if (qrInner) {
                qrInner.style.position    = 'absolute';
                qrInner.style.left        = (frame.qr_x * 100) + '%';
                qrInner.style.top         = (frame.qr_y * 100) + '%';
                qrInner.style.width       = (frame.qr_w * 100) + '%';
                qrInner.style.height      = (frame.qr_h * 100) + '%';
                qrInner.style.maxWidth    = 'none';
                qrInner.style.aspectRatio = 'auto';
                qrInner.style.zIndex      = '2';
                qrInner.style.display     = 'block';
                qrInner.style.overflow    = 'hidden';
            }

            if (plainQrDataUrl) qrImg.src = plainQrDataUrl;
            qrImg.style.width     = '100%';
            qrImg.style.height    = '100%';
            qrImg.style.maxWidth  = 'none';
            qrImg.style.maxHeight = 'none';
            qrImg.style.objectFit = 'contain';
            qrImg.style.display   = 'block';

            _currentSvgFrame = frame;
        }

        function selectSvgFrame(el, frame) {
            document.querySelectorAll('.frame-option, .frame-option-custom, .frame-option-svg').forEach(function (s) {
                s.classList.remove('active');
            });
            el.classList.add('active');
            if (frameInput) frameInput.value = '';   // no DB frame — composite baked client-side
            applySvgStandardFrame(frame);
        }

        /* Override selectFrame to also clear _currentSvgFrame when a non-SVG frame is picked */
        var _origSelectFrame = selectFrame;
        selectFrame = function (el) {
            _currentSvgFrame = null;
            document.querySelectorAll('.frame-option-svg').forEach(function (s) { s.classList.remove('active'); });
            _origSelectFrame(el);
        };
        window.qfpSelectFrame = selectFrame;

        /* Expose current SVG frame for submit handler */
        window.qfpGetCurrentSvgFrame = function () { return _currentSvgFrame; };

        /* Expose selectSvgFrame globally */
        window.qfpSelectSvgFrame = selectSvgFrame;

        /* Allow external code to re-render current SVG frame with modified data (e.g. after color/text change) */
        window.qfpUpdateSvgFrame = function (modifiedFrame) {
            _currentSvgFrame = modifiedFrame;
            applySvgStandardFrame(modifiedFrame);
        };

        /* Attach click handlers to preset frame options */
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
                    d.innerHTML = '<img class="custom-frame-thumb" src="' + _escHtml(f.image_url) + '" alt="' + _escHtml(f.name) + '"><span class="frame-label">' + _escHtml(f.name) + '</span>';
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
                    d.innerHTML = '<img src="' + _escHtml(f.image_url) + '" alt="" '
                        + 'style="width:100%;max-width:40px;height:auto;aspect-ratio:1/1;object-fit:cover;border-radius:4px;display:block;flex-shrink:0;">'
                        + '<span class="frame-label" style="margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%;display:block;">' + _escHtml(f.name) + '</span>';
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
