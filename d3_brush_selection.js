    x0=%d; y0=%d; x1=%d; y1=%d;
    console.log("d3_brush_selection.js", x0, y0, x1, y1)

    const selectedData = d3
        .select("#map_svg")
        .selectAll(".loc2")
        .filter(function(d, i) {
			const g = d3.select(this);
//			console.log("g", g, g.node());
			const g2 = d3.select(g.attr("xlink:href"))
//			console.log("g2", g2, g2.node());
			const rect = g2.select("rect");
//			console.log("rect", rect, rect.node());
			const left = +g.attr("x") + +rect.attr("x")
			const top = +g.attr("y") + +rect.attr("y")
//			top = +this.getAttribute("y")
			const right = left + +rect.attr("width")
			const bottom = top + +rect.attr("height")
//			console.log(g.attr("id"), left, top, right, bottom);
//			bottom = +this.getAttribute("y")
//			console.log(this, i, r);
			return (!(right < x0 || left > x1 || bottom < y0 || top > y1));
        });
	const ids = selectedData
			  .nodes()
			  .map(node => node.id);
	console.log(ids);
	return ids;

//
//        const targets = Array.from(document.querySelectorAll('.loc2'));
//        let overlapping =
//            targets.filter(el => {
//                const r = el.getBoundingClientRect();
//                return (!(r.right < x1 || r.left > x0 ||
//                      r.bottom < y1 || r.top > y0));
//                })
//            .map(el => el.id);
//        return overlapping;

