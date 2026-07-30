function initialize_d3_js() {
    const loc_mode=%s;
    const map_svg="%s";
    const map_svg_image_group="%s";
    console.log('initialize_d3_js', loc_mode, map_svg, map_svg_image_group);
    const svg = d3.select(map_svg);
    const g = svg.select("#everything");
    const map_image = svg.select(map_svg_image_group);
//    console.log("g", g);

    g.selectAll("circle")
      .attr("fill", "steelblue");

    //console.log(d3.selectAll("circle").size());

    if (loc_mode)
        {
        svg.classed("unselectable", true); // disable drag-to-select text behavior
        g.attr("cursor", "grab");

        if (1)
            {
            svg.call(d3.zoom()
                .filter(function(event) {
                        return event.type === "wheel" || !event.ctrlKey && event.button==2; // Only allow wheel events, disable mousedown, mousemove, dblclick
                    })
                .extent([[0, 0], [1000, 1000]])
                .scaleExtent([0.5, 8])
                .translateExtent([[0, 0], [1000,1000]])
                .on("zoom", zoomed));
            console.log("zooming turned on")
            }

        if (1)
            {
            console.log("brushing turned on")
            map_image.call(d3.brush().on("end", ({selection, sourceEvent}) => {
//                if (!sourceEvent) return; // use this if changes to brush here trigger more events
                console.log("brush end", selection)
                var [[x0, y0], [x1, y1]] = [[0, 0], [0, 0]];
                console.log("initial", x0, y0, x1, y1)

                if (selection)
                    [[x0, y0], [x1, y1]] = selection;

                console.log("js_brush_end_event", x0, y0, x1, y1)
                emitEvent('js_brush_end_event', { x0: x0, x1: x1, y0: y0, y1: y1 });
//                d3.event.stopPropagation();

           // Inform downstream cells that the selection has changed.
//         svg.property("value", value).dispatch("input");
         }));}

        g.selectAll(".loc2")
            .call(d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended))
            .on("click", function(event, d) {
              if (event.defaultPrevented)
                    return; // If the drag behavior prevented the default, it was a drag, not a click
              console.log("Clicked!"); // Handle actual click
              emitEvent('js_click_event', { id: this.id });
                })
            ;


        }
    else
        {
        svg.classed("unselectable", false);
//        d3.select("body").classed("unselectable", false);
        svg.call(d3.zoom()
            .extent([[0, 0], [1000, 1000]])
            .scaleExtent([0.5, 8])
            .translateExtent([[0, 0], [1000,1000]])
            .on("zoom", zoomed));
        console.log("handling clicks")
        g.selectAll(".loc2")
            .on("click", function(event, d) {
//            if (event.defaultPrevented) return; // If the drag behavior prevented the default, it was a drag, not a click
                  console.log("location clicked!"); // Handle actual click
                  emitEvent('js_click_event', { id: this.id });
                  })
            .on("dblclick", function(event, d) {
                event.stopPropagation();
                console.log("location double clicked!"); // Handle actual click
                emitEvent('js_dblclick_event', { id: this.id });
                })
            ;
        }

    function get_group(node) {
        const g1 = d3.select(node);
        const g2 = d3.select(g1.attr("xlink:href"));
        return g2;
        }

    function get_rect(node) {
        const g2 = get_group(node);
        r = g2.select("rect");
//      console.log(r);
        return r;
        }

    function dragstarted(e) {
        console.log('dragstarted');
        console.log('dragstarted', e.x, e.y);
        g.attr("cursor", "grabbing");
//      get_rect(this).attr("fill-opacity", 0);
        get_group(this).attr("mask", "url(#drag_mask)");
        g.selectAll(".loc2")
            .attr("opacity", "0.3");
        d3.select(this)
            .raise()
            .attr("opacity", null);

        d3.dragDisable(window);
//      emitEvent('js_drag_start_event', { id: this.id, x: e.x, y: e.y });
      }

    function dragged(e, d) {
//      console.log("drag", "x", +this.getAttribute("x"), "e.x", e.x, "sx", e.subject.x, "dx", e.dx)
        this.setAttribute("x", +this.getAttribute("x") + e.dx);
        this.setAttribute("y", +this.getAttribute("y") + e.dy);
      }

    function dragended(e) {
        d3.dragEnable(window);
        console.log('dragended', e.x, e.y, e.subject.x, e.subject.y, e.dx, e.dy);
        g.attr("cursor", "grab");
//      get_rect(this).attr("fill-opacity", null);
        get_group(this).attr("mask", null);
        g.selectAll(".loc2")
            .attr("opacity", null);
        console.log((e.x-e.subject.x) || (e.y-e.subject.y))
        if ((e.x-e.subject.x) || (e.y-e.subject.y)) {
            emitEvent('js_drag_end_event', { id: this.id, dx: e.x-e.subject.x, dy: e.y-e.subject.y });
            }
      }

    function zoomed({transform}) {
//        console.log('zoomed');
        svg.attr("transform", transform);
    }
};
        // Call the function after the elements are rendered
setTimeout(initialize_d3_js, 400);

