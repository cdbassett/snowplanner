// delivery plans: dragging plan squares on the map, picking a map point while adding a stop, and drag-and-drop of the stop lists. Needs Sortable.min.js loaded first.
(() => {
    window.planPickMode = false;
    window._planEntryHit = false;
    const planGroup = () => document.querySelector('#region_group') || document.querySelector('#everything');
    const toGroup = (grp, cx, cy) => {
        const m = grp.getScreenCTM();
        if (!m) return null;
        const p = new DOMPoint(cx, cy).matrixTransform(m.inverse());
        return { x: p.x, y: p.y };
    };
    let drag = null, justDragged = false;

    const startDrag = (e, use) => {
        const grp = planGroup();
        if (e.button !== 0 || window.planPickMode || !grp) return;
        drag = { use, overlay: document.querySelector('[data-click-id="' + use.id + '"]'), grp, start: toGroup(grp, e.clientX, e.clientY), cx: e.clientX, cy: e.clientY, moved: false };
        e.stopPropagation(); // keeps the map's pan / zoom from starting
    };

    // The map entries live inside a <use>, which hides them from delegated listeners, so listeners go on the entries themselves (like d3 does)
    const bindEntries = () => {
        document.querySelectorAll('.loc2').forEach((el) => {
            if (el._planBound) return;
            el._planBound = true;
            el.addEventListener('click', () => { window._planEntryHit = true; });
            if (el.classList.contains('plan-stop')) el.addEventListener('mousedown', (e) => startDrag(e, el));
        });
    };
    // the delivery plan stop list (rebuilt whenever the plan changes, and only present once its tab was opened) gets drag-to-reorder
    const bindStopList = () => {
        document.querySelectorAll('.plan-seq').forEach((el) => {
            if (el._sortable || typeof Sortable === 'undefined') return;
            // every list (main route and each leg) shares one group so stops can be dragged between them
            el._sortable = Sortable.create(el, {
                group: 'plan-stops', handle: '.plan-handle', animation: 150, forceFallback: true, fallbackOnBody: true, swapThreshold: 0.65,
                onEnd: (evt) => {
                    if (evt.from === evt.to) emitEvent('js_plan_reorder', { leg: el.dataset.leg || '', ids: [...el.children].map(c => c.dataset.id).filter(Boolean) });
                    else emitEvent('js_plan_move', { id: evt.item.dataset.id, leg: evt.to.dataset.leg || '', index: evt.newIndex });
                },
            });
        });
    };
    let bindQueued = false;
    new MutationObserver(() => {
        if (bindQueued) return;
        bindQueued = true;
        requestAnimationFrame(() => { bindQueued = false; bindEntries(); bindStopList(); });
    }).observe(document.documentElement, { childList: true, subtree: true });

    // the icons overlay of a plan square is a plain element, so it can be dragged through delegation
    document.addEventListener('mousedown', (e) => {
        const hit = e.target.closest ? e.target.closest('g.plan[data-click-id]') : null;
        const use = hit && document.getElementById(hit.dataset.clickId);
        if (use) startDrag(e, use);
    }, true);

    document.addEventListener('mousemove', (e) => {
        if (!drag || (!drag.moved && Math.hypot(e.clientX - drag.cx, e.clientY - drag.cy) < 5)) return;
        drag.moved = true;
        const p = toGroup(drag.grp, e.clientX, e.clientY);
        const t = (p.x - drag.start.x) + 'px ' + (p.y - drag.start.y) + 'px';
        drag.use.style.translate = t;
        if (drag.overlay) drag.overlay.style.translate = t;
        e.preventDefault();
    }, true);

    document.addEventListener('mouseup', (e) => {
        if (!drag) return;
        const d = drag;
        drag = null;
        if (!d.moved) return;
        justDragged = true;
        setTimeout(() => { justDragged = false; }, 60);
        const p = toGroup(d.grp, e.clientX, e.clientY);
        if (p && typeof emitEvent === 'function') emitEvent('js_plan_drag_end', { id: d.use.id, x: p.x, y: p.y });
    }, true);

    document.addEventListener('click', (e) => {
        window._planEntryHit = false; // set again by the entry's own listener if this click lands on one
        if (justDragged) { e.stopImmediatePropagation(); e.preventDefault(); }
    }, true);

    // choosing a plan location: a click on empty map is a point; clicks on entries are handled through js_click_event.
    // Captured (and stopped) so that in the region view the area tile's link doesn't navigate away.
    document.addEventListener('click', (e) => {
        if (!window.planPickMode || justDragged || !e.target.closest || !e.target.closest('svg') || e.target.closest('.loc2, [data-click-id]')) return;
        const grp = planGroup();
        const p = grp && toGroup(grp, e.clientX, e.clientY);
        if (!p) return;
        e.preventDefault();
        e.stopPropagation();
        if (typeof emitEvent === 'function') emitEvent('js_map_point_event', p);
    }, true);
})();
