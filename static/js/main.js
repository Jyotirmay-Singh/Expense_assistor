/* main.js — initializes third-party libraries and lightweight UI enhancements */

document.addEventListener('DOMContentLoaded', () => {
    initAOS();
    initLucide();
    initMockBars();
    initFlashUndo();
});

// Re-run Lucide after Alpine.js processes the DOM so dynamic icons render
document.addEventListener('alpine:initialized', () => {
    initLucide();
});

// Re-run Lucide after HTMX swaps a fragment in (e.g. profile activity results)
document.body.addEventListener('htmx:afterSwap', () => {
    initLucide();
});

// ------------------------------------------------------------------ //
// AOS — scroll-triggered entrance animations                          //
// ------------------------------------------------------------------ //

function initAOS() {
    try {
        if (typeof AOS === 'undefined') return;
        AOS.init({
            once: true,
            duration: 700,
            easing: 'ease-out-cubic',
            offset: 60,
        });
    } catch (err) {
        console.warn('[Spendly] AOS init failed:', err);
    }
}

// ------------------------------------------------------------------ //
// Lucide icons                                                        //
// ------------------------------------------------------------------ //

function initLucide() {
    try {
        if (typeof lucide === 'undefined') return;
        lucide.createIcons();
    } catch (err) {
        console.warn('[Spendly] Lucide init failed:', err);
    }
}

// ------------------------------------------------------------------ //
// Flash "Undo" countdown — depletes alongside the server-side         //
// undo window for soft-deleted expenses                               //
// ------------------------------------------------------------------ //

function initFlashUndo() {
    try {
        document.querySelectorAll('.flash-undo-form[data-undo-seconds]').forEach((form) => {
            const seconds = parseFloat(form.dataset.undoSeconds) || 8;
            const flash = form.closest('.flash');
            const button = form.querySelector('.flash-undo-btn');
            if (!flash || !button) return;

            const bar = document.createElement('div');
            bar.className = 'flash-countdown';
            flash.appendChild(bar);

            requestAnimationFrame(() => {
                bar.style.transitionDuration = `${seconds}s`;
                bar.classList.add('is-counting');
            });

            setTimeout(() => {
                button.disabled = true;
            }, seconds * 1000);
        });
    } catch (err) {
        console.warn('[Spendly] Flash undo init failed:', err);
    }
}

// ------------------------------------------------------------------ //
// Mock chart bars — animate widths on scroll into view                //
// ------------------------------------------------------------------ //

function initMockBars() {
    try {
        const bars = document.querySelectorAll('.mock-bar');
        if (!bars.length) return;

        const targets = Array.from(bars).map(b => b.style.width);
        bars.forEach(b => { b.style.width = '0'; });

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;
                bars.forEach((b, i) => {
                    setTimeout(() => { b.style.width = targets[i]; }, i * 120);
                });
                observer.disconnect();
            });
        }, { threshold: 0.4 });

        const card = document.querySelector('.mock-card');
        if (card) observer.observe(card);
    } catch (err) {
        console.warn('[Spendly] Mock bars animation failed:', err);
    }
}
