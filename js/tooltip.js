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
    document.addEventListener('mouseover', (e) => {
        const el = e.target.closest ? e.target.closest('[data-tip-title]') : null;
        if (!el) { if (tip) tip.style.display = 'none'; return; }
        const t = ensureTip();
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
    });
    // icons and hover areas sit above the map entries, so pass clicks through to the entry underneath
    document.addEventListener('click', (e) => {
        const el = e.target.closest ? e.target.closest('[data-click-id]') : null;
        if (el && typeof emitEvent === 'function') emitEvent('js_click_event', { id: el.dataset.clickId });
    });
    document.addEventListener('mousemove', (e) => { if (tip && tip.style.display !== 'none') place(e); });
})();
