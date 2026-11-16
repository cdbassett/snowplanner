// hover tooltips for the map svg (elements carry data-tip-* attributes) and click forwarding for overlay icons
(() => {
    let tip = null;
    const make = (cls, parent) => { const el = document.createElement('div'); el.className = cls; parent.appendChild(el); return el; };
    const ensureTip = () => {
        if (!tip) {
            tip = make('cargo-tip', document.body);
            tip.icon = make('cargo-tip-icon', tip);
            const text = make('', tip);
            tip.name = make('cargo-tip-name', text);
            tip.count = make('cargo-tip-count', text);
            tip.extra = make('cargo-tip-extra', text);
        }
        return tip;
    };
    const place = (e) => {
        const t = ensureTip();
        t.style.left = Math.min(e.clientX + 14, window.innerWidth - t.offsetWidth - 4) + 'px';
        t.style.top = Math.min(e.clientY + 14, window.innerHeight - t.offsetHeight - 4) + 'px';
    };
    let current = null;
    const show = (el, e) => {
        const t = ensureTip();
        current = el;
        t.icon.textContent = '';
        const imgs = (el.dataset.tipImg || '').split(' ').filter(Boolean);
        if (imgs.length) imgs.forEach(src => { const i = document.createElement('img'); i.src = src; i.style.cssText = 'width:34px;height:34px'; t.icon.appendChild(i); });
        else t.icon.textContent = el.dataset.tipIcon;
        t.name.textContent = el.dataset.tipTitle;
        t.count.textContent = el.dataset.tipSub || '';
        t.count.style.display = t.count.textContent ? 'block' : 'none';
        t.extra.textContent = el.dataset.tipExtra || '';
        t.extra.style.display = t.extra.textContent ? 'block' : 'none';
        t.style.display = 'flex';
        place(e);
    };
    const hide = () => { current = null; if (tip) tip.style.display = 'none'; };
    // while editing locations the entries are <use> elements inside the map's own <use>, so the browser reports the outer one as the target; find the entry under the pointer by its box instead (topmost = last drawn)
    const entryUnder = (e) => {
        const uses = document.querySelectorAll('use.loc2[data-tip-title]');
        if (!uses.length) return null;
        const svg = uses[0].ownerSVGElement, ctm = svg && svg.getScreenCTM();
        if (!ctm) return null;
        const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse()); // pointer in the svg's own units; the entries aren't rendered themselves (only through the map's <use>), so their boxes come from the bounding box
        for (let n = uses.length - 1; n >= 0; n--) {
            const u = uses[n], b = u.getBBox(), x = b.x, y = b.y; // already includes the entry's x / y
            if (pt.x >= x && pt.x <= x + b.width && pt.y >= y && pt.y <= y + b.height) return u;
        }
        return null;
    };
    document.addEventListener('mouseover', (e) => {
        const el = e.target.closest ? e.target.closest('[data-tip-title]') : null;
        if (!el) { if (!entryUnder(e)) hide(); return; }
        show(el, e);
    });
    // icons and hover areas sit above the map entries, so pass clicks through to the entry underneath
    document.addEventListener('click', (e) => {
        const el = e.target.closest ? e.target.closest('[data-click-id]') : null;
        if (el && typeof emitEvent === 'function') emitEvent('js_click_event', { id: el.dataset.clickId });
    });
    // the region view has no d3 click handlers: an entry without icons (e.g. a gate) has no overlay, so a click on the entry itself is forwarded here (the area view's d3 handlers do this there)
    document.addEventListener('click', (e) => {
        const el = e.target.closest ? e.target.closest('.loc2') : null;
        if (el && el.id && location.pathname.startsWith('/region/') && typeof emitEvent === 'function') emitEvent('js_click_event', { id: el.id });
    });
    document.addEventListener('mousemove', (e) => {
        const direct = e.target.closest ? e.target.closest('[data-tip-title]') : null;
        const el = direct || entryUnder(e);
        if (el && el !== current) show(el, e);
        else if (!el && current) hide();
        else if (tip && tip.style.display !== 'none') place(e);
    });
})();
